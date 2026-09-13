from __future__ import annotations

from app.providers.mock import LatencyProfile, MockLLM, scripted_tutor
from app.providers.types import Role

from eval.generate import generate_all, generate_reply
from eval.schema import GoldenTurn


def _turn(**overrides: object) -> GoldenTurn:
    defaults: dict[str, object] = dict(
        id="t1", pack="zh_hsk", level="HSK1", scenario="ordering_lunch",
        learner_utterance="我要米饭。",
    )
    defaults.update(overrides)
    return GoldenTurn(**defaults)  # type: ignore[arg-type]


def _fast_llm(reply: str) -> MockLLM:
    return MockLLM(
        responder=scripted_tutor([reply]), ttft=LatencyProfile(0.0),
        inter_token=LatencyProfile(0.0),
    )


class TestGenerateReply:
    async def test_returns_generated_reply_with_llm_output(self) -> None:
        llm = _fast_llm("好的！")
        result = await generate_reply(llm, _turn())
        assert result.turn.id == "t1"
        assert "好的" in result.reply_text

    async def test_system_prompt_reflects_pack_and_level(self) -> None:
        llm = _fast_llm("好的！")
        await generate_reply(llm, _turn())
        system_msg = llm.calls[0][0]
        assert system_msg.role is Role.SYSTEM
        assert "zh-CN" in system_msg.content
        assert "HSK1" in system_msg.content

    async def test_history_is_included_before_learner_utterance(self) -> None:
        llm = _fast_llm("好的！")
        turn = _turn(history=(("assistant", "你好！我们去吃午饭吧。"),))
        await generate_reply(llm, turn)
        messages = llm.calls[0]
        contents = [m.content for m in messages]
        assert "你好！我们去吃午饭吧。" in contents
        assert contents[-1] == "我要米饭。"
        assert messages[-1].role is Role.USER

    async def test_works_for_fr_sle_pack(self) -> None:
        llm = _fast_llm("Bonjour!")
        turn = _turn(
            pack="fr_sle", level="A", scenario="ordering_lunch", learner_utterance="Bonjour"
        )
        result = await generate_reply(llm, turn)
        assert "Bonjour" in result.reply_text


class TestGenerateAll:
    async def test_produces_one_reply_per_turn_in_order(self) -> None:
        llm = _fast_llm("好的！")
        turns = [_turn(id="a"), _turn(id="b"), _turn(id="c")]
        results = await generate_all(llm, turns)
        assert [r.turn.id for r in results] == ["a", "b", "c"]

    async def test_empty_turns_produces_empty_list(self) -> None:
        llm = _fast_llm("好的！")
        assert await generate_all(llm, []) == []
