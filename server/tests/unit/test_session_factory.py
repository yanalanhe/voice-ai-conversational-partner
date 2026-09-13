from __future__ import annotations

import asyncio

from app.pedagogy.packs import load_builtin_pack
from app.pedagogy.prompts import build_system_prompt
from app.providers.mock import LatencyProfile, MockLLM, MockSTT, MockTTS, scripted_tutor
from app.providers.types import Message, Role
from app.session.events import OrchestratorEvent
from app.session.factory import build_pedagogy_orchestrator
from app.state.learner import LearnerStore


def _fast_stt(utterances: list[str]) -> MockSTT:
    return MockSTT(
        utterances=utterances,
        interim_latency=LatencyProfile(0.0),
        final_latency=LatencyProfile(0.0),
    )


def _fast_llm(reply: str) -> MockLLM:
    return MockLLM(
        responder=scripted_tutor([reply]), ttft=LatencyProfile(0.0),
        inter_token=LatencyProfile(0.0),
    )


def _fast_tts() -> MockTTS:
    return MockTTS(ttfb=LatencyProfile(0.0), realtime_factor=0.0)


class TestFactoryWiring:
    async def test_built_prompt_matches_a_fresh_build_system_prompt_call(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        store = LearnerStore()
        learner = store.get_or_create("alan", "zh_hsk", "HSK1")
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()

        _orch, prompt = build_pedagogy_orchestrator(
            stt=_fast_stt(["hi"]),
            llm=_fast_llm("hello"),
            tts=_fast_tts(),
            outbox=outbox,
            pack=pack,
            scenario_id="ordering_lunch",
            learner=learner,
        )

        expected = build_system_prompt(
            pack, pack.level("HSK1"), pack.scenario("ordering_lunch"), learner_name="alan"
        )
        assert prompt.version_hash == expected.version_hash
        assert prompt.text == expected.text

    async def test_records_scenario_start_on_the_learner(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        store = LearnerStore()
        learner = store.get_or_create("alan", "zh_hsk", "HSK1")
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()

        build_pedagogy_orchestrator(
            stt=_fast_stt(["hi"]), llm=_fast_llm("hello"), tts=_fast_tts(),
            outbox=outbox, pack=pack, scenario_id="ordering_lunch", learner=learner,
        )

        assert learner.scenario_history == ["ordering_lunch"]

    async def test_ceiling_violation_in_agent_reply_lands_in_error_log(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        store = LearnerStore()
        learner = store.get_or_create("alan", "zh_hsk", "HSK1")
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()

        orch, _prompt = build_pedagogy_orchestrator(
            stt=_fast_stt(["你好"]),
            llm=_fast_llm("我们要互相尊重"),  # "尊重" is HSK4-only -- violates HSK1 ceiling
            tts=_fast_tts(),
            outbox=outbox,
            pack=pack,
            scenario_id="ordering_lunch",
            learner=learner,
        )

        await orch.on_speech_end()
        await asyncio.sleep(0.05)

        assert learner.error_log
        assert all(e.category == "vocabulary_ceiling" for e in learner.error_log)
        assert learner.turns_completed == 1

    async def test_clean_reply_produces_no_error_log_entries(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        store = LearnerStore()
        learner = store.get_or_create("alan", "zh_hsk", "HSK1")
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()

        orch, _prompt = build_pedagogy_orchestrator(
            stt=_fast_stt(["你好"]),
            llm=_fast_llm("你好"),  # well within HSK1
            tts=_fast_tts(),
            outbox=outbox,
            pack=pack,
            scenario_id="ordering_lunch",
            learner=learner,
        )

        await orch.on_speech_end()
        await asyncio.sleep(0.05)

        assert learner.error_log == []
        assert learner.turns_completed == 1

    async def test_prior_messages_are_restored_into_orchestrator_history(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        store = LearnerStore()
        learner = store.get_or_create("alan", "zh_hsk", "HSK1")
        learner.messages = [
            Message(role=Role.USER, content="你好"),
            Message(role=Role.ASSISTANT, content="你好，很高兴认识你"),
        ]
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()

        orch, _prompt = build_pedagogy_orchestrator(
            stt=_fast_stt(["新的一句话"]), llm=_fast_llm("好的"), tts=_fast_tts(),
            outbox=outbox, pack=pack, scenario_id="ordering_lunch", learner=learner,
        )

        assert len(orch.history) == 2
        assert orch.history[0].content == "你好"

    async def test_pack_tts_voice_and_speaking_rate_are_applied(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        store = LearnerStore()
        learner = store.get_or_create("alan", "zh_hsk", "HSK1")
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()

        orch, _prompt = build_pedagogy_orchestrator(
            stt=_fast_stt(["hi"]), llm=_fast_llm("hello"), tts=_fast_tts(),
            outbox=outbox, pack=pack, scenario_id="ordering_lunch", learner=learner,
        )

        assert orch.tts_config.voice == pack.tts_voice
        assert orch.tts_config.speaking_rate == pack.level("HSK1").speaking_rate

    async def test_works_end_to_end_for_fr_sle_pack(self) -> None:
        pack = load_builtin_pack("fr_sle")
        store = LearnerStore()
        learner = store.get_or_create("yan", "fr_sle", "A")
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()

        orch, prompt = build_pedagogy_orchestrator(
            stt=_fast_stt(["bonjour"]),
            llm=_fast_llm("Bonjour, comment allez-vous?"),
            tts=_fast_tts(),
            outbox=outbox,
            pack=pack,
            scenario_id="ordering_lunch",
            learner=learner,
        )

        await orch.on_speech_end()
        await asyncio.sleep(0.05)

        assert "fr-CA" in prompt.text
        assert learner.turns_completed == 1
