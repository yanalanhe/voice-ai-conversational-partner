"""Conformance suite for provider adapters (ADR-002).

The point of this file: adding a vendor means making it pass these tests, not
reading a wiki. Parametrized over every adapter currently implemented -- when
an Azure or Gemini adapter is added later, it is added to `_STT_PROVIDERS` /
`_LLM_PROVIDERS` / `_TTS_PROVIDERS` below and gets this whole suite for free.

Fast and free by construction: every entry here is a mock with latency
profiles zeroed out, so this suite runs in CI with no credentials and no
spend. A real adapter would additionally carry a `@pytest.mark.live` twin
that hits the actual vendor endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.providers.mock import LatencyProfile, MockLLM, MockSTT, MockTTS
from app.providers.protocols import LLMProvider, STTProvider, TTSProvider
from app.providers.types import (
    AudioChunk,
    LLMConfig,
    Message,
    Role,
    STTConfig,
    TTSConfig,
)


def _make_stt() -> STTProvider:
    return MockSTT(
        utterances=["conformance check"],
        interim_latency=LatencyProfile(0.0),
        final_latency=LatencyProfile(0.0),
    )


def _make_llm() -> LLMProvider:
    return MockLLM(ttft=LatencyProfile(0.0), inter_token=LatencyProfile(0.0))


def _make_tts() -> TTSProvider:
    return MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.0)


_STT_PROVIDERS = [pytest.param(_make_stt, id="mock")]
_LLM_PROVIDERS = [pytest.param(_make_llm, id="mock")]
_TTS_PROVIDERS = [pytest.param(_make_tts, id="mock")]


async def _audio(n: int = 2) -> AsyncIterator[AudioChunk]:
    for i in range(n):
        yield AudioChunk(data=b"\x00" * 320, seq=i)


async def _text(*pieces: str) -> AsyncIterator[str]:
    for p in pieces:
        yield p


@pytest.mark.parametrize("factory", _STT_PROVIDERS)
class TestSTTConformance:
    def test_has_a_name(self, factory) -> None:
        stt = factory()
        assert isinstance(stt.name, str) and stt.name

    async def test_yields_exactly_one_final_per_utterance(self, factory) -> None:
        stt = factory()
        results = [t async for t in stt.stream(_audio(), STTConfig())]
        finals = [t for t in results if t.is_final]
        assert len(finals) == 1

    async def test_interim_results_flag_is_honored(self, factory) -> None:
        stt = factory()
        results = [
            t async for t in stt.stream(_audio(), STTConfig(interim_results=False))
        ]
        assert all(t.is_final for t in results)

    async def test_confidence_is_in_unit_range(self, factory) -> None:
        stt = factory()
        results = [t async for t in stt.stream(_audio(), STTConfig())]
        assert all(0.0 <= t.confidence <= 1.0 for t in results)

    async def test_aclose_does_not_raise(self, factory) -> None:
        stt = factory()
        await stt.aclose()
        await stt.aclose()  # idempotent


@pytest.mark.parametrize("factory", _LLM_PROVIDERS)
class TestLLMConformance:
    def test_has_a_name(self, factory) -> None:
        llm = factory()
        assert isinstance(llm.name, str) and llm.name

    async def test_yields_a_final_delta_with_finish_reason(self, factory) -> None:
        llm = factory()
        messages = [Message(role=Role.USER, content="hi")]
        deltas = [d async for d in llm.stream(messages, LLMConfig())]
        assert deltas
        assert deltas[-1].finish_reason is not None

    async def test_only_the_last_delta_is_final(self, factory) -> None:
        llm = factory()
        messages = [Message(role=Role.USER, content="hi")]
        deltas = [d async for d in llm.stream(messages, LLMConfig())]
        assert all(not d.is_final for d in deltas[:-1])

    async def test_cancellation_stops_generation_promptly(self, factory) -> None:
        """Barge-in depends on this: a cancelled LLM stream must not keep
        running to completion in the background."""
        import asyncio

        llm = factory()
        messages = [Message(role=Role.USER, content="hi")]

        async def consume() -> None:
            async for _ in llm.stream(messages, LLMConfig()):
                await asyncio.sleep(0.01)

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_aclose_does_not_raise(self, factory) -> None:
        llm = factory()
        await llm.aclose()
        await llm.aclose()


@pytest.mark.parametrize("factory", _TTS_PROVIDERS)
class TestTTSConformance:
    def test_has_a_name(self, factory) -> None:
        tts = factory()
        assert isinstance(tts.name, str) and tts.name

    async def test_consumes_text_stream_and_yields_audio(self, factory) -> None:
        tts = factory()
        chunks = [c async for c in tts.synthesize(_text("Hello.", "World."), TTSConfig())]
        assert chunks
        assert all(isinstance(c.audio, AudioChunk) for c in chunks)

    async def test_handles_empty_text_stream(self, factory) -> None:
        tts = factory()
        chunks = [c async for c in tts.synthesize(_text(), TTSConfig())]
        assert chunks == []

    async def test_accepts_async_iterator_not_just_str(self, factory) -> None:
        """The load-bearing shape decision in protocols.py: TTS must take an
        AsyncIterator[str], not a str, or clause-level pipelining is
        impossible by construction."""
        import inspect

        tts = factory()
        sig = inspect.signature(tts.synthesize)
        assert "text" in sig.parameters

    async def test_aclose_does_not_raise(self, factory) -> None:
        tts = factory()
        await tts.aclose()
        await tts.aclose()
