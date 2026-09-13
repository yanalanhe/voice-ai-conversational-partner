"""Wire-protocol round-trip tests for the FastAPI gateway.

Deliberately thin: all turn-taking and barge-in logic is already covered
against the orchestrator directly in test_orchestrator.py with zero transport
overhead. This file only proves the ASGI WebSocket plumbing -- binary audio
frames in, JSON control in, JSON events + binary audio out -- actually
round-trips end to end.
"""

from __future__ import annotations

import app.main as main_module
import pytest
from app.main import app
from app.security.demo_guard import RateLimiter
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _disable_demo_hardening(monkeypatch: pytest.MonkeyPatch) -> None:
    """This file tests wire-protocol round-tripping, not demo hardening (see
    test_demo_hardening_gateway.py for that) -- but `_CONNECTION_RATE_LIMITER`
    is a module-level singleton in app.main shared across the whole pytest
    process. Without resetting it here, this file's ~10 connections plus
    whatever test_demo_hardening_gateway.py opened in the same run can
    exceed the production default of 5/minute and get legitimately
    rejected -- a real test-isolation bug, not a flaky test."""
    monkeypatch.setattr(
        main_module, "_CONNECTION_RATE_LIMITER", RateLimiter(max_events=1000, window_seconds=60)
    )


def test_health_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_full_turn_round_trips_over_the_socket() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws/session") as ws:
        ws.send_bytes(b"\x00" * 320)
        ws.send_json({"type": "speech_end"})

        transcript = ws.receive_json()
        assert transcript["type"] == "transcript"
        assert transcript["text"]  # first scripted MockSTT utterance

        got_audio = False
        for _ in range(20):
            msg = ws.receive_json()
            if msg["type"] == "assistant_text":
                audio = ws.receive_bytes()
                assert isinstance(audio, (bytes, bytearray))
                got_audio = True
            elif msg["type"] == "turn_complete":
                assert msg["summary"]["ttfa_ms"] is not None
                break
        assert got_audio


def test_speech_start_with_no_prior_turn_does_not_crash_the_socket() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws/session") as ws:
        ws.send_json({"type": "speech_start"})
        # Socket should still be alive and able to complete a normal turn.
        ws.send_bytes(b"\x00" * 320)
        ws.send_json({"type": "speech_end"})
        msg = ws.receive_json()
        assert msg["type"] == "transcript"


def test_multiple_turns_in_one_session_advance_the_scripted_conversation() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws/session") as ws:
        seen_texts = []
        for _ in range(2):
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "speech_end"})
            transcript = ws.receive_json()
            seen_texts.append(transcript["text"])
            # drain until turn_complete
            while True:
                msg = ws.receive_json()
                if msg["type"] == "assistant_text":
                    ws.receive_bytes()
                elif msg["type"] == "turn_complete":
                    break
        assert seen_texts == ["你好。", "我要米饭。"]


def test_demo_script_loops_past_the_scripted_conversation_end() -> None:
    """Regression test for the original bug report: after the scripted
    conversation runs out, the demo must keep cycling, not go silently
    unresponsive (see MockSTT/scripted_tutor's `loop` parameter)."""
    client = TestClient(app)
    with client.websocket_connect("/ws/session") as ws:
        seen_texts = []
        for _ in range(5):  # more turns than the 3-line script has
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "speech_end"})
            transcript = ws.receive_json()
            seen_texts.append(transcript["text"])
            while True:
                msg = ws.receive_json()
                if msg["type"] == "assistant_text":
                    ws.receive_bytes()
                elif msg["type"] == "turn_complete":
                    break
        assert seen_texts == ["你好。", "我要米饭。", "谢谢，再见。", "你好。", "我要米饭。"]


def test_demo_script_env_var_switches_to_generic_english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_DEMO_SCRIPT", "generic")
    client = TestClient(main_module.app)
    with client.websocket_connect("/ws/session") as ws:
        ws.send_bytes(b"\x00" * 320)
        ws.send_json({"type": "speech_end"})
        transcript = ws.receive_json()
        assert transcript["text"] == "hello"
