"""Deterministic (non-LLM) checks over generated replies (PRD EV-3).

These reuse the same building blocks report.py uses for a live session
(`app.pedagogy.ceiling.check_ceiling`, `tokenize`) -- a learner's live
end-of-session report and an offline eval run are scored by the identical
mechanism, which is what makes this harness a real predictor of live session
quality rather than a parallel, disconnected metric.

`target_vocabulary_reference_rate` is named carefully: it measures whether
the agent's OWN reply models the scenario's target vocabulary, which is
computable from a single turn. True *elicitation* -- did the learner go on to
use it -- needs the learner's next utterance, which a single golden-set entry
does not have by construction (see schema.py). Calling this "elicitation"
would overclaim what a one-shot check can prove.

`language_leakage_rate` is a coarse heuristic, not a language-ID model: for
CJK packs, any run of 3+ ASCII letters is treated as leaked source-language
text (a rare loanword or proper noun is a known false-positive source). For
whitespace-tokenized packs, leakage is detected via a short list of common
English marker words -- it will miss real leakage that avoids all of them.
Both limitations are documented here, not silently absorbed into the number.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.pedagogy.ceiling import check_ceiling, tokenize
from app.pedagogy.models import LanguagePack, Tokenizer

from eval.schema import GeneratedReply

_ASCII_RUN = re.compile(r"[A-Za-z]{3,}")
_ENGLISH_MARKERS = frozenset(
    {"the", "is", "and", "you", "yes", "hello", "please", "thanks", "what", "how"}
)


def _has_language_leakage(text: str, tokenizer: Tokenizer) -> bool:
    if tokenizer is Tokenizer.JIEBA:
        return bool(_ASCII_RUN.search(text))
    words = {w.lower() for w in tokenize(text, tokenizer)}
    return bool(words & _ENGLISH_MARKERS)


@dataclass(frozen=True, slots=True)
class DeterministicReport:
    n: int
    vocabulary_ceiling_violation_rate: float
    avg_agent_words_per_turn: float
    target_vocabulary_reference_rate: float
    language_leakage_rate: float


def compute_deterministic_metrics(
    replies: Sequence[GeneratedReply],
    pack: LanguagePack,
) -> DeterministicReport:
    if not replies:
        return DeterministicReport(0, 0.0, 0.0, 0.0, 0.0)

    total_violations = 0
    total_tokens = 0
    total_words = 0
    referenced_count = 0
    leaked_count = 0

    for gen in replies:
        level = pack.level(gen.turn.level)
        scenario = pack.scenario(gen.turn.scenario)

        result = check_ceiling(gen.reply_text, level, pack.tokenizer)
        total_violations += result.violation_count
        total_tokens += result.total_tokens
        total_words += len(tokenize(gen.reply_text, pack.tokenizer))

        if scenario.target_vocabulary and any(
            w in gen.reply_text for w in scenario.target_vocabulary
        ):
            referenced_count += 1

        if not level.l1_scaffolding_allowed and _has_language_leakage(
            gen.reply_text, pack.tokenizer
        ):
            leaked_count += 1

    n = len(replies)
    return DeterministicReport(
        n=n,
        vocabulary_ceiling_violation_rate=(
            round(total_violations / total_tokens, 4) if total_tokens else 0.0
        ),
        avg_agent_words_per_turn=round(total_words / n, 2),
        target_vocabulary_reference_rate=round(referenced_count / n, 4),
        language_leakage_rate=round(leaked_count / n, 4),
    )
