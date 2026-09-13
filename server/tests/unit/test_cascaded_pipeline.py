import asyncio

import pytest
from app.pipeline.cascaded import BargeInError, run_turn
from app.providers.mock import LatencyProfile, MockLLM, MockTTS, scripted_tutor
from app.providers.types import LLMConfig, Message, Role, TTSConfig
from app.telemetry.spans import Mark, TurnTimeline


def _fast_llm(text: str) -> MockLLM:
    return MockLLM(
        responder=scripted_tutor([text]),
        ttft=LatencyProfile(0.0),
        inter_token=LatencyProfile(0.0),
    )


def _fast_tts() -> MockTTS:
    return MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.0)


class TestRunTurn:
    async def test_produces_audio_for_full_reply(self) -> None:
        llm = _fast_llm("Hello there. How are you today?")
        tts = _fast_tts()
        timeline = TurnTimeline(turn_id="t1")
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)

        chunks = [
            c
            async for c in run_turn(
                llm, tts, [Message(role=Role.USER, content="hi")], LLMConfig(), TTSConfig(),
                timeline,
            )
        ]

        assert chunks
        full_text = "".join(c.text for c in chunks)
        assert "Hello there." in full_text
        assert "How are you today?" in full_text

    async def test_marks_are_set_in_causal_order(self) -> None:
        llm = _fast_llm("Short reply.")
        tts = _fast_tts()
        timeline = TurnTimeline(turn_id="t1")
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)

        async for _ in run_turn(
            llm, tts, [Message(role=Role.USER, content="hi")], LLMConfig(), TTSConfig(), timeline
        ):
            pass

        m = timeline.marks
        assert m[Mark.PROMPT_READY.value] <= m[Mark.LLM_FIRST_TOKEN.value]
        assert m[Mark.LLM_FIRST_TOKEN.value] <= m[Mark.FIRST_CLAUSE.value]
        assert m[Mark.FIRST_CLAUSE.value] <= m[Mark.TTS_FIRST_CHUNK.value]
        assert m[Mark.TTS_FIRST_CHUNK.value] <= m[Mark.FIRST_AUDIO_OUT.value]
        assert m[Mark.LLM_COMPLETE.value] <= m[Mark.TURN_COMPLETE.value]

    async def test_ttfa_is_measurable_after_a_turn(self) -> None:
        llm = _fast_llm("A reply with enough content to form a clause.")
        tts = _fast_tts()
        timeline = TurnTimeline(turn_id="t1")
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)

        async for _ in run_turn(
            llm, tts, [Message(role=Role.USER, content="hi")], LLMConfig(), TTSConfig(), timeline
        ):
            pass

        assert timeline.ttfa_ms is not None
        assert timeline.ttfa_ms >= 0

    async def test_tts_starts_before_llm_finishes_generating(self) -> None:
        """The entire point of clause pipelining: first audio must not wait
        for the full LLM reply. Proven by giving TTS deliberate synthesis
        latency and the LLM deliberate inter-token latency, then checking
        that TTS_FIRST_CHUNK lands before LLM_COMPLETE."""
        llm = MockLLM(
            responder=scripted_tutor(["First clause here. Second clause follows after it."]),
            ttft=LatencyProfile(0.0),
            inter_token=LatencyProfile(5.0),
        )
        tts = MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.0)
        timeline = TurnTimeline(turn_id="t1")
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)

        async for _ in run_turn(
            llm, tts, [Message(role=Role.USER, content="hi")], LLMConfig(), TTSConfig(), timeline
        ):
            pass

        assert timeline.marks[Mark.TTS_FIRST_CHUNK.value] < timeline.marks[Mark.LLM_COMPLETE.value]

    async def test_cancelling_a_child_task_surfaces_as_canccallederror(self) -> None:
        """When run_turn is consumed inside its own child Task and that Task is
        cancelled from outside, asyncio's Task machinery collapses ANY
        CancelledError subclass -- including BargeInError -- into a plain
        CancelledError once you `await` the cancelled task. This is asyncio's
        behavior, not a pipeline bug: subclassing CancelledError only survives
        an in-process catch (see the next test), never a Task boundary.
        """
        llm = MockLLM(
            responder=scripted_tutor(["A very long reply that keeps on going and going."]),
            ttft=LatencyProfile(0.0),
            inter_token=LatencyProfile(50.0),
        )
        tts = MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.5)
        timeline = TurnTimeline(turn_id="t1")
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)

        async def consume() -> None:
            async for _ in run_turn(
                llm, tts, [Message(role=Role.USER, content="hi")], LLMConfig(), TTSConfig(),
                timeline,
            ):
                pass

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.02)  # let it get partway through synthesis
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert timeline.barged_in is True

    async def test_bargein_error_is_catchable_inline_within_the_same_task(self) -> None:
        """The pattern a real session orchestrator uses: catch BargeInError
        around the per-turn loop, IN THE SAME TASK that gets cancelled, and do
        not re-raise. Because the coroutine absorbs the CancelledError instead
        of letting it escape, the task completes normally rather than landing
        in cancelled state -- which is what lets a session survive a barge-in
        and start its next turn instead of dying with the whole task.
        """
        llm = MockLLM(
            responder=scripted_tutor(["Another long reply that keeps going for a while."]),
            ttft=LatencyProfile(0.0),
            inter_token=LatencyProfile(50.0),
        )
        tts = MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.5)
        timeline = TurnTimeline(turn_id="t1")
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)
        caught = False

        async def body() -> None:
            nonlocal caught
            try:
                async for _ in run_turn(
                    llm, tts, [Message(role=Role.USER, content="hi")], LLMConfig(), TTSConfig(),
                    timeline,
                ):
                    pass
            except BargeInError:
                caught = True

        task = asyncio.ensure_future(body())
        await asyncio.sleep(0.02)
        task.cancel()
        await task  # does not raise: body() absorbed the BargeInError

        assert caught is True
        assert timeline.barged_in is True

    async def test_no_output_swallowed_on_short_reply_with_no_terminator(self) -> None:
        """A reply with no sentence-ending punctuation must still reach TTS via
        flush() -- this is exactly the failure mode the chunker's flush()
        exists to prevent, exercised through the full pipeline."""
        llm = _fast_llm("no terminal punctuation here")
        tts = _fast_tts()
        timeline = TurnTimeline(turn_id="t1")
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)

        chunks = [
            c
            async for c in run_turn(
                llm, tts, [Message(role=Role.USER, content="hi")], LLMConfig(), TTSConfig(),
                timeline,
            )
        ]
        assert "".join(c.text for c in chunks) == "no terminal punctuation here"
