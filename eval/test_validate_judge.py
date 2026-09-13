from __future__ import annotations

import pytest

from eval.schema import GoldenTurn, RubricScore
from eval.validate_judge import spearman_rho, validate


def _turn(turn_id: str, human_labels: dict[str, int] | None) -> GoldenTurn:
    return GoldenTurn(
        id=turn_id, pack="zh_hsk", level="HSK1", scenario="ordering_lunch",
        learner_utterance="x", human_labels=human_labels,
    )


class TestSpearmanRho:
    def test_perfect_positive_correlation(self) -> None:
        assert spearman_rho([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self) -> None:
        assert spearman_rho([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_hand_computed_tie_case(self) -> None:
        # Worked by hand: ranks of [1,2,2,3] are [1, 2.5, 2.5, 4]; ranks of
        # [1,2,3,4] are [1,2,3,4]. cov=4.5, var_a=4.5, var_b=5.0 ->
        # rho = 4.5 / sqrt(22.5) = 0.9486832...
        rho = spearman_rho([1, 2, 2, 3], [1, 2, 3, 4])
        assert rho == pytest.approx(0.94868, abs=1e-4)

    def test_single_point_returns_zero_not_an_error(self) -> None:
        assert spearman_rho([1], [1]) == 0.0

    def test_constant_series_returns_zero(self) -> None:
        """Zero variance makes correlation mathematically undefined; 0.0 is a
        documented fallback, not a claim that the series are uncorrelated."""
        assert spearman_rho([2, 2, 2], [1, 2, 3]) == 0.0

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            spearman_rho([1, 2], [1, 2, 3])


class TestValidate:
    def test_empty_input_is_not_passed(self) -> None:
        result = validate([], {})
        assert result.n == 0
        assert result.passed is False

    def test_turns_without_human_labels_are_excluded(self) -> None:
        turns = [_turn("a", None), _turn("b", {"level_appropriateness": 3})]
        scores = {
            "a": RubricScore("a", {"level_appropriateness": 4}, 1, "mock"),
            "b": RubricScore("b", {"level_appropriateness": 3}, 1, "mock"),
        }
        result = validate(turns, scores)
        assert result.n == 1  # only "b" has human labels

    def test_perfect_agreement_yields_rho_one_and_full_exact_agreement(self) -> None:
        turns = [
            _turn("a", {"level_appropriateness": 1, "task_progression": 2}),
            _turn("b", {"level_appropriateness": 3, "task_progression": 4}),
            _turn("c", {"level_appropriateness": 2, "task_progression": 3}),
        ]
        scores = {
            "a": RubricScore("a", {"level_appropriateness": 1, "task_progression": 2}, 1, "mock"),
            "b": RubricScore("b", {"level_appropriateness": 3, "task_progression": 4}, 1, "mock"),
            "c": RubricScore("c", {"level_appropriateness": 2, "task_progression": 3}, 1, "mock"),
        }
        result = validate(turns, scores)
        assert result.composite_rho == pytest.approx(1.0)
        assert result.exact_agreement_rate == 1.0
        assert result.passed is True

    def test_disagreement_fails_threshold(self) -> None:
        turns = [
            _turn("a", {"level_appropriateness": 4}),
            _turn("b", {"level_appropriateness": 1}),
            _turn("c", {"level_appropriateness": 3}),
            _turn("d", {"level_appropriateness": 2}),
        ]
        scores = {
            "a": RubricScore("a", {"level_appropriateness": 1}, 1, "mock"),
            "b": RubricScore("b", {"level_appropriateness": 4}, 1, "mock"),
            "c": RubricScore("c", {"level_appropriateness": 2}, 1, "mock"),
            "d": RubricScore("d", {"level_appropriateness": 3}, 1, "mock"),
        }
        result = validate(turns, scores)
        assert result.composite_rho < 0  # inverted agreement
        assert result.passed is False

    def test_missing_judge_score_for_a_labeled_turn_is_skipped(self) -> None:
        turns = [_turn("a", {"level_appropriateness": 3}), _turn("b", {"level_appropriateness": 2})]
        scores = {"a": RubricScore("a", {"level_appropriateness": 3}, 1, "mock")}  # no "b"
        result = validate(turns, scores)
        assert result.n == 1

    def test_per_dimension_rho_reported_separately(self) -> None:
        turns = [
            _turn("a", {"level_appropriateness": 1, "groundedness_safety": 4}),
            _turn("b", {"level_appropriateness": 4, "groundedness_safety": 1}),
        ]
        scores = {
            "a": RubricScore(
                "a", {"level_appropriateness": 1, "groundedness_safety": 1}, 1, "mock"
            ),
            "b": RubricScore(
                "b", {"level_appropriateness": 4, "groundedness_safety": 4}, 1, "mock"
            ),
        }
        result = validate(turns, scores)
        assert result.per_dimension_rho["level_appropriateness"] == pytest.approx(1.0)
        assert result.per_dimension_rho["groundedness_safety"] == pytest.approx(-1.0)
