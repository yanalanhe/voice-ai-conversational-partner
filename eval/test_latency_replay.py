from __future__ import annotations

import pytest

from eval.latency_replay import replay_turns


class TestReplayTurns:
    """n is kept small (5-8) in every test here on purpose: MockLLM/MockTTS
    simulate latency with real `asyncio.sleep()` calls (that is the whole
    point -- see mock.py's ADR-003 discussion), so each replayed turn costs
    genuine wall-clock time (~0.5s). A larger n belongs in the actual CI
    quality-gate run (see test_quality_gates.py), not in every unit test that
    merely checks this module's arithmetic."""

    async def test_produces_one_sample_per_turn(self) -> None:
        report = await replay_turns(n=5, seed=0)
        assert report.stats()["n"] == 5

    async def test_p50_is_less_than_or_equal_to_p95(self) -> None:
        report = await replay_turns(n=8, seed=0)
        stats = report.stats()
        assert stats["p50"] <= stats["p95"]

    async def test_same_seed_is_deterministic_within_scheduler_jitter(self) -> None:
        """"Seeded" controls the REQUESTED sleep durations, which are drawn
        from the same random values on both runs -- but `asyncio.sleep(x)` is
        a lower bound, not an exact wait, so the OBSERVED wall-clock timing
        (perf_counter deltas) still carries a few ms of real event-loop
        scheduling jitter even when every requested delay was identical.
        Exact equality genuinely does not hold here; this asserts the
        tolerance that does."""
        a = await replay_turns(n=5, seed=42)
        b = await replay_turns(n=5, seed=42)
        a_stats, b_stats = a.stats(), b.stats()
        assert a_stats["n"] == b_stats["n"]
        assert a_stats["p50"] == pytest.approx(b_stats["p50"], rel=0.05)
        assert a_stats["p95"] == pytest.approx(b_stats["p95"], rel=0.05)

    async def test_different_seed_can_produce_different_stats(self) -> None:
        a = await replay_turns(n=5, seed=1)
        b = await replay_turns(n=5, seed=2)
        # Not a strict requirement that they differ, but with real jitter in
        # the modelled distributions they should essentially never collide.
        assert a.samples != b.samples

    async def test_stats_are_within_a_sane_bound_for_the_modelled_profile(self) -> None:
        report = await replay_turns(n=6, seed=0)
        stats = report.stats()
        # Generous bound -- this is a sanity check against a broken profile
        # (e.g. an accidental 10x unit error), not a tight regression gate.
        assert stats["p95"] < 3000
        assert stats["p50"] > 0

    async def test_zero_turns_returns_empty_stats(self) -> None:
        report = await replay_turns(n=0)
        assert report.stats() == {"n": 0}
