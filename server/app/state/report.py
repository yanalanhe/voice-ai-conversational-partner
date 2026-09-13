"""End-of-session report (PRD PD-5), built entirely from signals this repo
can honestly compute without a real grammar-error detector: vocabulary
ceiling violations, target-vocabulary elicitation, and talk-time ratio. These
are exactly the deterministic checks PRD EV-3 asks the eval harness to run --
this module and the eval harness share `check_ceiling`, so a learner's live
session report and an offline eval run are scored the same way.

Word counts use the pack's own tokenizer (`app.pedagogy.ceiling.tokenize`),
not `str.split()` -- Mandarin has no whitespace between words, so a naive
split would silently undercount every zh_hsk session to "one giant word."
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.pedagogy.ceiling import check_ceiling, tokenize
from app.pedagogy.models import LevelPolicy, Scenario, Tokenizer
from app.providers.types import Message, Role

_VIOLATION_RATE_NEEDS_REVIEW = 0.05


@dataclass(frozen=True, slots=True)
class SessionReport:
    learner_id: str
    scenario_id: str
    level_code: str
    turns: int
    learner_word_count: int
    agent_word_count: int
    talk_ratio: float  # learner words / (learner + agent words), 0..1
    vocabulary_ceiling_violations: int
    vocabulary_ceiling_violation_rate: float
    target_vocabulary_used: tuple[str, ...]
    target_vocabulary_missed: tuple[str, ...]
    next_steps: str


def build_session_report(
    learner_id: str,
    scenario: Scenario,
    level: LevelPolicy,
    tokenizer: Tokenizer,
    messages: Sequence[Message],
) -> SessionReport:
    learner_words = 0
    agent_words = 0
    violations = 0
    total_tokens = 0
    used_vocab: set[str] = set()
    turns = 0

    for m in messages:
        if m.role is Role.USER:
            turns += 1
            learner_words += len(tokenize(m.content, tokenizer))
            for word in scenario.target_vocabulary:
                if word in m.content:
                    used_vocab.add(word)
        elif m.role is Role.ASSISTANT:
            agent_words += len(tokenize(m.content, tokenizer))
            result = check_ceiling(m.content, level, tokenizer)
            violations += result.violation_count
            total_tokens += result.total_tokens

    total_words = learner_words + agent_words
    talk_ratio = learner_words / total_words if total_words else 0.0
    violation_rate = violations / total_tokens if total_tokens else 0.0
    missed = tuple(w for w in scenario.target_vocabulary if w not in used_vocab)

    if violation_rate > _VIOLATION_RATE_NEEDS_REVIEW:
        next_steps = (
            f"Review vocabulary at the {level.code} level -- several agent "
            "replies used words above the ceiling."
        )
    elif missed:
        next_steps = f"Try to use these words next time: {', '.join(missed)}."
    else:
        next_steps = f"Good progress at {level.code}. Ready for a new scenario or the next level."

    return SessionReport(
        learner_id=learner_id,
        scenario_id=scenario.id,
        level_code=level.code,
        turns=turns,
        learner_word_count=learner_words,
        agent_word_count=agent_words,
        talk_ratio=round(talk_ratio, 3),
        vocabulary_ceiling_violations=violations,
        vocabulary_ceiling_violation_rate=round(violation_rate, 4),
        target_vocabulary_used=tuple(sorted(used_vocab)),
        target_vocabulary_missed=missed,
        next_steps=next_steps,
    )
