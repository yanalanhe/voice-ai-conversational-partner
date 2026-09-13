"""Learner profile and store (PRD LS-1, LS-2).

`LearnerStore` is in-memory. The PRD's stack table lists Postgres as the
production path; the get_or_create/save contract here is deliberately the
whole interface a Postgres-backed store would need to satisfy, so swapping
storage later does not touch the orchestrator or the pedagogy layer -- only
this module's internals change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.types import Message


@dataclass(frozen=True, slots=True)
class ErrorLogEntry:
    """One recorded pedagogical error, persistent across sessions (LS-1)."""

    turn_id: str
    category: str  # e.g. "vocabulary_ceiling"
    detail: str  # e.g. the offending word


@dataclass(slots=True)
class LearnerProfile:
    learner_id: str
    pack_name: str
    level_code: str
    scenario_history: list[str] = field(default_factory=list)
    error_log: list[ErrorLogEntry] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    """Snapshot of conversation history, persisted between sessions so a
    reconnect can restore context (LS-2). Written by whatever owns the
    SessionOrchestrator (the gateway) when a session ends."""
    turns_completed: int = 0

    def record_scenario_start(self, scenario_id: str) -> None:
        if not self.scenario_history or self.scenario_history[-1] != scenario_id:
            self.scenario_history.append(scenario_id)

    def record_error(self, entry: ErrorLogEntry) -> None:
        self.error_log.append(entry)

    def errors_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.error_log:
            counts[entry.category] = counts.get(entry.category, 0) + 1
        return counts


@dataclass
class LearnerStore:
    _profiles: dict[str, LearnerProfile] = field(default_factory=dict)

    def get_or_create(self, learner_id: str, pack_name: str, level_code: str) -> LearnerProfile:
        profile = self._profiles.get(learner_id)
        if profile is None:
            profile = LearnerProfile(
                learner_id=learner_id, pack_name=pack_name, level_code=level_code
            )
            self._profiles[learner_id] = profile
        return profile

    def save(self, profile: LearnerProfile) -> None:
        self._profiles[profile.learner_id] = profile

    def get(self, learner_id: str) -> LearnerProfile | None:
        return self._profiles.get(learner_id)
