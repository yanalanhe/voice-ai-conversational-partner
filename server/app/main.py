"""FastAPI WebSocket gateway.

Thin transport shim over SessionOrchestrator (server/app/session/orchestrator.py)
-- this file's only job is translating between the wire protocol (binary PCM
frames + JSON control messages) and the orchestrator's transport-agnostic
method calls. All turn-taking, barge-in, and pipeline logic lives in the
orchestrator; there is deliberately little to test here beyond "does the wire
format round-trip" (see test_gateway.py).

Providers are mocks (ADR-003) until real adapters land -- swapping in Azure
Speech / Azure OpenAI later is a one-line change in `_default_orchestrator`,
not a change to the orchestrator or this gateway. The pedagogy wiring around
those mocks (pack, level, scenario, prompt) is real, via
`app.session.factory.build_pedagogy_orchestrator` -- not a stub.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.pedagogy.packs import load_builtin_pack
from app.providers.mock import MockLLM, MockSTT, MockTTS, scripted_tutor
from app.providers.types import AudioChunk
from app.security.demo_guard import (
    AccessCodeGuard,
    DailySpendCeiling,
    RateLimiter,
    TurnCapEnforcer,
)
from app.session.events import (
    AssistantAudioEvent,
    OrchestratorEvent,
    TranscriptEvent,
    TurnCompleteEvent,
    TurnInterruptedEvent,
)
from app.session.factory import build_pedagogy_orchestrator
from app.session.orchestrator import SessionOrchestrator
from app.state.learner import LearnerStore

logger = logging.getLogger("parlons.gateway")

app = FastAPI(title="Parlons Voice AI Gateway")

# Public-demo hardening (PRD Sec 8.0 amendment) -- see app/security/demo_guard.py.
# DEMO_ACCESS_CODE unset means the guard is disabled, which is correct for
# local development; a public deployment must set it.
_ACCESS_CODE_GUARD = AccessCodeGuard(required_code=os.environ.get("DEMO_ACCESS_CODE"))
_CONNECTION_RATE_LIMITER = RateLimiter(
    max_events=int(os.environ.get("DEMO_CONNECTIONS_PER_MINUTE", "5")), window_seconds=60.0
)
_SPEND_CEILING = DailySpendCeiling(
    max_turns_per_day=int(os.environ.get("DEMO_DAILY_TURN_CEILING", "500"))
)
_MAX_TURNS_PER_SESSION = int(os.environ.get("DEMO_TURNS_PER_SESSION", "20"))

# "zh_hsk" (default) shows the actual pedagogy layer: real prompt-building
# from the HSK1 level policy and a real vocabulary-ceiling check on every
# reply. "generic" is a plain English scripted stub with no pedagogy at all
# -- useful for sanity-checking pipeline mechanics (turn-taking, barge-in,
# latency) without needing to read Mandarin. Both packs that actually ship
# (zh_hsk, fr_sle) always have English as the SOURCE language, never the
# target -- there is no "practice English" pack, because the project's whole
# point is an English speaker practicing a foreign language. "generic" is
# the closest thing to an English-language demo, and it is not pedagogy at
# all, just a fixed script.
_DEMO_SCRIPT = os.environ.get("DEMO_SCRIPT", "zh_hsk")

# Loaded once at import time -- pack loading reads and parses YAML + wordlist
# files (app/pedagogy/packs.py), no reason to redo that per connection.
_DEMO_PACK = load_builtin_pack("zh_hsk")
_DEMO_SCENARIO_ID = "ordering_lunch"
_DEMO_LEVEL_CODE = "HSK1"

# Scripted learner utterances and agent replies for the `ordering_lunch`
# scenario, verified against the real HSK1 ceiling check
# (app/pedagogy/ceiling.py) before being hardcoded here -- see this file's
# git history for two rounds of wordlist gaps ("我要", "我们") that turned up
# only once these exact lines were run through check_ceiling for real, not
# eyeballed. `loop=True` on both sides keeps the STT and LLM scripts in
# lockstep after they run out, rather than the demo going silently
# unresponsive once the scenario ends (see MockSTT's and scripted_tutor's
# `loop` parameter docstrings).
_DEMO_LEARNER_UTTERANCES = ["你好。", "我要米饭。", "谢谢，再见。"]
_DEMO_AGENT_REPLIES = ["你好！你想吃什么？", "好，我们有米饭。", "再见！"]


def _default_orchestrator(outbox: asyncio.Queue[OrchestratorEvent]) -> SessionOrchestrator:
    """Pedagogy-backed demo orchestrator.

    STT/LLM/TTS are mocks (ADR-003) -- no real speech recognition or model
    call happens here, and the "recognized" learner utterances are scripted
    regardless of what a visitor actually says into their microphone. What IS
    real: the prompt is built from the actual zh_hsk pack and HSK1 level
    policy (app/pedagogy/prompts.py), and every agent reply is checked
    against the real vocabulary ceiling via `build_pedagogy_orchestrator`'s
    `on_turn_complete` hook, same as a live session's would be.

    Each connection gets a fresh, unpersisted LearnerProfile -- there is no
    reason for one public-demo visitor's session to share state with another.

    Set DEMO_SCRIPT=generic for a plain English scripted conversation instead
    -- no pedagogy layer involved at all, just MockSTT/MockLLM directly.
    """
    if _DEMO_SCRIPT == "generic":
        return SessionOrchestrator(
            stt=MockSTT(utterances=["hello", "how are you", "goodbye"], loop=True),
            llm=MockLLM(
                responder=scripted_tutor(
                    [
                        "Hello! Nice to meet you.",
                        "I'm doing well, thank you for asking.",
                        "Goodbye, take care!",
                    ],
                    loop=True,
                )
            ),
            tts=MockTTS(),
            outbox=outbox,
        )

    learner = LearnerStore().get_or_create(
        learner_id=str(uuid.uuid4()), pack_name=_DEMO_PACK.name, level_code=_DEMO_LEVEL_CODE
    )
    orchestrator, _prompt = build_pedagogy_orchestrator(
        stt=MockSTT(utterances=_DEMO_LEARNER_UTTERANCES, loop=True),
        llm=MockLLM(responder=scripted_tutor(_DEMO_AGENT_REPLIES, loop=True)),
        tts=MockTTS(),
        outbox=outbox,
        pack=_DEMO_PACK,
        scenario_id=_DEMO_SCENARIO_ID,
        learner=learner,
    )
    return orchestrator


def _event_to_json(event: OrchestratorEvent) -> dict[str, object]:
    if isinstance(event, TranscriptEvent):
        return {"type": "transcript", "text": event.text}
    if isinstance(event, TurnCompleteEvent):
        return {"type": "turn_complete", "summary": event.summary}
    if isinstance(event, TurnInterruptedEvent):
        return {"type": "turn_interrupted", "summary": event.summary}
    raise TypeError(f"no JSON mapping for {type(event)!r}")


@app.websocket("/ws/session")
async def session_endpoint(websocket: WebSocket) -> None:
    client_ip = websocket.client.host if websocket.client else "unknown"
    presented_code = websocket.query_params.get("code")

    # Both checks happen BEFORE accept() -- an unaccepted WebSocket can still
    # be closed with a custom code, which the client's onclose handler can
    # distinguish from a normal disconnect, without spending an accept/turn
    # on a request that should never have been let in.
    if not _ACCESS_CODE_GUARD.check(presented_code):
        await websocket.close(code=4001, reason="invalid access code")
        return
    if not _CONNECTION_RATE_LIMITER.allow(client_ip):
        await websocket.close(code=4002, reason="rate limited, try again shortly")
        return

    await websocket.accept()
    outbox: asyncio.Queue[OrchestratorEvent] = asyncio.Queue()
    orch = _default_orchestrator(outbox)
    turn_cap = TurnCapEnforcer(max_turns=_MAX_TURNS_PER_SESSION)
    seq = 0

    async def sender() -> None:
        while True:
            event = await outbox.get()
            if isinstance(event, AssistantAudioEvent):
                await websocket.send_json(
                    {"type": "assistant_text", "text": event.chunk.text, "seq": event.chunk.seq}
                )
                await websocket.send_bytes(event.chunk.audio.data)
            else:
                await websocket.send_json(_event_to_json(event))

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if (data := message.get("bytes")) is not None:
                await orch.on_audio_frame(AudioChunk(data=data, seq=seq))
                seq += 1
            elif (text := message.get("text")) is not None:
                control = json.loads(text)
                if control.get("type") == "speech_start":
                    await orch.on_speech_start()
                elif control.get("type") == "speech_end":
                    if not _SPEND_CEILING.record_turn():
                        await websocket.send_json(
                            {"type": "error", "reason": "daily demo capacity reached"}
                        )
                        break
                    if not turn_cap.record_turn():
                        await websocket.send_json(
                            {"type": "error", "reason": "session turn limit reached"}
                        )
                        break
                    await orch.on_speech_end()
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass
        await orch.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
