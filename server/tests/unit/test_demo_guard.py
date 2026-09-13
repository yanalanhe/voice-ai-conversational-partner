from __future__ import annotations

from datetime import date

from app.security.demo_guard import (
    AccessCodeGuard,
    DailySpendCeiling,
    RateLimiter,
    TurnCapEnforcer,
)


class TestAccessCodeGuard:
    def test_disabled_when_no_code_configured(self) -> None:
        guard = AccessCodeGuard(required_code=None)
        assert guard.check(None) is True
        assert guard.check("anything") is True

    def test_accepts_matching_code(self) -> None:
        guard = AccessCodeGuard(required_code="secret")
        assert guard.check("secret") is True

    def test_rejects_wrong_code(self) -> None:
        guard = AccessCodeGuard(required_code="secret")
        assert guard.check("wrong") is False

    def test_rejects_missing_code_when_one_is_required(self) -> None:
        guard = AccessCodeGuard(required_code="secret")
        assert guard.check(None) is False


class TestRateLimiter:
    def test_allows_up_to_the_limit(self) -> None:
        limiter = RateLimiter(max_events=3, window_seconds=60)
        assert limiter.allow("ip1", now=0.0)
        assert limiter.allow("ip1", now=0.0)
        assert limiter.allow("ip1", now=0.0)

    def test_rejects_beyond_the_limit_within_the_window(self) -> None:
        limiter = RateLimiter(max_events=2, window_seconds=60)
        assert limiter.allow("ip1", now=0.0)
        assert limiter.allow("ip1", now=1.0)
        assert not limiter.allow("ip1", now=2.0)

    def test_old_events_expire_out_of_the_window(self) -> None:
        limiter = RateLimiter(max_events=2, window_seconds=10)
        assert limiter.allow("ip1", now=0.0)
        assert limiter.allow("ip1", now=1.0)
        assert not limiter.allow("ip1", now=2.0)
        # First two events are now outside the 10s window
        assert limiter.allow("ip1", now=15.0)

    def test_keys_are_independent(self) -> None:
        limiter = RateLimiter(max_events=1, window_seconds=60)
        assert limiter.allow("ip1", now=0.0)
        assert not limiter.allow("ip1", now=0.0)
        assert limiter.allow("ip2", now=0.0)  # different key, unaffected


class TestTurnCapEnforcer:
    def test_allows_turns_up_to_the_cap(self) -> None:
        cap = TurnCapEnforcer(max_turns=2)
        assert cap.record_turn() is True
        assert cap.record_turn() is True

    def test_rejects_beyond_the_cap(self) -> None:
        cap = TurnCapEnforcer(max_turns=1)
        assert cap.record_turn() is True
        assert cap.record_turn() is False

    def test_remaining_counts_down(self) -> None:
        cap = TurnCapEnforcer(max_turns=3)
        assert cap.remaining == 3
        cap.record_turn()
        assert cap.remaining == 2

    def test_remaining_never_goes_negative(self) -> None:
        cap = TurnCapEnforcer(max_turns=1)
        cap.record_turn()
        cap.record_turn()  # rejected, but should not corrupt state
        assert cap.remaining == 0


class TestDailySpendCeiling:
    def test_allows_turns_up_to_the_ceiling(self) -> None:
        ceiling = DailySpendCeiling(max_turns_per_day=2)
        today = date(2026, 9, 11)
        assert ceiling.record_turn(today) is True
        assert ceiling.record_turn(today) is True

    def test_fails_closed_beyond_the_ceiling(self) -> None:
        ceiling = DailySpendCeiling(max_turns_per_day=1)
        today = date(2026, 9, 11)
        assert ceiling.record_turn(today) is True
        assert ceiling.record_turn(today) is False

    def test_resets_on_a_new_day(self) -> None:
        ceiling = DailySpendCeiling(max_turns_per_day=1)
        day1 = date(2026, 9, 11)
        day2 = date(2026, 9, 12)
        assert ceiling.record_turn(day1) is True
        assert ceiling.record_turn(day1) is False
        assert ceiling.record_turn(day2) is True  # new day, counter reset

    def test_shared_across_calls_same_day(self) -> None:
        """Models multiple sessions sharing one ceiling instance."""
        ceiling = DailySpendCeiling(max_turns_per_day=3)
        today = date(2026, 9, 11)
        # Three different "sessions" all draw from the same daily budget.
        assert ceiling.record_turn(today) is True
        assert ceiling.record_turn(today) is True
        assert ceiling.record_turn(today) is True
        assert ceiling.record_turn(today) is False
