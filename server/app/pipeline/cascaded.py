"""Cascaded STT -> LLM -> TTS pipeline (ADR-004).

Cascaded mode buys a text checkpoint: agent text exists before it is spoken,
so a vocabulary-ceiling check could in principle regenerate a bad reply before
it reaches TTS (see PRD 4.6.1). That checkpoint is what realtime mode gives up
in exchange for lower latency.

The concurrency shape is the whole point of this module. The LLM stream and
the TTS stream run as two tasks overlapped through a queue of ready clauses.
Without that overlap, "clause-level TTS pipelining" (LATENCY.md 5.4.1) does
not exist -- TTS would simply wait for the full reply before starting.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from app.pipeline.chunker import ClauseChunker
from app.providers.protocols import LLMProvider, TTSProvider
from app.providers.types import LLMConfig, Message, SynthesisChunk, TTSConfig
from app.telemetry.spans import Mark, TurnTimeline


class BargeInError(asyncio.CancelledError):
    """Raised out of `run_turn` when the caller cancels mid-generation.

    Barge-in must be delivered as cancellation of the *task* running this
    generator (`task.cancel()`), not by the caller abandoning iteration -- the
    latter raises `GeneratorExit`, which this function does not special-case.
    Naming the re-raised exception makes the intent legible at the call site
    (the session orchestrator) instead of looking like an unexplained
    cancellation.
    """


async def run_turn(
    llm: LLMProvider,
    tts: TTSProvider,
    messages: Sequence[Message],
    llm_config: LLMConfig,
    tts_config: TTSConfig,
    timeline: TurnTimeline,
    *,
    chunker: ClauseChunker | None = None,
) -> AsyncIterator[SynthesisChunk]:
    """Run one assistant turn: LLM generation pipelined into TTS synthesis.

    Caller must mark `Mark.PROMPT_READY` before invoking this -- prompt
    assembly (RAG, pedagogy) happens upstream and this function only measures
    generation and synthesis.
    """
    chunker = chunker or ClauseChunker()
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    first_clause_seen = False

    async def feed_llm() -> None:
        nonlocal first_clause_seen
        try:
            async for delta in llm.stream(messages, llm_config):
                if delta.text:
                    if not timeline.has(Mark.LLM_FIRST_TOKEN):
                        timeline.mark(Mark.LLM_FIRST_TOKEN)
                    for clause in chunker.feed(delta.text):
                        if not first_clause_seen:
                            timeline.mark(Mark.FIRST_CLAUSE)
                            first_clause_seen = True
                        await queue.put(clause)
                if delta.is_final:
                    timeline.mark(Mark.LLM_COMPLETE)
        finally:
            remainder = chunker.flush()
            if remainder:
                if not first_clause_seen:
                    timeline.mark(Mark.FIRST_CLAUSE)
                    first_clause_seen = True
                await queue.put(remainder)
            await queue.put(None)  # sentinel: no more clauses

    async def clause_stream() -> AsyncIterator[str]:
        while (clause := await queue.get()) is not None:
            yield clause

    feed_task = asyncio.create_task(feed_llm())
    try:
        first_audio = True
        async for chunk in tts.synthesize(clause_stream(), tts_config):
            if not timeline.has(Mark.TTS_FIRST_CHUNK):
                timeline.mark(Mark.TTS_FIRST_CHUNK)
            if first_audio:
                timeline.mark(Mark.FIRST_AUDIO_OUT)
                first_audio = False
            yield chunk
        await feed_task
    except asyncio.CancelledError:
        timeline.barged_in = True
        feed_task.cancel()
        raise BargeInError from None
    finally:
        if not feed_task.done():
            feed_task.cancel()
        timeline.mark(Mark.TURN_COMPLETE)
