"""Public-demo hardening (PRD Sec 8.0 amendment).

A publicly reachable voice endpoint spends real API credits for anyone who
finds the URL. Four independent guards, each failing closed by default:

    AccessCodeGuard     -- WS connections must present a shared code
    RateLimiter         -- caps new connections per IP per time window
    TurnCapEnforcer      -- caps turns within one WebSocket connection
    DailySpendCeiling    -- caps total turns across ALL sessions per UTC day

All four are in-memory and process-local -- correct for a single-instance
demo deployment (Azure Container Apps running one replica), not a substitute
for distributed rate limiting if this ever needed to scale past one process.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class AccessCodeGuard:
    """Rejects unless the caller presents the configured shared code.

    `required_code=None` disables the guard entirely -- the default for
    local development, where there is nothing to protect.
    """

    required_code: str | None

    def check(self, presented_code: str | None) -> bool:
        if self.required_code is None:
            return True
        return presented_code == self.required_code


@dataclass(slots=True)
class RateLimiter:
    """Sliding-window limiter: at most `max_events` per `window_seconds`, per key."""

    max_events: int
    window_seconds: float
    _events: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        window_start = now - self.window_seconds
        events = [t for t in self._events.get(key, []) if t >= window_start]
        if len(events) >= self.max_events:
            self._events[key] = events
            return False
        events.append(now)
        self._events[key] = events
        return True


@dataclass(slots=True)
class TurnCapEnforcer:
    """Caps turns within a single session. Construct one instance per connection."""

    max_turns: int
    _count: int = field(default=0, init=False)

    def record_turn(self) -> bool:
        """True if this turn is allowed; False if the cap was already reached."""
        if self._count >= self.max_turns:
            return False
        self._count += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.max_turns - self._count)


@dataclass(slots=True)
class DailySpendCeiling:
    """Global daily turn budget, shared across all sessions, fails closed.

    A proxy for real spend tracking: this build has no real provider billing
    to sum (every provider is a mock -- see ADR-003), so turn count stands in
    for cost until a real adapter exists to report actual token/audio-second
    usage. Resets at UTC midnight.
    """

    max_turns_per_day: int
    _day: date = field(default_factory=date.today, init=False)
    _count: int = field(default=0, init=False)

    def _roll_if_new_day(self, today: date) -> None:
        if today != self._day:
            self._day = today
            self._count = 0

    def record_turn(self, today: date | None = None) -> bool:
        self._roll_if_new_day(today if today is not None else date.today())
        if self._count >= self.max_turns_per_day:
            return False
        self._count += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.max_turns_per_day - self._count)
