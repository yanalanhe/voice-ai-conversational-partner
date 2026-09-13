"""Per-session turn state machine.

Transport-agnostic on purpose: this class knows nothing about WebSockets or
FastAPI. It exposes three inbound methods (`on_audio_frame`, `on_speech_end`,
`on_speech_start`) driven by whatever transport is in front of it, and writes
outbound events onto an `asyncio.Queue` for that transport to drain. That
separation is what makes the state machine unit-testable against mock
providers with no server running (see test_orchestrator.py) -- and it is
exactly the seam a later transport (LiveKit, a telephony bridge) would plug
into without touching this file.

Barge-in is the one piece of this file that depends on a non-obvious asyncio
fact proven in test_cascaded_pipeline.py: cancelling `_turn_task` from here
and awaiting it collapses `BargeInError` into a plain `CancelledError` at this
call site (Task-boundary cancellation always does that, regardless of the
exception subclass). That is fine -- this method already knows *why* it
cancelled the task, so it does not need the exception's identity, only the
side effect already written onto the shared `TurnTimeline` object
(`barged_in = True`) before the exception was swallowed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from app.pipeline.cascaded import run_turn
from app.providers.protocols import LLMProvider, STTProvider, TTSProvider
from app.providers.types import (
    AudioChunk,
    LLMConfig,
    Message,
    Role,
    STTConfig,
    TTSConfig,
)
from app.session.events import (
    AssistantAudioEvent,
    OrchestratorEvent,
    TranscriptEvent,
    TurnCompleteEvent,
    TurnInterruptedEvent,
)
from app.telemetry.spans import Mark, TurnTimeline

# How many recent learner audio frames to keep while the agent is speaking.
# On barge-in these are replayed into the new utterance's STT stream so the
# first syllables of the interruption are not lost while the client's
# speech_start control message is in flight.
_BARGE_IN_BUFFER_FRAMES = 100  # ~2s at 20ms frames


async def _drain_queue(queue: asyncio.Queue[AudioChunk | None]) -> AsyncIterator[AudioChunk]:
    """Adapt a Queue into the AsyncIterator[AudioChunk] the STT protocol wants.

    Ends when a `None` sentinel is dequeued -- `on_speech_end` puts one to
    signal the current utterance is over.
    """
    while (item := await queue.get()) is not None:
        yield item


@dataclass
class SessionOrchestrator:
    stt: STTProvider
    llm: LLMProvider
    tts: TTSProvider
    outbox: asyncio.Queue[OrchestratorEvent]
    system_prompt: str = (
        "You are a friendly conversation partner helping someone practice a "
        "language. Keep replies short and natural."
    )
    stt_config: STTConfig = field(default_factory=STTConfig)
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    tts_config: TTSConfig = field(default_factory=TTSConfig)
    on_turn_complete: Callable[[str, str], None] | None = None
    """Called (learner_text, agent_text) after each turn that finishes
    normally (never on barge-in). Lets a caller wire in pedagogy checks --
    e.g. the vocabulary-ceiling check in app/pedagogy/ceiling.py -- without
    this module importing anything pedagogy-specific. Kept as a plain
    callback, not an event, because it needs to observe the full turn text at
    exactly the point of completion, not race the outbox consumer."""

    _messages: list[Message] = field(default_factory=list, init=False)
    _state: str = field(default="listening", init=False)  # "listening" | "speaking"
    _audio_queue: asyncio.Queue[AudioChunk | None] | None = field(default=None, init=False)
    _pending_barge_in_audio: list[AudioChunk] = field(default_factory=list, init=False)
    _turn_task: asyncio.Task[None] | None = field(default=None, init=False)
    _current_timeline: TurnTimeline | None = field(default=None, init=False)
    _turn_counter: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._open_new_audio_queue()

    @property
    def state(self) -> str:
        return self._state

    @property
    def history(self) -> list[Message]:
        return list(self._messages)

    def _open_new_audio_queue(self) -> None:
        self._audio_queue = asyncio.Queue()

    async def on_audio_frame(self, chunk: AudioChunk) -> None:
        """Route one frame of learner audio.

        While listening, frames feed the open STT stream directly. While the
        agent is speaking, frames cannot go to STT yet (no stream is open --
        `on_speech_end` hasn't been called), so they are buffered in case this
        turns into a barge-in.
        """
        if self._state == "listening" and self._audio_queue is not None:
            await self._audio_queue.put(chunk)
        elif self._state == "speaking":
            self._pending_barge_in_audio.append(chunk)
            if len(self._pending_barge_in_audio) > _BARGE_IN_BUFFER_FRAMES:
                self._pending_barge_in_audio.pop(0)

    async def on_speech_start(self) -> None:
        """Client-side VAD detected the learner starting to talk.

        If the agent is mid-turn, this is a barge-in: cancel the turn task,
        drain any buffered pre-interruption audio into a fresh STT stream, and
        return to listening. If the agent is already listening, this is just
        the normal start of an utterance -- a no-op beyond making sure a
        stream is open.
        """
        if self._state == "speaking":
            await self._cancel_current_turn()
            self._open_new_audio_queue()
            for chunk in self._pending_barge_in_audio:
                await self._audio_queue.put(chunk)  # type: ignore[union-attr]
            self._pending_barge_in_audio.clear()
            self._state = "listening"
        elif self._audio_queue is None:
            self._open_new_audio_queue()

    async def _cancel_current_turn(self) -> None:
        task, timeline = self._turn_task, self._current_timeline
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # expected: we just requested this cancellation
        self._turn_task = None
        if timeline is not None:
            await self.outbox.put(TurnInterruptedEvent(summary=timeline.summary()))
        self._current_timeline = None

    async def on_speech_end(self) -> None:
        """Client-side VAD detected silence: finalize the utterance.

        Closes the current audio stream, drains STT for the final transcript,
        and -- if the learner actually said something -- kicks off a turn.
        """
        if self._audio_queue is None:
            return
        timeline = TurnTimeline(turn_id=str(self._turn_counter))
        timeline.mark(Mark.SPEECH_END)

        queue = self._audio_queue
        self._audio_queue = None
        await queue.put(None)

        final_text = ""
        async for transcript in self.stt.stream(_drain_queue(queue), self.stt_config):
            if transcript.is_final:
                timeline.mark(Mark.STT_FINAL)
                final_text = transcript.text

        if not final_text.strip():
            self._open_new_audio_queue()
            return

        self._turn_counter += 1
        self._messages.append(Message(role=Role.USER, content=final_text))
        await self.outbox.put(TranscriptEvent(text=final_text))

        self._state = "speaking"
        self._current_timeline = timeline
        self._turn_task = asyncio.create_task(self._run_turn(timeline, final_text))

    def _build_messages(self) -> list[Message]:
        return [Message(role=Role.SYSTEM, content=self.system_prompt), *self._messages]

    async def _run_turn(self, timeline: TurnTimeline, learner_text: str) -> None:
        """Generate and stream one assistant turn.

        `learner_text` is passed explicitly rather than re-read from
        `self._messages[-1]` -- it is the exact utterance `on_speech_end`
        already extracted, and indexing into a list that could in principle
        grow is a needless way to reintroduce the same value with a chance of
        drift.

        If cancelled (barge-in), control never reaches the lines after the
        `async for` -- `_cancel_current_turn` is solely responsible for the
        state transition back to "listening" in that case, so this function
        must not also perform it, or the two would race.
        """
        timeline.mark(Mark.PROMPT_READY)
        messages = self._build_messages()
        reply_parts: list[str] = []

        async for chunk in run_turn(
            self.llm, self.tts, messages, self.llm_config, self.tts_config, timeline
        ):
            reply_parts.append(chunk.text)
            await self.outbox.put(AssistantAudioEvent(chunk=chunk))

        agent_text = "".join(reply_parts)
        self._messages.append(Message(role=Role.ASSISTANT, content=agent_text))
        await self.outbox.put(TurnCompleteEvent(summary=timeline.summary()))
        self._turn_task = None
        self._current_timeline = None
        self._state = "listening"
        self._open_new_audio_queue()

        if self.on_turn_complete is not None:
            self.on_turn_complete(learner_text, agent_text)

    def restore_history(self, messages: list[Message]) -> None:
        """Resume a session with prior conversation context (PRD LS-2).

        Only valid before any turn has started -- call this immediately after
        construction, before the first `on_speech_end`.
        """
        self._messages = list(messages)

    async def close(self) -> None:
        """Release the current turn task and providers. Idempotent."""
        await self._cancel_current_turn()
        await self.stt.aclose()
        await self.llm.aclose()
        await self.tts.aclose()
