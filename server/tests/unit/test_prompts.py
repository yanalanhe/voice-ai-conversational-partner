from __future__ import annotations

from app.pedagogy.packs import load_builtin_pack
from app.pedagogy.prompts import build_system_prompt


class TestPromptDeterminism:
    def test_same_inputs_produce_same_hash(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")

        a = build_system_prompt(pack, level, scenario)
        b = build_system_prompt(pack, level, scenario)
        assert a.text == b.text
        assert a.version_hash == b.version_hash

    def test_different_level_produces_different_hash(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        scenario = pack.scenario("ordering_lunch")

        a = build_system_prompt(pack, pack.level("HSK1"), scenario)
        b = build_system_prompt(pack, pack.level("HSK3"), scenario)
        assert a.version_hash != b.version_hash

    def test_different_scenario_produces_different_hash(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")

        a = build_system_prompt(pack, level, pack.scenario("ordering_lunch"))
        b = build_system_prompt(pack, level, pack.scenario("asking_directions"))
        assert a.version_hash != b.version_hash

    def test_learner_name_changes_hash_but_not_scenario_content(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")

        a = build_system_prompt(pack, level, scenario, learner_name="Alan")
        b = build_system_prompt(pack, level, scenario, learner_name="Yan")
        assert a.version_hash != b.version_hash
        assert "Alan" in a.text
        assert "Yan" in b.text


class TestPromptContent:
    def test_disallowed_l1_scaffolding_adds_stay_in_target_language_instruction(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        scenario = pack.scenario("ordering_lunch")

        hsk1 = build_system_prompt(pack, pack.level("HSK1"), scenario)  # l1 allowed
        hsk3 = build_system_prompt(pack, pack.level("HSK3"), scenario)  # l1 disallowed

        assert "Stay entirely in" not in hsk1.text
        assert "Stay entirely in" in hsk3.text

    def test_target_vocabulary_is_included_when_present(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK2")
        scenario = pack.scenario("ordering_lunch")
        result = build_system_prompt(pack, level, scenario)
        for word in scenario.target_vocabulary:
            assert word in result.text

    def test_retrieved_curriculum_appended_when_given(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        level = pack.level("HSK1")
        scenario = pack.scenario("ordering_lunch")

        without = build_system_prompt(pack, level, scenario)
        with_curriculum = build_system_prompt(
            pack, level, scenario, retrieved_curriculum="Unit 3: ordering food"
        )
        assert "Unit 3: ordering food" not in without.text
        assert "Unit 3: ordering food" in with_curriculum.text
        assert without.version_hash != with_curriculum.version_hash

    def test_correction_strategy_instruction_matches_level(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        scenario = pack.scenario("ordering_lunch")

        hsk1 = build_system_prompt(pack, pack.level("HSK1"), scenario)  # none
        hsk3 = build_system_prompt(pack, pack.level("HSK3"), scenario)  # recast

        assert "do not correct" in hsk1.text.lower()
        assert "recast" in hsk3.text.lower()

    def test_works_for_fr_sle_pack_too(self) -> None:
        """Proves the builder is genuinely pack-agnostic, not accidentally
        specialized to zh_hsk's shape."""
        pack = load_builtin_pack("fr_sle")
        level = pack.level("A")
        scenario = pack.scenario("ordering_lunch")
        result = build_system_prompt(pack, level, scenario)
        assert pack.target_language in result.text
        assert scenario.persona in result.text
