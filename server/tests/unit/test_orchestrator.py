import asyncio

from app.providers.mock import LatencyProfile, MockLLM, MockSTT, MockTTS, scripted_tutor
from app.providers.types import AudioChunk, Role
from app.session.events import (
    AssistantAudioEvent,
    NoSpeechEvent,
    OrchestratorEvent,
    TranscriptEvent,
    TurnCompleteEvent,
    TurnInterruptedEvent,
)
from app.session.orchestrator import SessionOrchestrator


def _fast_stt(utterances: list[str], **kwargs) -> MockSTT:
    return MockSTT(
        utterances=utterances,
        interim_latency=LatencyProfile(0.0),
        final_latency=LatencyProfile(0.0),
        **kwargs,
    )


def _fast_llm(reply: str, **kwargs) -> MockLLM:
    kwargs.setdefault("inter_token", LatencyProfile(0.0))
    return MockLLM(responder=scripted_tutor([reply]), ttft=LatencyProfile(0.0), **kwargs)


def _fast_tts(**kwargs) -> MockTTS:
    kwargs.setdefault("realtime_factor", 0.0)
    return MockTTS(ttfb=LatencyProfile(0.0), **kwargs)


async def _drain(outbox: asyncio.Queue[OrchestratorEvent]) -> list[OrchestratorEvent]:
    events: list[OrchestratorEvent] = []
    while not outbox.empty():
        events.append(outbox.get_nowait())
    return events


class TestHappyPath:
    async def test_full_turn_emits_transcript_audio_and_completion(self) -> None:
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(
            stt=_fast_stt(["hello there"]),
            llm=_fast_llm("Good to hear from you."),
            tts=_fast_tts(),
            outbox=outbox,
        )

        await orch.on_audio_frame(AudioChunk(data=b"\x00" * 320, seq=0))
        await orch.on_speech_end()
        await asyncio.sleep(0.05)  # let the turn task run to completion

        events = await _drain(outbox)
        assert any(isinstance(e, TranscriptEvent) and e.text == "hello there" for e in events)
        assert any(isinstance(e, AssistantAudioEvent) for e in events)
        assert any(isinstance(e, TurnCompleteEvent) for e in events)
        assert orch.state == "listening"

    async def test_history_records_both_sides_of_the_turn(self) -> None:
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(
            stt=_fast_stt(["hi"]),
            llm=_fast_llm("Hello!"),
            tts=_fast_tts(),
            outbox=outbox,
        )
        await orch.on_speech_end()
        await asyncio.sleep(0.05)

        history = orch.history
        assert history[-2].role is Role.USER
        assert history[-2].content == "hi"
        assert history[-1].role is Role.ASSISTANT
        assert "Hello!" in history[-1].content

    async def test_silence_produces_no_turn(self) -> None:
        """No turn happens, but the learner still gets told nothing was
        heard -- a real STT provider can genuinely hear silence or unclear
        audio, and dropping that outcome with zero feedback is
        indistinguishable from the app being broken (see NoSpeechEvent)."""
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(
            stt=_fast_stt([""]),  # STT heard nothing
            llm=_fast_llm("should never be called"),
            tts=_fast_tts(),
            outbox=outbox,
        )
        await orch.on_speech_end()
        await asyncio.sleep(0.02)

        events = await _drain(outbox)
        assert events == [NoSpeechEvent()]
        assert orch.history == []
        assert orch.state == "listening"


class TestBargeIn:
    async def test_speech_start_mid_turn_cancels_and_flags_interrupted(self) -> None:
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(
            stt=_fast_stt(["first utterance", "second utterance"]),
            llm=_fast_llm(
                "A long reply that keeps going for quite a while so there is time to interrupt.",
                inter_token=LatencyProfile(20.0),
            ),
            tts=_fast_tts(realtime_factor=0.5),
            outbox=outbox,
        )

        await orch.on_speech_end()  # starts turn 1
        await asyncio.sleep(0.02)  # let it get partway through generation
        assert orch.state == "speaking"

        await orch.on_speech_start()  # barge-in

        assert orch.state == "listening"
        events = await _drain(outbox)
        assert any(isinstance(e, TurnInterruptedEvent) for e in events)
        assert not any(isinstance(e, TurnCompleteEvent) for e in events)

    async def test_interrupted_turn_does_not_pollute_history(self) -> None:
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(
            stt=_fast_stt(["said something"]),
            llm=_fast_llm(
                "A long reply that keeps going for quite a while.",
                inter_token=LatencyProfile(20.0),
            ),
            tts=_fast_tts(realtime_factor=0.5),
            outbox=outbox,
        )
        await orch.on_speech_end()
        await asyncio.sleep(0.02)
        await orch.on_speech_start()

        # The user's turn is recorded; no partial/garbled assistant reply is.
        assert len(orch.history) == 1
        assert orch.history[0].role is Role.USER

    async def test_buffered_audio_during_speaking_is_replayed_after_bargein(self) -> None:
        received: list[AudioChunk] = []
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(
            stt=_fast_stt(["turn one", "turn two"], received_chunks=received),
            llm=_fast_llm(
                "A long reply that keeps going for quite a while so there is time.",
                inter_token=LatencyProfile(20.0),
            ),
            tts=_fast_tts(realtime_factor=0.5),
            outbox=outbox,
        )

        await orch.on_speech_end()  # turn 1, no audio buffered for it
        await asyncio.sleep(0.02)
        assert orch.state == "speaking"

        interrupting_chunk = AudioChunk(data=b"\x01" * 320, seq=99)
        await orch.on_audio_frame(interrupting_chunk)  # buffered, agent is speaking
        await orch.on_speech_start()  # barge-in: buffered audio should be replayed

        await orch.on_speech_end()  # finalize the (short) interrupting utterance
        await asyncio.sleep(0.02)

        assert interrupting_chunk in received

    async def test_speech_start_while_already_listening_is_a_noop_not_a_crash(self) -> None:
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(stt=_fast_stt(["x"]), llm=_fast_llm("y"), tts=_fast_tts(),
                                    outbox=outbox)
        await orch.on_speech_start()
        assert orch.state == "listening"


class TestClose:
    async def test_close_cancels_pending_turn_without_raising(self) -> None:
        outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
        orch = SessionOrchestrator(
            stt=_fast_stt(["hi"]),
            llm=_fast_llm("A long reply.", inter_token=LatencyProfile(20.0)),
            tts=_fast_tts(realtime_factor=0.5),
            outbox=outbox,
        )
        await orch.on_speech_end()
        await asyncio.sleep(0.02)
        await orch.close()  # should not raise
