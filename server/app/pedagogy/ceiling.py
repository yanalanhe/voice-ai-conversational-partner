"""Deterministic vocabulary-ceiling check (PRD EV-3).

The one place tokenization strategy is chosen based on the pack's declared
`tokenizer` field -- never on a hardcoded language name. That distinction is
the whole point of PD-0: this module has no idea it is being used for Mandarin
or French, only that this particular pack asked for `jieba` or `whitespace`
segmentation.

For `zh_hsk`, this check is only as good as the wordlist in
langpacks/zh_hsk/vocab/ -- see that directory's README for the honest scope
of what is and is not the verbatim official HSK list.
"""

from __future__ import annotations

import re
import string
import unicodedata
from dataclasses import dataclass, field

from app.pedagogy.models import LevelPolicy, Tokenizer

_LATIN_PUNCT_TABLE = str.maketrans("", "", string.punctuation + "‘’“”…")


def _normalize_whitespace_word(word: str) -> str:
    """The single-word version of `_tokenize_whitespace`'s cleanup.

    Applied to BOTH sides of the ceiling comparison -- see `check_ceiling`.
    Without this, a vocab file entry like "aujourd'hui" would never match the
    "aujourdhui" produced by tokenizing running text, because the apostrophe
    is stripped from text but the wordlist was never put through the same
    transform. A silently-broken ceiling check would fail open (every word
    "unknown"), which is worse than the check not existing at all.
    """
    return unicodedata.normalize("NFC", word.lower()).translate(_LATIN_PUNCT_TABLE)


def _tokenize_whitespace(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace.

    Deliberately keeps accented letters intact (no ASCII-folding): "élève"
    and "eleve" are different words for ceiling purposes, and folding them
    would let the model dodge the ceiling by relying on the learner's level
    tolerating an accent-stripped near-miss that isn't actually in the list.
    """
    cleaned = _normalize_whitespace_word(text)
    return [tok for tok in cleaned.split() if tok]


def _tokenize_jieba(text: str) -> list[str]:
    import logging

    import jieba  # optional dependency (pyproject [zh] extra); only imported when used

    jieba.setLogLevel(logging.WARNING)  # silence "Building prefix dict..." on first call

    # CJK punctuation isn't in string.punctuation; strip it separately so
    # trailing 。！？ don't get segmented as part of the last word.
    cleaned = re.sub(r"[，。！？；：、「」『』（）《》]", " ", text)
    return [tok.strip() for tok in jieba.cut(cleaned) if tok.strip()]


def _identity(word: str) -> str:
    return word


_TOKENIZERS = {
    Tokenizer.WHITESPACE: _tokenize_whitespace,
    Tokenizer.JIEBA: _tokenize_jieba,
}

# How to normalize a single VOCAB FILE ENTRY so it compares equal to what
# `tokenize()` produces from running text. Identity for jieba -- a wordlist
# entry like "会议室" is already exactly the token jieba would produce.
_WORD_NORMALIZERS = {
    Tokenizer.WHITESPACE: _normalize_whitespace_word,
    Tokenizer.JIEBA: _identity,
}


def tokenize(text: str, tokenizer: Tokenizer) -> list[str]:
    return _TOKENIZERS[tokenizer](text)


@dataclass(frozen=True, slots=True)
class CeilingCheckResult:
    violations: tuple[str, ...] = field(default_factory=tuple)
    total_tokens: int = 0

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def violation_rate(self) -> float:
        """Matches the CI gate metric in PRD 6.3 (`vocab_ceiling_violation_rate`)."""
        if self.total_tokens == 0:
            return 0.0
        return self.violation_count / self.total_tokens

    @property
    def passed(self) -> bool:
        return self.violation_count == 0


def check_ceiling(text: str, level: LevelPolicy, tokenizer: Tokenizer) -> CeilingCheckResult:
    """Check whether `text` stays within `level`'s vocabulary ceiling.

    An empty ceiling (a pack that ships no wordlist for a level) means the
    check is not enforced for that level and always passes -- this is a
    deliberate opt-out, not a silent failure, so a pack author who forgets a
    vocab file gets a `PackLoadError` at load time (packs.py), not a
    permanently-passing ceiling check at runtime.
    """
    tokens = tokenize(text, tokenizer)
    if not level.vocabulary_ceiling:
        return CeilingCheckResult(violations=(), total_tokens=len(tokens))
    normalize_word = _WORD_NORMALIZERS[tokenizer]
    ceiling = {normalize_word(w) for w in level.vocabulary_ceiling}
    violations = tuple(t for t in tokens if t not in ceiling)
    return CeilingCheckResult(violations=violations, total_tokens=len(tokens))
