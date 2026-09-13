"""Deterministic mock providers with injectable latency.

Not test doubles -- these are first-class components (ADR-003). They make two
otherwise-impossible things possible:

1. **CI with no credentials and no spend.** The whole eval harness runs on
   mocks, so quality gates can block a PR without anyone provisioning keys.

2. **Reproducible latency regression tests.** Real providers jitter, so a real
   p95 cannot fail a build deterministically. Mocks replay a recorded latency
   distribution from a fixed seed, which turns TTFA into a testable number.

Every sleep here is deliberate. Removing them would make tests faster and
worthless.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

from app.providers.types import (
    BYTES_PER_SAMPLE,
    AudioChunk,
    LLMConfig,
    LLMDelta,
    Message,
    PronunciationScore,
    Role,
    STTConfig,
    SynthesisChunk,
    Transcript,
    TTSConfig,
)


@dataclass(frozen=True, slots=True)
class LatencyProfile:
    """A stage's latency as a distribution, not a constant.

    Defaults are the per-stage targets from LATENCY.md 5.2, so a mock run
    reproduces the modelled budget. Set `stdev_ms=0` for exact determinism.
    """

    mean_ms: float
    stdev_ms: float = 0.0

    def sample(self, rng: random.Random) -> float:
        if self.stdev_ms <= 0:
            return max(0.0, self.mean_ms)
        return max(0.0, rng.gauss(self.mean_ms, self.stdev_ms))

    async def sleep(self, rng: random.Random) -> None:
        await asyncio.sleep(self.sample(rng) / 1000.0)


def _pcm_silence(ms: float, sample_rate: int) -> bytes:
    return b"\x00" * (int(sample_rate * ms / 1000.0) * BYTES_PER_SAMPLE)


@dataclass
class MockSTT:
    """Replays scripted transcripts, emitting interims first.

    `utterances` is consumed one entry per `stream()` call, mirroring one
    detected utterance per call.
    """

    utterances: list[str] = field(default_factory=list)
    interim_latency: LatencyProfile = LatencyProfile(80.0)
    final_latency: LatencyProfile = LatencyProfile(100.0)
    confidence: float = 0.95
    seed: int = 0
    name: str = "mock-stt"
    loop: bool = False
    """When the scripted utterances run out: False (default) yields an empty
    transcript forever after, matching a real session that's gone quiet --
    every existing test relies on this. True wraps back to the start, for a
    long-running demo script that should keep going rather than go silent
    (see server/app/main.py's default gateway orchestrator)."""
    received_chunks: list[AudioChunk] | None = None
    """Set to a list to record every AudioChunk drained by `stream()`, across
    all calls. Used by orchestrator tests to prove buffered barge-in audio was
    actually replayed into the next utterance's STT stream, not dropped."""
    _cursor: int = field(default=0, init=False)

    async def stream(
        self,
        audio: AsyncIterator[AudioChunk],
        config: STTConfig,
    ) -> AsyncIterator[Transcript]:
        rng = random.Random(self.seed + self._cursor)

        # Drain the audio the caller is feeding us. A real recognizer consumes
        # continuously; not draining here would deadlock the producer.
        async for chunk in audio:
            if self.received_chunks is not None:
                self.received_chunks.append(chunk)

        if self._cursor < len(self.utterances):
            text = self.utterances[self._cursor]
        elif self.loop and self.utterances:
            text = self.utterances[self._cursor % len(self.utterances)]
        else:
            text = ""
        self._cursor += 1

        if config.interim_results and text:
            words = text.split() or [text]
            # CJK has no spaces, so fall back to character-wise interims.
            if len(words) == 1 and len(text) > 4:
                words = [text[: len(text) // 2], text]
                partials = words
            else:
                partials = [" ".join(words[: i + 1]) for i in range(len(words) - 1)]
            for p in partials:
                await self.interim_latency.sleep(rng)
                yield Transcript(text=p, is_final=False, confidence=self.confidence)

        await self.final_latency.sleep(rng)
        yield Transcript(
            text=text, is_final=True, confidence=self.confidence, language=config.language
        )

    async def aclose(self) -> None:
        return None


@dataclass
class MockLLM:
    """Streams a scripted reply token by token.

    `responder` receives the full message list so tests can assert on what the
    pedagogy layer actually built, not just that something was sent.
    """

    responder: Callable[[Sequence[Message]], str] = lambda _: "That sounds good. Tell me more."
    ttft: LatencyProfile = LatencyProfile(300.0)
    inter_token: LatencyProfile = LatencyProfile(18.0)
    seed: int = 0
    name: str = "mock-llm"
    calls: list[list[Message]] = field(default_factory=list)

    async def stream(
        self,
        messages: Sequence[Message],
        config: LLMConfig,
    ) -> AsyncIterator[LLMDelta]:
        self.calls.append(list(messages))
        rng = random.Random(self.seed + len(self.calls))
        reply = self.responder(messages)

        await self.ttft.sleep(rng)

        # Chunk into token-ish pieces. Latin splits on whitespace; CJK on
        # characters, which is closer to how these models actually tokenize.
        pieces = reply.split(" ") if " " in reply else list(reply)
        emitted = 0
        for i, piece in enumerate(pieces):
            if i > 0:
                await self.inter_token.sleep(rng)
            text = piece + " " if " " in reply and i < len(pieces) - 1 else piece
            emitted += len(text)
            yield LLMDelta(text=text)

        yield LLMDelta(
            finish_reason="stop",
            input_tokens=sum(len(m.content) for m in messages) // 4,
            output_tokens=emitted // 4,
        )

    async def aclose(self) -> None:
        return None


@dataclass
class MockTTS:
    """Synthesizes silence proportional to text length.

    Audio content is irrelevant; timing is the point. `realtime_factor` below
    1.0 means synthesis outruns playback, which is what a real streaming engine
    does and what keeps the jitter buffer fed.
    """

    ttfb: LatencyProfile = LatencyProfile(180.0)
    realtime_factor: float = 0.35
    ms_per_char: float = 60.0
    seed: int = 0
    name: str = "mock-tts"

    async def synthesize(
        self,
        text: AsyncIterator[str],
        config: TTSConfig,
    ) -> AsyncIterator[SynthesisChunk]:
        rng = random.Random(self.seed)
        first = True
        seq = 0

        async for clause in text:
            if not clause:
                continue
            if first:
                await self.ttfb.sleep(rng)
                first = False

            speech_ms = len(clause) * self.ms_per_char / max(config.speaking_rate, 0.1)
            await asyncio.sleep(speech_ms * self.realtime_factor / 1000.0)

            yield SynthesisChunk(
                audio=AudioChunk(
                    data=_pcm_silence(speech_ms, config.sample_rate),
                    sample_rate=config.sample_rate,
                    seq=seq,
                ),
                text=clause,
                seq=seq,
            )
            seq += 1

    async def aclose(self) -> None:
        return None


@dataclass
class MockPronunciation:
    """Scores by a scripted table, defaulting to a passing grade.

    `scores` maps reference text to a score so tests can force a recast without
    needing real audio.
    """

    scores: dict[str, PronunciationScore] = field(default_factory=dict)
    default_accuracy: float = 88.0
    latency: LatencyProfile = LatencyProfile(140.0)
    seed: int = 0
    name: str = "mock-pronunciation"

    async def assess(
        self,
        audio: Sequence[AudioChunk],
        reference_text: str,
        language: str,
        *,
        assess_tones: bool = False,
    ) -> PronunciationScore:
        await self.latency.sleep(random.Random(self.seed))
        if (hit := self.scores.get(reference_text)) is not None:
            return hit
        return PronunciationScore(
            accuracy=self.default_accuracy,
            fluency=self.default_accuracy,
            completeness=100.0,
            prosody=self.default_accuracy,
        )


def scripted_tutor(
    replies: list[str], *, loop: bool = False
) -> Callable[[Sequence[Message]], str]:
    """Responder that walks a fixed list, then either repeats the last entry
    (default) or wraps back to the start (`loop=True`).

    Lets a test drive a multi-turn conversation deterministically. `loop`
    exists to stay in sync with `MockSTT(loop=True)` for a long-running demo
    script -- see server/app/main.py's default gateway orchestrator, which
    pairs the two so a scripted conversation restarts cleanly instead of the
    STT side cycling back to turn 1 while the LLM side is still stuck
    repeating its final reply.
    """
    state = {"i": 0}

    def respond(_: Sequence[Message]) -> str:
        if not replies:
            return ""
        i = state["i"] % len(replies) if loop else min(state["i"], len(replies) - 1)
        state["i"] += 1
        return replies[i]

    return respond


def echo_level_check(ceiling: set[str]) -> Callable[[Sequence[Message]], str]:
    """Responder that deliberately violates a vocabulary ceiling.

    Used by eval tests to prove the deterministic ceiling check actually fires
    -- a check that has never caught anything is not a check.
    """

    def respond(messages: Sequence[Message]) -> str:
        last = next((m for m in reversed(messages) if m.role is Role.USER), None)
        return f"{last.content if last else ''} notwithstanding extraordinarily"

    return respond
