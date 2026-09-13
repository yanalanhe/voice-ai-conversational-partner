"""Public-demo hardening, tested through the real WebSocket protocol.

The four guards in app/security/demo_guard.py already have thorough
unit-level tests (test_demo_guard.py) for their own arithmetic. This file
proves they are actually wired into the gateway correctly -- a guard that is
implemented but never checked protects nothing.

The guards are module-level singletons in app.main, configured once from
environment variables at import time. Each test monkeypatches the specific
singleton it needs, which isolates tests from each other without requiring
environment-variable gymnastics or module reloading.
"""

from __future__ import annotations

import app.main as main_module
from app.security.demo_guard import AccessCodeGuard, DailySpendCeiling, RateLimiter
from fastapi.testclient import TestClient


class TestAccessCodeEnforcement:
    def test_connection_rejected_without_correct_code(self, monkeypatch) -> None:
        monkeypatch.setattr(
            main_module, "_ACCESS_CODE_GUARD", AccessCodeGuard(required_code="secret")
        )
        client = TestClient(main_module.app)
        try:
            with client.websocket_connect("/ws/session") as ws:
                ws.receive_json()  # should never get here
            raised = False
        except Exception:
            raised = True
        assert raised

    def test_connection_accepted_with_correct_code(self, monkeypatch) -> None:
        monkeypatch.setattr(
            main_module, "_ACCESS_CODE_GUARD", AccessCodeGuard(required_code="secret")
        )
        client = TestClient(main_module.app)
        with client.websocket_connect("/ws/session?code=secret") as ws:
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "speech_end"})
            msg = ws.receive_json()
            assert msg["type"] == "transcript"

    def test_no_code_required_when_guard_disabled(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module, "_ACCESS_CODE_GUARD", AccessCodeGuard(required_code=None))
        client = TestClient(main_module.app)
        with client.websocket_connect("/ws/session") as ws:
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "speech_end"})
            msg = ws.receive_json()
            assert msg["type"] == "transcript"


class TestConnectionRateLimit:
    def test_excess_connections_from_same_client_are_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module, "_ACCESS_CODE_GUARD", AccessCodeGuard(required_code=None))
        monkeypatch.setattr(
            main_module, "_CONNECTION_RATE_LIMITER", RateLimiter(max_events=1, window_seconds=60)
        )
        client = TestClient(main_module.app)

        with client.websocket_connect("/ws/session"):
            pass  # first connection consumes the only allowed slot

        rejected = False
        try:
            with client.websocket_connect("/ws/session") as ws:
                ws.receive_json()
        except Exception:
            rejected = True
        assert rejected


class TestDailySpendCeiling:
    def test_turn_rejected_once_daily_ceiling_reached(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module, "_ACCESS_CODE_GUARD", AccessCodeGuard(required_code=None))
        monkeypatch.setattr(main_module, "_SPEND_CEILING", DailySpendCeiling(max_turns_per_day=0))
        client = TestClient(main_module.app)

        with client.websocket_connect("/ws/session") as ws:
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "speech_end"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "capacity" in msg["reason"]


class TestSessionTurnCap:
    def test_session_ends_after_turn_cap_reached(self, monkeypatch) -> None:
        monkeypatch.setattr(main_module, "_ACCESS_CODE_GUARD", AccessCodeGuard(required_code=None))
        monkeypatch.setattr(
            main_module, "_SPEND_CEILING", DailySpendCeiling(max_turns_per_day=1000)
        )
        monkeypatch.setattr(main_module, "_MAX_TURNS_PER_SESSION", 1)
        client = TestClient(main_module.app)

        with client.websocket_connect("/ws/session") as ws:
            # First turn succeeds normally.
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "speech_end"})
            msg = ws.receive_json()
            assert msg["type"] == "transcript"
            while True:
                msg = ws.receive_json()
                if msg["type"] == "assistant_text":
                    ws.receive_bytes()
                elif msg["type"] == "turn_complete":
                    break

            # Second turn is rejected by the per-session cap.
            ws.send_bytes(b"\x00" * 320)
            ws.send_json({"type": "speech_end"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "session turn limit" in msg["reason"]
