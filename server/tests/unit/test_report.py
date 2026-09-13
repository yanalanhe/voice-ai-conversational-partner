from __future__ import annotations

from app.pedagogy.packs import load_builtin_pack
from app.providers.types import Message, Role
from app.state.report import build_session_report


def _msgs(*pairs: tuple[Role, str]) -> list[Message]:
    return [Message(role=r, content=c) for r, c in pairs]


class TestSessionReportZhHsk:
    def test_counts_words_via_jieba_not_naive_split(self) -> None:
        """Regression guard: str.split() on Chinese text returns one token
        for a whole unbroken sentence, which would silently undercount every
        zh_hsk session. len(jieba.cut(...)) must be used instead."""
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")
        messages = _msgs((Role.USER, "我喜欢米饭"), (Role.ASSISTANT, "好，我们去吃饭吧"))

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        assert report.learner_word_count > 1  # jieba segments this into several tokens
        assert report.agent_word_count > 1

    def test_detects_ceiling_violation_in_agent_reply(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")
        # "尊重" (respect) is HSK4-only -- an HSK1 agent reply using it is a
        # real ceiling violation given the cumulative vocabulary design.
        messages = _msgs((Role.USER, "你好"), (Role.ASSISTANT, "我们要互相尊重"))

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        assert report.vocabulary_ceiling_violations > 0
        assert report.vocabulary_ceiling_violation_rate > 0

    def test_zero_violations_when_agent_stays_in_ceiling(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")
        messages = _msgs((Role.USER, "你好"), (Role.ASSISTANT, "你好，我很高兴"))

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        assert report.vocabulary_ceiling_violations == 0

    def test_target_vocabulary_used_and_missed_are_disjoint_and_complete(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK2")
        scenario = pack.scenario("ordering_lunch")  # target_vocabulary includes 米饭, 好吃, ...
        messages = _msgs((Role.USER, "我喜欢米饭"), (Role.ASSISTANT, "好，米饭很好吃"))

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        all_target = set(scenario.target_vocabulary)
        used = set(report.target_vocabulary_used)
        missed = set(report.target_vocabulary_missed)
        assert used | missed == all_target
        assert used & missed == set()
        assert "米饭" in used

    def test_talk_ratio_is_between_zero_and_one(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")
        messages = _msgs((Role.USER, "你好"), (Role.ASSISTANT, "你好，很高兴认识你"))

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        assert 0.0 <= report.talk_ratio <= 1.0

    def test_no_messages_produces_a_report_with_no_crash(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")

        report = build_session_report("alan", scenario, level, pack.tokenizer, [])

        assert report.turns == 0
        assert report.talk_ratio == 0.0
        assert report.vocabulary_ceiling_violation_rate == 0.0

    def test_next_steps_flags_high_violation_rate_first(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")
        messages = _msgs((Role.USER, "你好"), (Role.ASSISTANT, "尊重努力奋斗坚持"))  # all HSK4+

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        assert "review vocabulary" in report.next_steps.lower()

    def test_next_steps_suggests_missed_vocabulary_when_ceiling_is_clean(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")
        messages = _msgs((Role.USER, "你好"), (Role.ASSISTANT, "你好"))  # clean, no target vocab

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        assert report.vocabulary_ceiling_violations == 0
        assert "try to use" in report.next_steps.lower()


class TestSessionReportFrSle:
    def test_works_for_whitespace_tokenized_pack_too(self) -> None:
        pack = load_builtin_pack("fr_sle")
        level = pack.level("A")
        scenario = pack.scenario("ordering_lunch")
        messages = _msgs(
            (Role.USER, "Je voudrais manger"),
            (Role.ASSISTANT, "Bon, qu'est-ce que tu veux boire?"),
        )

        report = build_session_report("alan", scenario, level, pack.tokenizer, messages)

        assert report.learner_word_count == 3
        assert report.turns == 1
