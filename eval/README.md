# Evaluation harness

Everything here runs on mocks with zero credentials and zero API spend
(ADR-003) — `python -m eval.report` produces a full report from a clean
checkout with nothing configured. Swapping in a real model or judge is a
one-line change at the two call sites (`report.py`'s `_default_llm`, and
wherever a real judge gets wired into `eval.judge.run_judge`), not a
different code path.

## Layers

| Module | What it checks | Needs a real LLM? |
|---|---|---|
| `golden.py` | Loads `datasets/golden_turns.jsonl` | No |
| `generate.py` | Produces a fresh agent reply per golden turn via the real prompt-building path | Only for a real signal — mocks work for wiring tests |
| `deterministic.py` | Vocabulary ceiling, words/turn, target-vocabulary reference, language leakage | No — pure text analysis |
| `judge.py` | LLM-as-judge scoring against `rubrics/pedagogical_v1.yaml` | Only for a real signal |
| `validate_judge.py` | Spearman correlation between judge scores and human labels | No — pure statistics |
| `latency_replay.py` | Reproducible TTFA percentiles via seeded mock latency | No |
| `gates.py` | PRD Sec 6.3 threshold checks | No |
| `report.py` | Orchestrates all of the above into `reports/latest.md` | No, by default |

## Honesty notes — read before citing a number from this harness

**The golden set is a 30-turn starter set, not the PRD's ≥50-turn target.**
It covers every level and scenario in both packs, prioritizing breadth over
raw count. Extend `datasets/golden_turns.jsonl` before treating coverage
claims as complete.

**Judge validation (EV-5) has not been run.** The golden set carries
`human_labels` on 8 `zh_hsk` turns — illustrative placeholders written to
prove `validate_judge.py`'s Spearman-correlation math is correct (see its
test file for hand-verified reference values), not genuine human judgment.
`report.py` reports this section as "not run" rather than computing a
correlation against placeholder labels and presenting it as validated. A real
ρ requires: (1) a live judge LLM scoring real generated replies, and (2)
someone who can actually read Mandarin reviewing those same replies
independently. Do the second part yourself before citing a ρ value anywhere.

**`fr_sle` carries no human labels at all**, on purpose — see
`app/pedagogy/langpacks/fr_sle/README.md`. Its deterministic checks and judge
scores are real and computed the same way as `zh_hsk`'s; there is simply no
one on this project positioned to validate French output.

**The deterministic checks are only as good as the wordlists behind them.**
`zh_hsk`'s and `fr_sle`'s vocabulary files are curated demonstration subsets,
not the verbatim official HSK list or a licensed SLE standard (see each
pack's own README). A perfectly reasonable reply can fail the ceiling check
simply because a common word wasn't included in the demo list — that is a
wordlist-coverage limitation, not evidence the checking mechanism is wrong.
`report.py`'s default demo reply is deliberately restricted to words known to
be in the wordlists, so the default report shows a representative pass;
`test_gates.py::test_deliberately_bad_reply_fails_the_gate` is what proves
the gate actually fires when it should.

**The judge-score quality gates (`composite_judge_score`, `min_any_dimension`
in `gates.py`) are only a meaningful signal against a real judge scoring a
real model's output.** Against the default mock they would just be testing
the mock's own scripted reply. They are implemented as real, fully-tested
threshold logic regardless — see `test_gates.py`'s pure-logic test classes.

## Running it

```
python -m eval.report          # writes eval/reports/latest.md
pytest eval/                   # the harness's own test suite
```
