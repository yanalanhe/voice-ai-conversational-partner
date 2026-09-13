"""CI quality-gate thresholds (PRD Sec 6.3) and the pass/fail check against
them.

Split deliberately from what feeds them: the deterministic and latency gates
are meaningful in the default mock-only CI run (ADR-003) because they measure
mechanism correctness against any model, mock or real. The judge-score gates
(`composite_judge_score`, `min_any_dimension`) are only a meaningful *quality*
signal when scoring a real model's output with a real judge -- against
MockLLM's canned scripted replies they would just be testing the mock's own
fixed script. They are still implemented as real, fully-tested threshold
logic (see test_gates.py) so wiring in a live judge later is a data-supply
change, not a new code path.
"""

from __future__ import annotations

from dataclasses import dataclass

from eval.deterministic import DeterministicReport


@dataclass(frozen=True, slots=True)
class Thresholds:
    composite_judge_score_min: float = 3.2
    min_any_dimension_min: float = 2.8
    vocab_ceiling_violation_rate_max: float = 0.05
    language_leakage_rate_max: float = 0.02
    ttfa_p95_cascaded_replay_max_ms: float = 1400.0


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class GateReport:
    checks: tuple[GateCheck, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> tuple[GateCheck, ...]:
        return tuple(c for c in self.checks if not c.passed)


def check_deterministic_gates(
    report: DeterministicReport,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> GateReport:
    checks = (
        GateCheck(
            "vocab_ceiling_violation_rate",
            report.vocabulary_ceiling_violation_rate <= thresholds.vocab_ceiling_violation_rate_max,
            f"{report.vocabulary_ceiling_violation_rate:.2%} "
            f"<= {thresholds.vocab_ceiling_violation_rate_max:.0%}",
        ),
        GateCheck(
            "language_leakage_rate",
            report.language_leakage_rate <= thresholds.language_leakage_rate_max,
            f"{report.language_leakage_rate:.2%} <= {thresholds.language_leakage_rate_max:.0%}",
        ),
    )
    return GateReport(checks=checks)


def check_latency_gate(
    p95_ms: float,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> GateCheck:
    return GateCheck(
        "ttfa_p95_cascaded_replay",
        p95_ms <= thresholds.ttfa_p95_cascaded_replay_max_ms,
        f"{p95_ms:.0f}ms <= {thresholds.ttfa_p95_cascaded_replay_max_ms:.0f}ms",
    )


def check_judge_gates(
    composite_scores: list[float],
    per_turn_min_scores: list[int],
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> GateReport:
    """Only a meaningful quality signal against real judge output on real
    model replies -- see module docstring. Pure threshold logic either way."""
    avg_composite = sum(composite_scores) / len(composite_scores) if composite_scores else 0.0
    min_dimension = min(per_turn_min_scores) if per_turn_min_scores else 0
    checks = (
        GateCheck(
            "composite_judge_score",
            avg_composite >= thresholds.composite_judge_score_min,
            f"{avg_composite:.2f} >= {thresholds.composite_judge_score_min}",
        ),
        GateCheck(
            "min_any_dimension",
            min_dimension >= thresholds.min_any_dimension_min,
            f"{min_dimension} >= {thresholds.min_any_dimension_min}",
        ),
    )
    return GateReport(checks=checks)
