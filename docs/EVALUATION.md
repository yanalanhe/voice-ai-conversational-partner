# Evaluation

Full detail, including the honesty notes that matter before citing any number from this
harness, lives in [`eval/README.md`](../eval/README.md). This page is a short pointer for
anyone browsing `docs/`.

## What exists

- A 30-turn held-out golden set (`eval/datasets/golden_turns.jsonl`) covering every level and
  scenario in both language packs — a starter set toward the PRD's ≥50-turn target, not a
  claim of completeness.
- Deterministic checks (vocabulary ceiling, words/turn, target-vocabulary reference, language
  leakage) that run with no LLM at all — pure text analysis reusing the same
  `app/pedagogy/ceiling.py` code the live pedagogy layer uses.
- An LLM-judge rubric (`eval/rubrics/pedagogical_v1.yaml`) and scorer (`eval/judge.py`) that
  accept any `LLMProvider` — mock in CI. `AzureLLM` satisfies the same contract, but it has
  not been pointed at the golden set yet.
- Judge-validation statistics (`eval/validate_judge.py`) — Spearman correlation between judge
  scores and human labels, with hand-verified reference values in its own test file.
- Reproducible, seeded latency replay (`eval/latency_replay.py`) against the real cascaded
  pipeline.
- CI quality gates (`eval/gates.py`) enforcing the thresholds in this project's PRD Sec 6.3.

## What has not been done, and why that matters

**Judge validation has not actually been run.** The golden set carries illustrative
placeholder human labels on 8 `zh_hsk` turns, written to prove the correlation math is
correct — not genuine human judgment. `eval/report.py` reports this section as "not run"
rather than computing and presenting a fabricated correlation number. A real validation
needs a live judge LLM plus a human who can actually read Mandarin reviewing the same replies
independently.

**No real model has been scored.** Azure OpenAI is now wired up for the English `generic`
demo, but nothing has been run through the golden set with it. Every number in
`eval/reports/example.md` comes from a scripted mock model deliberately restricted to
wordlist-safe replies, which demonstrates the harness's wiring, not a real model's
pedagogical quality. Scoring a real model on the Mandarin golden turns also needs the Azure
adapters wired into the pedagogy path, which is not done yet.

Run it yourself:

```
python -m eval.report
pytest eval/
```
