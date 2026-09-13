from __future__ import annotations

import pytest
from app.providers.mock import LatencyProfile, MockLLM

from eval.judge import JudgeParseError, build_judge_prompt, parse_judge_response, run_judge
from eval.rubric import load_rubric
from eval.schema import GoldenTurn

RUBRIC = load_rubric("pedagogical_v1")


def _turn() -> GoldenTurn:
    return GoldenTurn(
        id="t1", pack="zh_hsk", level="HSK1", scenario="ordering_lunch",
        learner_utterance="我要米饭。", history=(("assistant", "你好！你想吃什么？"),),
    )


def _valid_response() -> str:
    return (
        '{"level_appropriateness": 4, "corrective_feedback_quality": 3, '
        '"task_progression": 4, "conversational_naturalness": 3, '
        '"language_persona_fidelity": 4, "groundedness_safety": 4}'
    )


class TestBuildJudgePrompt:
    def test_includes_all_rubric_dimensions(self) -> None:
        prompt = build_judge_prompt(RUBRIC, _turn(), "好的！")
        for dim in RUBRIC.dimension_ids:
            assert dim in prompt

    def test_includes_turn_context_and_reply(self) -> None:
        prompt = build_judge_prompt(RUBRIC, _turn(), "好的，米饭很好吃！")
        assert "HSK1" in prompt
        assert "你好！你想吃什么？" in prompt
        assert "我要米饭。" in prompt
        assert "好的，米饭很好吃！" in prompt


class TestParseJudgeResponse:
    def test_parses_valid_json(self) -> None:
        score = parse_judge_response(_valid_response(), RUBRIC, "t1", "mock-judge")
        assert score.turn_id == "t1"
        assert score.scores["level_appropriateness"] == 4
        assert score.judge_model == "mock-judge"
        assert score.rubric_version == RUBRIC.version

    def test_strips_markdown_code_fence(self) -> None:
        fenced = f"```json\n{_valid_response()}\n```"
        score = parse_judge_response(fenced, RUBRIC, "t1", "mock-judge")
        assert score.scores["level_appropriateness"] == 4

    def test_strips_bare_code_fence_without_language_tag(self) -> None:
        fenced = f"```\n{_valid_response()}\n```"
        score = parse_judge_response(fenced, RUBRIC, "t1", "mock-judge")
        assert score.scores["level_appropriateness"] == 4

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(JudgeParseError, match="not valid JSON"):
            parse_judge_response("not json at all", RUBRIC, "t1", "mock-judge")

    def test_raises_on_non_object_json(self) -> None:
        with pytest.raises(JudgeParseError, match="must be a JSON object"):
            parse_judge_response("[1, 2, 3]", RUBRIC, "t1", "mock-judge")

    def test_raises_on_missing_dimension(self) -> None:
        incomplete = '{"level_appropriateness": 4}'
        with pytest.raises(JudgeParseError, match="missing dimension"):
            parse_judge_response(incomplete, RUBRIC, "t1", "mock-judge")

    def test_raises_on_out_of_range_score(self) -> None:
        bad = _valid_response().replace('"level_appropriateness": 4', '"level_appropriateness": 9')
        with pytest.raises(JudgeParseError, match="out of range"):
            parse_judge_response(bad, RUBRIC, "t1", "mock-judge")

    def test_raises_on_non_integer_score(self) -> None:
        bad = _valid_response().replace(
            '"level_appropriateness": 4', '"level_appropriateness": "great"'
        )
        with pytest.raises(JudgeParseError, match="non-integer"):
            parse_judge_response(bad, RUBRIC, "t1", "mock-judge")


class TestRunJudge:
    async def test_end_to_end_with_mock_llm(self) -> None:
        def respond(_messages: object) -> str:
            return _valid_response()

        llm = MockLLM(responder=respond, ttft=LatencyProfile(0.0), inter_token=LatencyProfile(0.0))
        score = await run_judge(llm, RUBRIC, _turn(), "好的！")
        assert score.composite == pytest.approx(22 / 6)

    async def test_malformed_response_raises_judgeparseerror(self) -> None:
        def respond(_messages: object) -> str:
            return "I think this reply is pretty good, 4/5 stars."

        llm = MockLLM(responder=respond, ttft=LatencyProfile(0.0), inter_token=LatencyProfile(0.0))
        with pytest.raises(JudgeParseError):
            await run_judge(llm, RUBRIC, _turn(), "好的！")
