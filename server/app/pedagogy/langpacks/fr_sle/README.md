# fr_sle language pack

English → French, calibrated to Government of Canada Second Language
Evaluation (SLE) oral proficiency levels A/B/C.

## What this pack proves, and what it doesn't

This pack was **not built by someone who speaks French** — see the top-level
project README for why that's a deliberate, disclosed constraint rather than
a gap papered over. It exists to prove the language-pack architecture is
genuinely configuration, not code: everything here is data (`language.yaml`,
`levels/*.yaml`, `vocab/*.txt`, `scenarios/*.yaml`), and adding it required
zero changes to `app/pedagogy/`, `app/pipeline/`, or `app/session/`.

**Unlike `zh_hsk`, this pack's outputs are not human-validated.** There is no
one on this project who can judge whether the French agent turns are actually
level-appropriate or grammatically sound. Its evaluation report is marked
accordingly (see `eval/EVALUATION.md` once the harness lands) — a judge score
with no ground truth behind it is a number, not a validated metric, and
presenting it as more than that would be dishonest.

## On the vocabulary lists

SLE is a *proficiency scale*, not a vocabulary-list standard the way HSK is —
there is no official "SLE wordlist" to approximate in the first place. The
files under `vocab/` are a small, informally curated set of common French
words at roughly the right difficulty band per level, good enough to exercise
the ceiling-check mechanism, not to certify pedagogical accuracy.
