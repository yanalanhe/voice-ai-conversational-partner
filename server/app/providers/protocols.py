"""The provider contracts.

Structural typing (`Protocol`) rather than inheritance, so an adapter is a
plain class that happens to fit -- no base class to import, no framework to
buy into. Adding a vendor means passing `tests/conformance/`, not reading a
wiki. See ADR-002.

Four contracts:

    STTProvider   audio  -> transcripts     (cascaded only)
    LLMProvider   text   -> text            (cascaded only)
    TTSProvider   text   -> audio           (cascaded only)
    RealtimeProvider  audio <-> audio       (realtime only, one socket)

The realtime contract is deliberately *not* expressed as the other three
composed together. A native realtime API does STT, inference, and synthesis
inside one connection and exposes no seam between them. Pretending otherwise
would make the abstraction lie about what the vendor actually does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from app.providers.types import (
    AudioChunk,
    LLMConfig,
    LLMDelta,
    Message,
    PronunciationScore,
    STTConfig,
    SynthesisChunk,
    Transcript,
    TTSConfig,
)


@runtime_checkable
class STTProvider(Protocol):
    """Streaming speech recognition."""

    name: str

    def stream(
        self,
        audio: AsyncIterator[AudioChunk],
        config: STTConfig,
    ) -> AsyncIterator[Transcript]:
        """Consume audio frames, yield hypotheses as they form.

        Must yield interim results when `config.interim_results` is set, and
        must yield exactly one `is_final=True` transcript per detected
        utterance. Implementations should not buffer to end-of-audio: the whole
        point is that partials arrive while the learner is still speaking.
        """
        ...

    async def aclose(self) -> None:
        """Release the underlying connection. Idempotent."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """Streaming text generation."""

    name: str

    def stream(
        self,
        messages: Sequence[Message],
        config: LLMConfig,
    ) -> AsyncIterator[LLMDelta]:
        """Yield output increments as they are generated.

        Must yield a final delta with `finish_reason` set. Cancellation via
        `asyncio.CancelledError` must stop generation promptly -- barge-in
        depends on it.
        """
        ...

    async def aclose(self) -> None: ...


@runtime_checkable
class TTSProvider(Protocol):
    """Streaming speech synthesis."""

    name: str

    def synthesize(
        self,
        text: AsyncIterator[str],
        config: TTSConfig,
    ) -> AsyncIterator[SynthesisChunk]:
        """Consume a stream of clauses, yield audio as it is synthesized.

        Taking an `AsyncIterator[str]` rather than a `str` is the single most
        important shape decision in this file: it lets the pipeline dispatch
        the first clause to TTS while the LLM is still generating the rest.
        That is the largest latency win available in cascaded mode
        (see LATENCY.md 5.4.1).
        """
        ...

    async def aclose(self) -> None: ...


@runtime_checkable
class RealtimeProvider(Protocol):
    """Native speech-to-speech, one duplex connection.

    Trades the text checkpoint for latency: there is no stage at which agent
    text exists before it is spoken, so the vocabulary ceiling can only be
    requested in the system prompt and measured afterward (see PRD 4.6.1).
    """

    name: str

    def converse(
        self,
        audio: AsyncIterator[AudioChunk],
        instructions: str,
        config: LLMConfig,
    ) -> AsyncIterator[SynthesisChunk | Transcript]:
        """Full-duplex exchange.

        Yields a mixed stream: `SynthesisChunk` for agent audio, `Transcript`
        for whatever text the vendor surfaces (agent and learner). Callers
        discriminate on type.
        """
        ...

    async def interrupt(self) -> None:
        """Signal barge-in. Vendors handle truncation server-side."""
        ...

    async def aclose(self) -> None: ...


@runtime_checkable
class PronunciationProvider(Protocol):
    """Out-of-band phonetic scoring (ADR-006).

    Not part of either pipeline. Learner audio is forked at the transport layer
    and assessed in parallel, so the feature survives the cascaded/realtime
    switch and costs zero latency on the critical path.
    """

    name: str

    async def assess(
        self,
        audio: Sequence[AudioChunk],
        reference_text: str,
        language: str,
        *,
        assess_tones: bool = False,
    ) -> PronunciationScore:
        """Score an utterance. Never raises on a bad recognition -- returns a
        low-confidence score instead, because a failed assessment must not take
        down a conversation turn."""
        ...
