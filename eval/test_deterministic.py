from __future__ import annotations

from app.pedagogy.packs import load_builtin_pack

from eval.deterministic import compute_deterministic_metrics
from eval.schema import GeneratedReply, GoldenTurn


def _turn(**overrides: object) -> GoldenTurn:
    defaults: dict[str, object] = dict(
        id="t1", pack="zh_hsk", level="HSK1", scenario="ordering_lunch",
        learner_utterance="我要米饭。",
    )
    defaults.update(overrides)
    return GoldenTurn(**defaults)  # type: ignore[arg-type]


class TestDeterministicMetricsZhHsk:
    def test_empty_input_returns_all_zeros(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        report = compute_deterministic_metrics([], pack)
        assert report.n == 0
        assert report.vocabulary_ceiling_violation_rate == 0.0

    def test_clean_reply_has_zero_ceiling_violations(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        replies = [GeneratedReply(turn=_turn(), reply_text="你好，我很高兴")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.vocabulary_ceiling_violation_rate == 0.0

    def test_out_of_ceiling_reply_is_flagged(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        replies = [GeneratedReply(turn=_turn(), reply_text="我们要互相尊重")]  # HSK4 word
        report = compute_deterministic_metrics(replies, pack)
        assert report.vocabulary_ceiling_violation_rate > 0.0

    def test_target_vocabulary_reference_detected(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        turn = _turn(level="HSK2")  # ordering_lunch target vocab includes 米饭
        replies = [GeneratedReply(turn=turn, reply_text="好的，米饭很好吃")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.target_vocabulary_reference_rate == 1.0

    def test_target_vocabulary_reference_zero_when_absent(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        turn = _turn(level="HSK2")
        replies = [GeneratedReply(turn=turn, reply_text="你好")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.target_vocabulary_reference_rate == 0.0

    def test_language_leakage_flagged_when_l1_disallowed(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        turn = _turn(level="HSK3")  # HSK3 disallows L1 scaffolding
        replies = [GeneratedReply(turn=turn, reply_text="Hello, 你好")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.language_leakage_rate == 1.0

    def test_language_leakage_not_flagged_when_l1_allowed(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        turn = _turn(level="HSK1")  # HSK1 allows L1 scaffolding
        replies = [GeneratedReply(turn=turn, reply_text="Hello, 你好")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.language_leakage_rate == 0.0

    def test_avg_agent_words_uses_jieba_not_naive_split(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        replies = [GeneratedReply(turn=_turn(), reply_text="我们去吃午饭吧")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.avg_agent_words_per_turn > 1  # jieba segments this into several tokens

    def test_aggregates_across_multiple_replies(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        replies = [
            GeneratedReply(turn=_turn(id="a"), reply_text="你好"),
            GeneratedReply(turn=_turn(id="b"), reply_text="我们要互相尊重"),
        ]
        report = compute_deterministic_metrics(replies, pack)
        assert report.n == 2
        assert report.vocabulary_ceiling_violation_rate > 0.0  # from the second reply only


class TestDeterministicMetricsFrSle:
    def test_leakage_heuristic_catches_common_english_markers(self) -> None:
        pack = load_builtin_pack("fr_sle")
        turn = _turn(pack="fr_sle", level="B", scenario="ordering_lunch")  # B disallows L1
        replies = [GeneratedReply(turn=turn, reply_text="Hello, comment allez-vous?")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.language_leakage_rate == 1.0

    def test_clean_french_reply_not_flagged(self) -> None:
        pack = load_builtin_pack("fr_sle")
        turn = _turn(pack="fr_sle", level="B", scenario="ordering_lunch")
        replies = [GeneratedReply(turn=turn, reply_text="Bonjour, comment allez-vous?")]
        report = compute_deterministic_metrics(replies, pack)
        assert report.language_leakage_rate == 0.0
