"""Assembles one full eval run into a Markdown report (PRD EV-8).

Running this script costs nothing and needs no credentials: the default
model and judge are mocks (ADR-003). Swapping in a real model or judge is a
one-line change to `_default_llm`/`_default_judge` below -- everything else
here is agnostic to which `LLMProvider` it was handed, mock or real.

    python -m eval.report

writes `eval/reports/latest.md`.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.pedagogy.models import LanguagePack
from app.pedagogy.packs import load_builtin_pack
from app.providers.mock import LatencyProfile, MockLLM
from app.providers.protocols import LLMProvider

from eval.deterministic import DeterministicReport, compute_deterministic_metrics
from eval.gates import check_deterministic_gates, check_latency_gate
from eval.generate import generate_all
from eval.golden import load_golden_set, turns_with_human_labels
from eval.latency_replay import replay_turns
from eval.schema import GoldenTurn
from eval.validate_judge import JudgeValidationResult

REPORTS_ROOT = Path(__file__).parent / "reports"


@dataclass(frozen=True, slots=True)
class PackEvalResult:
    pack_name: str
    n_turns: int
    deterministic: DeterministicReport
    gate_passed: bool


@dataclass(frozen=True, slots=True)
class EvalRunResult:
    generated_at: str
    llm_model_name: str
    packs: tuple[PackEvalResult, ...]
    latency_stats: dict[str, float | int]
    latency_gate_passed: bool
    judge_validation: JudgeValidationResult | None
    judge_validation_is_placeholder: bool


def _default_llm() -> LLMProvider:
    """A deterministic scripted mock, deliberately restricted to words
    present in both packs' level-1/A demo wordlists (see langpacks/*/README.md
    for why those lists are small curated subsets, not the real official
    lists). This keeps the DEFAULT report demonstrating the harness's output
    format on a representative pass, rather than re-litigating wordlist
    completeness -- that gap is exercised on purpose by
    test_gates.py::test_deliberately_bad_reply_fails_the_gate. Replace with a
    real adapter to get a real quality signal instead of a demo one."""

    def respond(messages: object) -> str:
        system = messages[0].content if messages else ""  # type: ignore[index]
        if "zh-CN" in system:
            return "你好，很高兴。"
        return "Bonjour, très bien."

    return MockLLM(responder=respond, ttft=LatencyProfile(0.0), inter_token=LatencyProfile(0.0))


async def _eval_pack(
    pack: LanguagePack, turns: list[GoldenTurn], llm: LLMProvider
) -> PackEvalResult:
    replies = await generate_all(llm, turns)
    report = compute_deterministic_metrics(replies, pack)
    gate = check_deterministic_gates(report)
    return PackEvalResult(
        pack_name=pack.name, n_turns=len(turns), deterministic=report, gate_passed=gate.passed
    )


async def run_full_eval(
    llm: LLMProvider | None = None,
    golden_path: str | Path | None = None,
    latency_replay_n: int = 30,
) -> EvalRunResult:
    """`latency_replay_n` defaults to 30 for a real report run. Tests pass a
    smaller value -- MockLLM/MockTTS simulate latency with real
    `asyncio.sleep()` calls (see mock.py's ADR-003 discussion), so each
    replayed turn costs genuine wall-clock time; the exact count barely
    changes what a smoke test proves."""
    llm = llm or _default_llm()
    all_turns = load_golden_set(golden_path)

    pack_results = []
    for pack_name in sorted({t.pack for t in all_turns}):
        pack = load_builtin_pack(pack_name)
        turns = [t for t in all_turns if t.pack == pack_name]
        pack_results.append(await _eval_pack(pack, turns, llm))

    latency_report = await replay_turns(n=latency_replay_n, seed=0)
    latency_stats = latency_report.stats()
    latency_gate_passed = (
        check_latency_gate(latency_stats["p95"]).passed if latency_stats.get("n") else False
    )

    labeled = turns_with_human_labels(all_turns)
    # Judge validation needs a live judge scoring these exact turns to mean
    # anything -- with the default mock LLM there is no real signal to
    # validate against, so it is reported as absent, not faked.
    judge_validation = None
    judge_is_placeholder = bool(labeled)

    return EvalRunResult(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        llm_model_name=llm.name,
        packs=tuple(pack_results),
        latency_stats=latency_stats,
        latency_gate_passed=latency_gate_passed,
        judge_validation=judge_validation,
        judge_validation_is_placeholder=judge_is_placeholder,
    )


def render_markdown(result: EvalRunResult) -> str:
    lines = [
        "# Eval Report",
        "",
        f"Generated: {result.generated_at}",
        f"Model under test: `{result.llm_model_name}`",
        "",
        "## Deterministic checks (PRD EV-3)",
        "",
        "| Pack | n | Vocab ceiling violation rate | Avg words/turn | "
        "Target vocab reference rate | Language leakage rate | Gate |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in result.packs:
        d = p.deterministic
        gate_mark = "PASS" if p.gate_passed else "FAIL"
        lines.append(
            f"| {p.pack_name} | {p.n_turns} | {d.vocabulary_ceiling_violation_rate:.2%} | "
            f"{d.avg_agent_words_per_turn:.1f} | {d.target_vocabulary_reference_rate:.2%} | "
            f"{d.language_leakage_rate:.2%} | {gate_mark} |"
        )

    lines += [
        "",
        "## Latency replay (PRD EV-4)",
        "",
        f"n={result.latency_stats.get('n', 0)}, "
        f"p50={result.latency_stats.get('p50', '--')}ms, "
        f"p95={result.latency_stats.get('p95', '--')}ms",
        f"Gate: {'PASS' if result.latency_gate_passed else 'FAIL'}",
        "",
        "## Judge validation (PRD EV-5)",
        "",
    ]
    if result.judge_validation is not None:
        v = result.judge_validation
        lines.append(f"n={v.n}, composite rho={v.composite_rho}, passed={v.passed}")
    elif result.judge_validation_is_placeholder:
        lines.append(
            "**Not run.** The golden set has human-labeled turns, but this report was "
            "generated with a mock model and no live judge -- there is no real judge "
            "output to validate against. Run with a real judge LLM to produce this "
            "section honestly; do not fabricate a correlation number here."
        )
    else:
        lines.append("No human-labeled turns in the golden set.")

    return "\n".join(lines) + "\n"


def main() -> None:
    result = asyncio.run(run_full_eval())
    markdown = render_markdown(result)
    REPORTS_ROOT.mkdir(exist_ok=True)
    out_path = REPORTS_ROOT / "latest.md"
    out_path.write_text(markdown, encoding="utf-8")
    sys.stdout.write(markdown)
    sys.stdout.write(f"\nWritten to {out_path}\n")


if __name__ == "__main__":
    main()
