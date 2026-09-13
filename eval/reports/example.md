<!--
  Static example committed to the repo so a reviewer can see the harness's
  output without cloning and running it. Frozen at generation time -- it is
  NOT regenerated automatically. Run `python -m eval.report` for a live one
  (written to eval/reports/latest.md, which is gitignored). See eval/README.md
  for what this run does and does not prove -- in particular, the mock model
  used here is deliberately restricted to curated-wordlist-safe replies, and
  judge validation was not run (no fabricated correlation number below).
-->

# Eval Report

Generated: 2026-09-11T16:34:36+00:00
Model under test: `mock-llm`

## Deterministic checks (PRD EV-3)

| Pack | n | Vocab ceiling violation rate | Avg words/turn | Target vocab reference rate | Language leakage rate | Gate |
|---|---|---|---|---|---|---|
| fr_sle | 15 | 0.00% | 3.0 | 0.00% | 0.00% | PASS |
| zh_hsk | 15 | 0.00% | 3.0 | 0.00% | 0.00% | PASS |

## Latency replay (PRD EV-4)

n=30, p50=541.16ms, p95=637.48ms
Gate: PASS

## Judge validation (PRD EV-5)

**Not run.** The golden set has human-labeled turns, but this report was generated with a mock model and no live judge -- there is no real judge output to validate against. Run with a real judge LLM to produce this section honestly; do not fabricate a correlation number here.
