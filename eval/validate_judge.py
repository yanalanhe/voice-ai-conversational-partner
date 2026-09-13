"""Judge validation: is the LLM judge any good? (PRD EV-5, Sec 6.4)

Most eval harnesses stop at "we use an LLM judge" and never ask whether it
agrees with a human. This module is the piece that asks: given a set of
turns a human scored AND the judge scored, how well do the two agree?
Spearman rank correlation, not Pearson -- rubric scores are ordinal (0-4),
not a continuous measurement, so rank agreement is the honest statistic.

Deliberately pure math with no LLM call inside it. `judge_scores` is supplied
by the caller (a live judge run, or in tests a scripted mock) -- decoupling
the correlation arithmetic from "how were these scores produced" means this
module's correctness can be proven with zero API calls and zero mocking of
an LLM response format.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from eval.schema import GoldenTurn, RubricScore

SPEARMAN_TARGET = 0.7  # PRD EV-5


def _rank(values: Sequence[float]) -> list[float]:
    """Average (fractional) ranks, so tied values share the mean of the
    ranks they'd occupy -- the standard tie-handling for Spearman's rho."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_rho(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rank correlation. Returns 0.0 for fewer than 2 points or when
    either series has zero variance (correlation is undefined, not zero, in
    that case -- 0.0 is a deliberate, documented fallback so callers get a
    float rather than having to handle NaN)."""
    if len(a) != len(b):
        raise ValueError(f"series length mismatch: {len(a)} vs {len(b)}")
    n = len(a)
    if n < 2:
        return 0.0

    ra, rb = _rank(a), _rank(b)
    mean_ra, mean_rb = sum(ra) / n, sum(rb) / n
    cov = sum((ra[i] - mean_ra) * (rb[i] - mean_rb) for i in range(n))
    var_a = sum((r - mean_ra) ** 2 for r in ra)
    var_b = sum((r - mean_rb) ** 2 for r in rb)
    if var_a == 0 or var_b == 0:
        return 0.0
    return float(cov / (var_a * var_b) ** 0.5)


@dataclass(frozen=True, slots=True)
class JudgeValidationResult:
    n: int
    composite_rho: float
    per_dimension_rho: dict[str, float]
    exact_agreement_rate: float
    passed: bool


def validate(
    golden_turns: Sequence[GoldenTurn],
    judge_scores_by_id: dict[str, RubricScore],
) -> JudgeValidationResult:
    """Compare human labels against judge scores for every turn that has both.

    Turns without `human_labels` are silently excluded -- most of the golden
    set has none, by design (see schema.py); this is expected, not an error.
    """
    # Narrow Optional[human_labels] to a plain dict once, here, rather than
    # re-asserting it at every use below -- an empty dict is falsy anyway, so
    # this also naturally excludes a turn with human_labels={}.
    paired: list[tuple[GoldenTurn, dict[str, int], RubricScore]] = [
        (t, t.human_labels, judge_scores_by_id[t.id])
        for t in golden_turns
        if t.human_labels and t.id in judge_scores_by_id
    ]

    if not paired:
        return JudgeValidationResult(
            n=0, composite_rho=0.0, per_dimension_rho={}, exact_agreement_rate=0.0, passed=False
        )

    human_composite = [sum(labels.values()) / len(labels) for _, labels, _ in paired]
    judge_composite = [j.composite for _, _, j in paired]
    composite_rho = spearman_rho(human_composite, judge_composite)

    dimensions = {dim for _, labels, _ in paired for dim in labels}
    per_dimension_rho: dict[str, float] = {}
    for dim in sorted(dimensions):
        human_vals, judge_vals = [], []
        for _, labels, j in paired:
            if dim in labels and dim in j.scores:
                human_vals.append(labels[dim])
                judge_vals.append(j.scores[dim])
        if len(human_vals) >= 2:
            per_dimension_rho[dim] = spearman_rho(human_vals, judge_vals)

    exact_matches = 0
    total_scored = 0
    for _, labels, j in paired:
        for dim, human_val in labels.items():
            if dim in j.scores:
                total_scored += 1
                if j.scores[dim] == human_val:
                    exact_matches += 1
    exact_agreement_rate = exact_matches / total_scored if total_scored else 0.0

    return JudgeValidationResult(
        n=len(paired),
        composite_rho=round(composite_rho, 4),
        per_dimension_rho={k: round(v, 4) for k, v in per_dimension_rho.items()},
        exact_agreement_rate=round(exact_agreement_rate, 4),
        passed=composite_rho >= SPEARMAN_TARGET,
    )
