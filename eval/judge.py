"""The LLM judge itself (PRD EV-2).

Takes any `LLMProvider` -- the same protocol the cascaded pipeline uses for
the model under test -- so a mock judge (used in CI, zero cost, ADR-003) and
a real judge (Azure OpenAI, Gemini) are interchangeable with no code change,
only a different provider passed in at the call site.

Temperature is forced to 0: a judge that isn't deterministic makes "did this
PR cause a regression" indistinguishable from "the judge rolled differently
this time," which defeats the entire point of a CI quality gate.
"""

from __future__ import annotations

import json

from app.providers.protocols import LLMProvider
from app.providers.types import LLMConfig, Message, Role

from eval.rubric import Rubric
from eval.schema import GoldenTurn, RubricScore


class JudgeParseError(Exception):
    """The judge's response could not be parsed into a valid score set."""


def build_judge_prompt(rubric: Rubric, turn: GoldenTurn, reply_text: str) -> str:
    lines = [
        "You are scoring a language-tutoring AI's reply for pedagogical quality.",
        f"Learner proficiency level: {turn.level} ({turn.pack})",
        f"Scenario: {turn.scenario}",
        "",
        "Conversation so far:",
    ]
    for role, content in turn.history:
        lines.append(f"{role}: {content}")
    lines.append(f"learner: {turn.learner_utterance}")
    lines.append(f"assistant (SCORE THIS REPLY): {reply_text}")
    lines.append("")
    lines.append(
        f"Score each dimension on a {rubric.scale} scale, where 0 is very poor and 4 is "
        "excellent. Respond with ONLY a JSON object mapping each dimension id to an "
        "integer score -- no prose, no markdown fences."
    )
    for d in rubric.dimensions:
        lines.append(f"- {d.id}: {d.question}")
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.strip("`").strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    return cleaned


def parse_judge_response(
    text: str, rubric: Rubric, turn_id: str, judge_model: str
) -> RubricScore:
    cleaned = _strip_code_fence(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"judge response is not valid JSON: {text!r}") from exc
    if not isinstance(data, dict):
        raise JudgeParseError(f"judge response must be a JSON object, got {type(data).__name__}")

    scores: dict[str, int] = {}
    for dim_id in rubric.dimension_ids:
        if dim_id not in data:
            raise JudgeParseError(f"judge response missing dimension {dim_id!r}: {text!r}")
        try:
            score = int(data[dim_id])
        except (TypeError, ValueError) as exc:
            raise JudgeParseError(
                f"dimension {dim_id!r} has a non-integer score {data[dim_id]!r}"
            ) from exc
        if not 0 <= score <= 4:
            raise JudgeParseError(f"dimension {dim_id!r} score {score} is out of range 0-4")
        scores[dim_id] = score

    return RubricScore(
        turn_id=turn_id, scores=scores, rubric_version=rubric.version, judge_model=judge_model
    )


async def run_judge(
    llm: LLMProvider,
    rubric: Rubric,
    turn: GoldenTurn,
    reply_text: str,
) -> RubricScore:
    """Score one generated reply against the rubric."""
    prompt = build_judge_prompt(rubric, turn, reply_text)
    messages = [
        Message(role=Role.SYSTEM, content="You are a strict, consistent evaluator."),
        Message(role=Role.USER, content=prompt),
    ]
    config = LLMConfig(temperature=0.0)

    parts: list[str] = []
    async for delta in llm.stream(messages, config):
        if delta.text:
            parts.append(delta.text)

    return parse_judge_response("".join(parts), rubric, turn.id, judge_model=llm.name)
