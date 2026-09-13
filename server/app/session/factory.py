"""Wires a language pack + level + scenario + learner profile into a fully
configured SessionOrchestrator.

This is the one place pedagogy (app/pedagogy/*) and session (app/session/*)
meet. `orchestrator.py` itself imports neither `ceiling.py` nor `prompts.py`
-- this module exists specifically to keep that boundary real rather than
aspirational, per PD-0's "no language identifier in pipeline code" rule.
"""

from __future__ import annotations

import asyncio

from app.pedagogy.ceiling import check_ceiling
from app.pedagogy.models import LanguagePack
from app.pedagogy.prompts import BuiltPrompt, build_system_prompt
from app.providers.protocols import LLMProvider, STTProvider, TTSProvider
from app.providers.types import LLMConfig, STTConfig, TTSConfig
from app.session.events import OrchestratorEvent
from app.session.orchestrator import SessionOrchestrator
from app.state.learner import ErrorLogEntry, LearnerProfile


def build_pedagogy_orchestrator(
    *,
    stt: STTProvider,
    llm: LLMProvider,
    tts: TTSProvider,
    outbox: asyncio.Queue[OrchestratorEvent],
    pack: LanguagePack,
    scenario_id: str,
    learner: LearnerProfile,
    llm_config: LLMConfig | None = None,
) -> tuple[SessionOrchestrator, BuiltPrompt]:
    """Build an orchestrator calibrated to one learner's level and scenario.

    Returns the built prompt alongside the orchestrator so a caller can log
    `prompt.version_hash` per PD-3 without re-deriving it.
    """
    level = pack.level(learner.level_code)
    scenario = pack.scenario(scenario_id)
    prompt = build_system_prompt(pack, level, scenario, learner_name=learner.learner_id)

    def _on_turn_complete(_learner_text: str, agent_text: str) -> None:
        result = check_ceiling(agent_text, level, pack.tokenizer)
        for word in result.violations:
            learner.record_error(
                ErrorLogEntry(
                    turn_id=str(learner.turns_completed),
                    category="vocabulary_ceiling",
                    detail=word,
                )
            )
        learner.turns_completed += 1

    learner.record_scenario_start(scenario.id)

    orchestrator = SessionOrchestrator(
        stt=stt,
        llm=llm,
        tts=tts,
        outbox=outbox,
        system_prompt=prompt.text,
        stt_config=STTConfig(
            language=pack.target_language,
            phrase_hints=list(scenario.target_vocabulary),
        ),
        tts_config=TTSConfig(
            voice=pack.tts_voice,
            language=pack.target_language,
            speaking_rate=level.speaking_rate,
        ),
        llm_config=llm_config or LLMConfig(),
        on_turn_complete=_on_turn_complete,
    )

    if learner.messages:
        orchestrator.restore_history(learner.messages)

    return orchestrator, prompt
