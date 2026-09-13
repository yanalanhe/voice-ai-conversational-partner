"""Per-turn latency instrumentation.

The headline number is TTFA -- Time To First Audio -- measured from
end-of-learner-speech detection to the first audio sample played. Everything
else in this module exists to decompose that number, because a p95 you can
break into stages is worth more than a p50 you cannot explain.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum


class Mark(str, Enum):
    """Stage boundaries in one turn. Ordered as they occur."""

    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"  # endpointer fired; TTFA clock starts here
    STT_FINAL = "stt_final"
    PROMPT_READY = "prompt_ready"
    LLM_FIRST_TOKEN = "llm_first_token"
    FIRST_CLAUSE = "first_clause"  # chunker released clause 1 to TTS
    TTS_FIRST_CHUNK = "tts_first_chunk"
    FIRST_AUDIO_OUT = "first_audio_out"  # TTFA clock stops here
    LLM_COMPLETE = "llm_complete"
    TURN_COMPLETE = "turn_complete"


# Stage durations reported in the latency budget (LATENCY.md 5.2).
_STAGES: tuple[tuple[str, Mark, Mark], ...] = (
    ("stt_finalize", Mark.SPEECH_END, Mark.STT_FINAL),
    ("prompt_assembly", Mark.STT_FINAL, Mark.PROMPT_READY),
    ("llm_ttft", Mark.PROMPT_READY, Mark.LLM_FIRST_TOKEN),
    ("clause_buffer", Mark.LLM_FIRST_TOKEN, Mark.FIRST_CLAUSE),
    ("tts_ttfb", Mark.FIRST_CLAUSE, Mark.TTS_FIRST_CHUNK),
    ("egress", Mark.TTS_FIRST_CHUNK, Mark.FIRST_AUDIO_OUT),
)


@dataclass(slots=True)
class TurnTimeline:
    """Monotonic timestamps for one conversational turn.

    Marks are recorded at most once -- a second `mark()` for the same boundary
    is ignored rather than overwriting, so a retry or a duplicate event cannot
    silently corrupt a latency measurement.
    """

    turn_id: str
    marks: dict[str, float] = field(default_factory=dict)
    barged_in: bool = False

    def mark(self, mark: Mark) -> None:
        self.marks.setdefault(mark.value, time.perf_counter())

    def has(self, mark: Mark) -> bool:
        return mark.value in self.marks

    def _delta_ms(self, start: Mark, end: Mark) -> float | None:
        a, b = self.marks.get(start.value), self.marks.get(end.value)
        if a is None or b is None:
            return None
        return (b - a) * 1000.0

    @property
    def ttfa_ms(self) -> float | None:
        """The number that matters."""
        return self._delta_ms(Mark.SPEECH_END, Mark.FIRST_AUDIO_OUT)

    def stage_durations_ms(self) -> dict[str, float]:
        """Decomposition of TTFA. Missing stages are omitted, not zeroed --
        a stage that did not happen is different from one that took no time."""
        out: dict[str, float] = {}
        for label, start, end in _STAGES:
            d = self._delta_ms(start, end)
            if d is not None:
                out[label] = round(d, 2)
        return out

    def summary(self) -> dict[str, object]:
        return {
            "turn_id": self.turn_id,
            "ttfa_ms": round(self.ttfa_ms, 2) if self.ttfa_ms is not None else None,
            "stages": self.stage_durations_ms(),
            "barged_in": self.barged_in,
        }


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile.

    Deliberately not interpolated: with the sample sizes in an eval run,
    reporting an interpolated p95 implies a precision the data does not have.
    """
    if not values:
        raise ValueError("percentile of empty sequence")
    ordered = sorted(values)
    rank = max(1, min(len(ordered), round(p / 100.0 * len(ordered) + 0.5)))
    return ordered[rank - 1]


@dataclass(slots=True)
class LatencyReport:
    """Aggregate over many turns. Consumed by the CI quality gates."""

    samples: list[float] = field(default_factory=list)

    def add(self, timeline: TurnTimeline) -> None:
        if (t := timeline.ttfa_ms) is not None:
            self.samples.append(t)

    def stats(self) -> dict[str, float | int]:
        if not self.samples:
            return {"n": 0}
        return {
            "n": len(self.samples),
            "p50": round(percentile(self.samples, 50), 2),
            "p95": round(percentile(self.samples, 95), 2),
            "max": round(max(self.samples), 2),
        }


@contextmanager
def stage(timeline: TurnTimeline, start: Mark, end: Mark) -> Iterator[None]:
    """Bracket a block with two marks."""
    timeline.mark(start)
    try:
        yield
    finally:
        timeline.mark(end)
