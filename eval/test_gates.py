"""Quality-gate tests (PRD EV-6).

Two layers, matching gates.py's own docstring:
1. Pure threshold-logic tests -- no LLM, no golden set, just arithmetic.
2. One end-to-end integration test proving golden set -> generate -> metrics
   -> gate check wires together correctly against a deliberately clean mock
   model. This is a wiring regression test, not a model-quality benchmark --
   see gates.py for why the judge-score gates need a real judge to mean
   anything.
"""

from __future__ import annotations

from app.pedagogy.packs import load_builtin_pack
from app.providers.mock import LatencyProfile, MockLLM

from eval.deterministic import DeterministicReport, compute_deterministic_metrics
from eval.gates import (
    DEFAULT_THRESHOLDS,
    check_deterministic_gates,
    check_judge_gates,
    check_latency_gate,
)
from eval.generate import generate_all
from eval.golden import load_golden_set
from eval.latency_replay import replay_turns


class TestDeterministicGateLogic:
    def test_passes_when_within_thresholds(self) -> None:
        report = DeterministicReport(
            n=10, vocabulary_ceiling_violation_rate=0.01, avg_agent_words_per_turn=8.0,
            target_vocabulary_reference_rate=0.5, language_leakage_rate=0.0,
        )
        gate = check_deterministic_gates(report)
        assert gate.passed

    def test_fails_when_ceiling_violation_rate_too_high(self) -> None:
        report = DeterministicReport(
            n=10, vocabulary_ceiling_violation_rate=0.10, avg_agent_words_per_turn=8.0,
            target_vocabulary_reference_rate=0.5, language_leakage_rate=0.0,
        )
        gate = check_deterministic_gates(report)
        assert not gate.passed
        assert gate.failures[0].name == "vocab_ceiling_violation_rate"

    def test_fails_when_leakage_rate_too_high(self) -> None:
        report = DeterministicReport(
            n=10, vocabulary_ceiling_violation_rate=0.0, avg_agent_words_per_turn=8.0,
            target_vocabulary_reference_rate=0.5, language_leakage_rate=0.05,
        )
        gate = check_deterministic_gates(report)
        assert not gate.passed

    def test_exactly_at_threshold_passes(self) -> None:
        report = DeterministicReport(
            n=10,
            vocabulary_ceiling_violation_rate=DEFAULT_THRESHOLDS.vocab_ceiling_violation_rate_max,
            avg_agent_words_per_turn=8.0, target_vocabulary_reference_rate=0.5,
            language_leakage_rate=0.0,
        )
        gate = check_deterministic_gates(report)
        assert gate.passed


class TestLatencyGateLogic:
    def test_passes_under_threshold(self) -> None:
        check = check_latency_gate(900.0)
        assert check.passed

    def test_fails_over_threshold(self) -> None:
        check = check_latency_gate(2000.0)
        assert not check.passed

    def test_exactly_at_threshold_passes(self) -> None:
        check = check_latency_gate(DEFAULT_THRESHOLDS.ttfa_p95_cascaded_replay_max_ms)
        assert check.passed


class TestJudgeGateLogic:
    def test_passes_with_good_scores(self) -> None:
        gate = check_judge_gates(composite_scores=[3.5, 3.8, 3.2], per_turn_min_scores=[3, 3, 3])
        assert gate.passed

    def test_fails_low_composite(self) -> None:
        gate = check_judge_gates(composite_scores=[2.0, 2.5], per_turn_min_scores=[3, 3])
        assert not gate.passed
        assert gate.failures[0].name == "composite_judge_score"

    def test_fails_low_minimum_dimension_even_with_good_composite(self) -> None:
        # A composite of 3.5 can hide one dimension scored 0 -- the min gate
        # exists specifically to catch that.
        gate = check_judge_gates(composite_scores=[3.5], per_turn_min_scores=[0])
        assert not gate.passed
        assert any(c.name == "min_any_dimension" for c in gate.failures)

    def test_empty_input_does_not_crash_and_fails_closed(self) -> None:
        gate = check_judge_gates(composite_scores=[], per_turn_min_scores=[])
        assert not gate.passed


class TestEndToEndWiring:
    """Golden set -> generate -> deterministic metrics -> gate, against a
    deliberately clean scripted model. Proves the pipeline is wired
    correctly; does not and cannot prove a real model would pass this."""

    async def test_clean_zh_hsk_replies_pass_the_deterministic_gate(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        turns = [t for t in load_golden_set() if t.pack == "zh_hsk"]

        def clean_reply(_messages: object) -> str:
            return "你好，很高兴。"  # safe HSK1 vocabulary, no ceiling violation possible

        llm = MockLLM(
            responder=clean_reply, ttft=LatencyProfile(0.0), inter_token=LatencyProfile(0.0)
        )
        replies = await generate_all(llm, turns)
        report = compute_deterministic_metrics(replies, pack)

        assert check_deterministic_gates(report).passed

    async def test_clean_fr_sle_replies_pass_the_deterministic_gate(self) -> None:
        pack = load_builtin_pack("fr_sle")
        turns = [t for t in load_golden_set() if t.pack == "fr_sle"]

        def clean_reply(_messages: object) -> str:
            return "Bonjour, très bien."  # no English marker words

        llm = MockLLM(
            responder=clean_reply, ttft=LatencyProfile(0.0), inter_token=LatencyProfile(0.0)
        )
        replies = await generate_all(llm, turns)
        report = compute_deterministic_metrics(replies, pack)

        assert check_deterministic_gates(report).passed

    async def test_deliberately_bad_reply_fails_the_gate(self) -> None:
        """The gate must actually fire -- a check that never fails has never
        been proven to check anything."""
        pack = load_builtin_pack("zh_hsk")
        turns = [t for t in load_golden_set() if t.pack == "zh_hsk"]

        def bad_reply(_messages: object) -> str:
            return "我们要互相尊重，坚持奋斗，追求卓越的品质。"  # dense HSK4 vocabulary

        llm = MockLLM(
            responder=bad_reply, ttft=LatencyProfile(0.0), inter_token=LatencyProfile(0.0)
        )
        replies = await generate_all(llm, turns)
        report = compute_deterministic_metrics(replies, pack)

        assert not check_deterministic_gates(report).passed

    async def test_latency_replay_passes_the_ttfa_gate(self) -> None:
        report = await replay_turns(n=10, seed=0)
        stats = report.stats()
        assert check_latency_gate(stats["p95"]).passed
