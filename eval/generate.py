"""Generates fresh agent replies for golden-set turns against the model
under test.

Uses `app.pedagogy.prompts.build_system_prompt` -- the same function
production calls via `app.session.factory` -- so an eval run exercises the
real prompt-construction path, not a hand-written stand-in that could
silently drift from what the orchestrator actually sends.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.pedagogy.packs import load_builtin_pack
from app.pedagogy.prompts import build_system_prompt
from app.providers.protocols import LLMProvider
from app.providers.types import LLMConfig, Message, Role

from eval.schema import GeneratedReply, GoldenTurn


async def generate_reply(
    llm: LLMProvider,
    turn: GoldenTurn,
    llm_config: LLMConfig | None = None,
) -> GeneratedReply:
    pack = load_builtin_pack(turn.pack)
    level = pack.level(turn.level)
    scenario = pack.scenario(turn.scenario)
    prompt = build_system_prompt(pack, level, scenario)

    messages = [Message(role=Role.SYSTEM, content=prompt.text)]
    messages.extend(Message(role=Role(role), content=content) for role, content in turn.history)
    messages.append(Message(role=Role.USER, content=turn.learner_utterance))

    parts: list[str] = []
    async for delta in llm.stream(messages, llm_config or LLMConfig()):
        if delta.text:
            parts.append(delta.text)

    return GeneratedReply(turn=turn, reply_text="".join(parts))


async def generate_all(
    llm: LLMProvider,
    turns: Sequence[GoldenTurn],
    llm_config: LLMConfig | None = None,
) -> list[GeneratedReply]:
    return [await generate_reply(llm, t, llm_config) for t in turns]
