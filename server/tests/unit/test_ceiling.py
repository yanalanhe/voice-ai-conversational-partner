from __future__ import annotations

from app.pedagogy.ceiling import check_ceiling, tokenize
from app.pedagogy.models import CorrectionStrategy, LevelPolicy, Tokenizer


def _level(ceiling: frozenset[str], tokenizer_unused: object = None) -> LevelPolicy:
    return LevelPolicy(
        code="TEST",
        level_model="test",
        vocabulary_ceiling=ceiling,
        max_sentence_words=20,
        speaking_rate=1.0,
        correction_strategy=CorrectionStrategy.NONE,
        l1_scaffolding_allowed=True,
        target_agent_turn_words=20,
    )


class TestWhitespaceTokenizer:
    def test_lowercases_and_strips_punctuation(self) -> None:
        assert tokenize("Bonjour, ça va?", Tokenizer.WHITESPACE) == ["bonjour", "ça", "va"]

    def test_keeps_accents(self) -> None:
        tokens = tokenize("élève", Tokenizer.WHITESPACE)
        assert tokens == ["élève"]
        assert "eleve" not in tokens


class TestJiebaTokenizer:
    def test_segments_known_words(self) -> None:
        tokens = tokenize("你好世界", Tokenizer.JIEBA)
        assert tokens == ["你好", "世界"]

    def test_strips_cjk_punctuation(self) -> None:
        tokens = tokenize("你好。世界！", Tokenizer.JIEBA)
        assert "。" not in tokens
        assert "！" not in tokens


class TestCeilingCheck:
    def test_passes_when_every_word_is_in_ceiling(self) -> None:
        level = _level(frozenset({"hello", "world"}))
        result = check_ceiling("hello world", level, Tokenizer.WHITESPACE)
        assert result.passed
        assert result.violation_count == 0

    def test_flags_words_outside_ceiling(self) -> None:
        level = _level(frozenset({"hello"}))
        result = check_ceiling("hello world", level, Tokenizer.WHITESPACE)
        assert not result.passed
        assert result.violations == ("world",)
        assert result.violation_rate == 0.5

    def test_empty_ceiling_always_passes(self) -> None:
        level = _level(frozenset())
        result = check_ceiling("anything goes here", level, Tokenizer.WHITESPACE)
        assert result.passed

    def test_apostrophe_word_in_ceiling_matches_text_with_apostrophe(self) -> None:
        """Regression test: the vocab file stores "aujourd'hui" verbatim, but
        tokenizing running text strips the apostrophe to "aujourdhui". Both
        sides of the comparison must go through the same normalization or
        this legitimate word is flagged as a violation every time."""
        level = _level(frozenset({"aujourd'hui", "il", "fait", "beau"}))
        result = check_ceiling("Aujourd'hui il fait beau", level, Tokenizer.WHITESPACE)
        assert result.passed, result.violations

    def test_hyphenated_word_in_ceiling_matches_text(self) -> None:
        level = _level(frozenset({"rendez-vous", "demain"}))
        result = check_ceiling("rendez-vous demain", level, Tokenizer.WHITESPACE)
        assert result.passed, result.violations

    def test_jieba_ceiling_flags_out_of_list_word(self) -> None:
        level = _level(frozenset({"你好"}))
        result = check_ceiling("你好世界", level, Tokenizer.JIEBA)
        assert not result.passed
        assert "世界" in result.violations

    def test_violation_rate_is_zero_for_empty_text(self) -> None:
        level = _level(frozenset({"hello"}))
        result = check_ceiling("", level, Tokenizer.WHITESPACE)
        assert result.violation_rate == 0.0
        assert result.passed
