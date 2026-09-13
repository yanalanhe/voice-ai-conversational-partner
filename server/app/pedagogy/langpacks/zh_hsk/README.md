# zh_hsk language pack

English → Mandarin, calibrated to HSK proficiency levels 1–4.

## On the vocabulary lists

The files under `vocab/` are **curated demonstration wordlists** — a
representative sample of vocabulary at roughly the right difficulty band for
each HSK level, assembled from general knowledge of the HSK bands. They are
**not a verbatim reproduction of the official published HSK wordlists**,
which are copyrighted material maintained by Hanban/China's Ministry of
Education and not something to fabricate or misattribute in a public repo.

This matters for what the ceiling check (`app/pedagogy/ceiling.py`) actually
proves: the **mechanism** — cumulative per-level vocabulary membership testing
via `jieba` segmentation — is real and correct. The **specific word
boundaries** are an approximation. A production deployment should replace
these files with the licensed official lists (or a client-supplied curriculum
wordlist) without touching any code — that swap is exactly what this
architecture is for.

## Levels

HSK1 → HSK2 → HSK3 → HSK4, each cumulative over the ones before it.
`correction_strategy` shifts from `none` (HSK1–2, where interrupting flow to
correct grammar does more harm than good) to `recast` (HSK3–4, where the
learner can absorb an implicit correction without losing the thread).
