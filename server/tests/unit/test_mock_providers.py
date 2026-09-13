from collections.abc import AsyncIterator

from app.providers.mock import (
    LatencyProfile,
    MockLLM,
    MockPronunciation,
    MockSTT,
    MockTTS,
    echo_level_check,
    scripted_tutor,
)
from app.providers.types import (
    AudioChunk,
    LLMConfig,
    Message,
    PronunciationScore,
    Role,
    STTConfig,
    TTSConfig,
)


async def _silence_stream(n: int = 3) -> AsyncIterator[AudioChunk]:
    for i in range(n):
        yield AudioChunk(data=b"\x00" * 320, seq=i)


class TestMockSTT:
    async def test_yields_final_transcript_matching_script(self) -> None:
        stt = MockSTT(utterances=["hello there"], final_latency=LatencyProfile(0.0))
        results = [t async for t in stt.stream(_silence_stream(), STTConfig())]
        finals = [t for t in results if t.is_final]
        assert len(finals) == 1
        assert finals[0].text == "hello there"

    async def test_emits_interims_before_final_when_enabled(self) -> None:
        stt = MockSTT(
            utterances=["one two three"],
            interim_latency=LatencyProfile(0.0),
            final_latency=LatencyProfile(0.0),
        )
        results = [
            t async for t in stt.stream(_silence_stream(), STTConfig(interim_results=True))
        ]
        assert any(not t.is_final for t in results)
        assert results[-1].is_final

    async def test_no_interims_when_disabled(self) -> None:
        stt = MockSTT(utterances=["one two three"], final_latency=LatencyProfile(0.0))
        results = [
            t async for t in stt.stream(_silence_stream(), STTConfig(interim_results=False))
        ]
        assert all(t.is_final for t in results)

    async def test_cursor_advances_across_calls(self) -> None:
        stt = MockSTT(
            utterances=["first", "second"],
            interim_latency=LatencyProfile(0.0),
            final_latency=LatencyProfile(0.0),
        )
        r1 = [t async for t in stt.stream(_silence_stream(), STTConfig(interim_results=False))]
        r2 = [t async for t in stt.stream(_silence_stream(), STTConfig(interim_results=False))]
        assert r1[-1].text == "first"
        assert r2[-1].text == "second"

    async def test_drains_input_audio_even_when_scripted(self) -> None:
        # A real recognizer consumes continuously; failing to drain would
        # deadlock a producer that is awaiting queue space.
        drained = []

        async def audio() -> AsyncIterator[AudioChunk]:
            for i in range(5):
                drained.append(i)
                yield AudioChunk(data=b"\x00", seq=i)

        stt = MockSTT(utterances=["x"], final_latency=LatencyProfile(0.0))
        async for _ in stt.stream(audio(), STTConfig(interim_results=False)):
            pass
        assert drained == [0, 1, 2, 3, 4]


class TestMockLLM:
    async def test_streams_scripted_reply_and_records_call(self) -> None:
        llm = MockLLM(
            responder=scripted_tutor(["Bonjour!"]),
            ttft=LatencyProfile(0.0),
            inter_token=LatencyProfile(0.0),
        )
        messages = [Message(role=Role.USER, content="hi")]
        deltas = [d async for d in llm.stream(messages, LLMConfig())]
        text = "".join(d.text for d in deltas)
        assert "Bonjour!" in text
        assert deltas[-1].finish_reason == "stop"
        assert llm.calls == [messages]

    async def test_scripted_tutor_repeats_last_after_exhausted(self) -> None:
        responder = scripted_tutor(["a", "b"])
        assert responder([]) == "a"
        assert responder([]) == "b"
        assert responder([]) == "b"

    async def test_echo_level_check_violates_ceiling_on_purpose(self) -> None:
        responder = echo_level_check(ceiling={"hello"})
        reply = responder([Message(role=Role.USER, content="hello")])
        assert "notwithstanding" in reply  # a word no beginner ceiling permits


class TestMockTTS:
    async def test_synthesizes_chunk_per_clause(self) -> None:
        tts = MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.0)

        async def clauses() -> AsyncIterator[str]:
            yield "Hello."
            yield "How are you?"

        chunks = [c async for c in tts.synthesize(clauses(), TTSConfig())]
        assert [c.text for c in chunks] == ["Hello.", "How are you?"]
        assert all(c.audio.data for c in chunks)

    async def test_skips_empty_clauses(self) -> None:
        tts = MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.0)

        async def clauses() -> AsyncIterator[str]:
            yield ""
            yield "Real clause."

        chunks = [c async for c in tts.synthesize(clauses(), TTSConfig())]
        assert len(chunks) == 1


class TestMockPronunciation:
    async def test_default_score_is_passing(self) -> None:
        p = MockPronunciation(latency=LatencyProfile(0.0))
        score = await p.assess([], reference_text="hello", language="en-US")
        assert isinstance(score, PronunciationScore)
        assert not score.needs_recast

    async def test_scripted_score_forces_recast(self) -> None:
        p = MockPronunciation(
            scores={"买": PronunciationScore(accuracy=40.0, fluency=50.0, completeness=100.0,
                                              tone_errors=["mai3->mai4"])},
            latency=LatencyProfile(0.0),
        )
        score = await p.assess([], reference_text="买", language="zh-CN", assess_tones=True)
        assert score.needs_recast
        assert score.tone_errors == ["mai3->mai4"]
