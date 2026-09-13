"""Data types that cross the provider boundary.

Every type here is vendor-neutral by construction. No Azure, Google, or OpenAI
SDK type may appear in a signature in `protocols.py` -- that rule is what makes
an adapter swappable, and the conformance suite enforces it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# 16-bit signed PCM is the wire format everywhere inside the pipeline.
# Adapters convert to and from whatever their vendor wants at the edge.
BYTES_PER_SAMPLE = 2
DEFAULT_SAMPLE_RATE = 16_000


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class PipelineMode(str, Enum):
    """The two implementations of the pipeline contract (ADR-004)."""

    CASCADED = "cascaded"
    REALTIME = "realtime"


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """A frame of 16-bit mono PCM."""

    data: bytes
    sample_rate: int = DEFAULT_SAMPLE_RATE
    seq: int = 0

    @property
    def duration_ms(self) -> float:
        return len(self.data) / (self.sample_rate * BYTES_PER_SAMPLE) * 1000.0


@dataclass(frozen=True, slots=True)
class Transcript:
    """One STT hypothesis.

    Interim hypotheses drive the UI and speculative generation; only finals
    advance the turn state machine.
    """

    text: str
    is_final: bool = False
    confidence: float = 1.0
    language: str | None = None

    @property
    def is_confident(self) -> bool:
        """Below this, the agent asks for a repeat rather than responding to a
        possibly-hallucinated transcript (see LATENCY.md, L2 speech handling)."""
        return self.confidence >= 0.6


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str

    def truncated_to(self, chars: int) -> Message:
        """Shorten an assistant turn to what the learner actually heard.

        Called on barge-in. If the model believes it said words that were never
        played, the conversation drifts in a way that is invisible in testing.
        See ADR-005.
        """
        return Message(role=self.role, content=self.content[:chars])


@dataclass(frozen=True, slots=True)
class LLMDelta:
    """One streamed increment of model output."""

    text: str = ""
    finish_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def is_final(self) -> bool:
        return self.finish_reason is not None


@dataclass(frozen=True, slots=True)
class SynthesisChunk:
    """Audio for one clause, tagged with the text that produced it.

    `text` is what makes ADR-005 possible: on barge-in we know exactly how many
    characters of the assistant turn reached the learner's ears.
    """

    audio: AudioChunk
    text: str = ""
    seq: int = 0


@dataclass(frozen=True, slots=True)
class PronunciationScore:
    """Result of the out-of-band assessment tap (ADR-006).

    Populated from Azure AI Speech Pronunciation Assessment. `tone_errors` is
    only meaningful for tonal languages; the language pack declares whether to
    collect it.
    """

    accuracy: float
    fluency: float
    completeness: float
    prosody: float | None = None
    word_scores: dict[str, float] = field(default_factory=dict)
    tone_errors: list[str] = field(default_factory=list)

    @property
    def needs_recast(self) -> bool:
        return self.accuracy < 70.0 or bool(self.tone_errors)


@dataclass(slots=True)
class LLMConfig:
    model: str = "mock"
    temperature: float = 0.7
    max_output_tokens: int = 512


@dataclass(slots=True)
class STTConfig:
    """`phrase_hints` is seeded from the active scenario's target vocabulary.

    Biasing the recognizer toward words the learner is *supposed* to attempt is
    the cheapest available win on L2 speech accuracy.
    """

    language: str = "en-US"
    sample_rate: int = DEFAULT_SAMPLE_RATE
    phrase_hints: list[str] = field(default_factory=list)
    interim_results: bool = True


@dataclass(slots=True)
class TTSConfig:
    """`speaking_rate` is set by the learner's level policy, not by the caller.

    Beginners need slower speech; this is a pedagogical parameter that happens
    to live in the TTS config.
    """

    voice: str = "mock-voice"
    language: str = "en-US"
    speaking_rate: float = 1.0
    sample_rate: int = DEFAULT_SAMPLE_RATE
