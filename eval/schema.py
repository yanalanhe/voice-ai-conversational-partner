"""Data shapes for the eval harness.

A `GoldenTurn` records a *situation* (pack, level, scenario, conversation so
far, the learner's next utterance) -- not a fixed expected reply. The harness
generates a fresh agent reply against whatever `LLMProvider` is under test,
then scores that reply deterministically and via judge. This is what lets the
same golden set catch a regression from a prompt change or a model swap: a
hardcoded "expected reply" would go stale the moment either changed, while a
hardcoded *situation* does not.

`human_labels` is populated only for the subset of turns used for judge
validation (PRD EV-5) -- see validate_judge.py. Its absence on most turns is
intentional, not missing data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GoldenTurn:
    id: str
    pack: str
    level: str
    scenario: str
    learner_utterance: str
    history: tuple[tuple[str, str], ...] = ()  # (role, content) pairs before this turn
    expected_behavior: str = ""  # free-text note for human reviewers
    human_labels: dict[str, int] | None = None  # dimension -> 0..4


@dataclass(frozen=True, slots=True)
class GeneratedReply:
    """One golden turn's agent reply, generated fresh by the model under test."""

    turn: GoldenTurn
    reply_text: str


@dataclass(frozen=True, slots=True)
class RubricScore:
    """One judge's scoring of one generated reply."""

    turn_id: str
    scores: dict[str, int]  # dimension -> 0..4
    rubric_version: int
    judge_model: str

    @property
    def composite(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)
