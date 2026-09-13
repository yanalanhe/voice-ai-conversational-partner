from __future__ import annotations

from app.state.learner import ErrorLogEntry, LearnerStore


class TestLearnerStore:
    def test_get_or_create_returns_new_profile_with_given_fields(self) -> None:
        store = LearnerStore()
        profile = store.get_or_create("alan", "zh_hsk", "HSK1")
        assert profile.learner_id == "alan"
        assert profile.pack_name == "zh_hsk"
        assert profile.level_code == "HSK1"
        assert profile.messages == []
        assert profile.error_log == []

    def test_get_or_create_is_idempotent(self) -> None:
        store = LearnerStore()
        first = store.get_or_create("alan", "zh_hsk", "HSK1")
        first.turns_completed = 5
        second = store.get_or_create("alan", "zh_hsk", "HSK1")
        assert second is first
        assert second.turns_completed == 5

    def test_get_returns_none_for_unknown_learner(self) -> None:
        store = LearnerStore()
        assert store.get("nobody") is None

    def test_save_persists_external_mutations(self) -> None:
        store = LearnerStore()
        profile = store.get_or_create("alan", "zh_hsk", "HSK1")
        profile.scenario_history.append("ordering_lunch")
        store.save(profile)
        assert store.get("alan").scenario_history == ["ordering_lunch"]  # type: ignore[union-attr]


class TestLearnerProfile:
    def test_record_scenario_start_dedups_consecutive_repeats(self) -> None:
        store = LearnerStore()
        profile = store.get_or_create("alan", "zh_hsk", "HSK1")
        profile.record_scenario_start("ordering_lunch")
        profile.record_scenario_start("ordering_lunch")
        assert profile.scenario_history == ["ordering_lunch"]

    def test_record_scenario_start_keeps_distinct_repeats_non_consecutive(self) -> None:
        store = LearnerStore()
        profile = store.get_or_create("alan", "zh_hsk", "HSK1")
        profile.record_scenario_start("ordering_lunch")
        profile.record_scenario_start("asking_directions")
        profile.record_scenario_start("ordering_lunch")
        assert profile.scenario_history == ["ordering_lunch", "asking_directions", "ordering_lunch"]

    def test_errors_by_category_counts_correctly(self) -> None:
        store = LearnerStore()
        profile = store.get_or_create("alan", "zh_hsk", "HSK1")
        profile.record_error(
            ErrorLogEntry(turn_id="0", category="vocabulary_ceiling", detail="世界")
        )
        profile.record_error(
            ErrorLogEntry(turn_id="1", category="vocabulary_ceiling", detail="难")
        )
        profile.record_error(
            ErrorLogEntry(turn_id="1", category="turn_economy", detail="too long")
        )
        assert profile.errors_by_category() == {"vocabulary_ceiling": 2, "turn_economy": 1}
