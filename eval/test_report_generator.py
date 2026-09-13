"""Smoke tests for eval/report.py.

Deliberately light: every constituent piece (deterministic metrics, latency
replay, gate logic) already has its own thorough test file. This file only
proves the orchestration wires together and produces well-formed output.

All tests share one `run_full_eval()` call via the `result` fixture --
MockLLM/MockTTS simulate latency with real `asyncio.sleep()` calls, so
running it six times (once per assertion) would cost six times the wall
clock for zero extra coverage.
"""

from __future__ import annotations

import pytest

from eval.report import EvalRunResult, render_markdown, run_full_eval


@pytest.fixture
async def result() -> EvalRunResult:
    return await run_full_eval(latency_replay_n=5)


class TestRunFullEval:
    async def test_runs_end_to_end_with_default_mock(self, result: EvalRunResult) -> None:
        pack_names = {p.pack_name for p in result.packs}
        assert pack_names == {"zh_hsk", "fr_sle"}

    async def test_default_mock_reply_passes_the_deterministic_gate(
        self, result: EvalRunResult
    ) -> None:
        """The default report demo reply is deliberately restricted to
        curated-wordlist-safe words -- see report.py's _default_llm
        docstring for why a FAIL here would be a wordlist-coverage artifact,
        not a real quality signal."""
        assert all(p.gate_passed for p in result.packs)

    async def test_latency_stats_are_present(self, result: EvalRunResult) -> None:
        assert result.latency_stats["n"] == 5
        assert result.latency_gate_passed is True

    async def test_judge_validation_is_marked_placeholder_not_fabricated(
        self, result: EvalRunResult
    ) -> None:
        """The golden set has human-labeled turns but this run used the
        default mock with no live judge -- the report must say so plainly,
        never synthesize a correlation number it didn't actually compute."""
        assert result.judge_validation is None
        assert result.judge_validation_is_placeholder is True


class TestRenderMarkdown:
    def test_produces_all_expected_sections(self, result: EvalRunResult) -> None:
        markdown = render_markdown(result)
        assert "# Eval Report" in markdown
        assert "## Deterministic checks" in markdown
        assert "## Latency replay" in markdown
        assert "## Judge validation" in markdown

    def test_does_not_fabricate_a_judge_correlation_number(self, result: EvalRunResult) -> None:
        markdown = render_markdown(result)
        assert "**Not run.**" in markdown
        assert "do not fabricate" in markdown.lower()

    def test_includes_both_pack_rows(self, result: EvalRunResult) -> None:
        markdown = render_markdown(result)
        assert "| zh_hsk |" in markdown
        assert "| fr_sle |" in markdown
