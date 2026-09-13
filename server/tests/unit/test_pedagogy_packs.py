"""Pack-loading conformance suite (PRD PD-2b).

Parametrized over every pack that ships, matching the pattern already used
for provider conformance (test_provider_conformance.py). Adding a new pack
means adding its name to `_PACK_NAMES` and it inherits this whole suite.
"""

from __future__ import annotations

import pytest
from app.pedagogy.models import LanguagePack
from app.pedagogy.packs import PackLoadError, load_builtin_pack

_PACK_NAMES = ["zh_hsk", "fr_sle"]


@pytest.fixture(params=_PACK_NAMES)
def pack(request: pytest.FixtureRequest) -> LanguagePack:
    return load_builtin_pack(request.param)


class TestPackConformance:
    def test_loads_without_error(self, pack: LanguagePack) -> None:
        assert pack.name in _PACK_NAMES

    def test_has_at_least_one_level(self, pack: LanguagePack) -> None:
        assert len(pack.levels) >= 1

    def test_has_at_least_three_scenarios(self, pack: LanguagePack) -> None:
        assert len(pack.scenarios) >= 3

    def test_every_level_has_a_nonempty_ceiling(self, pack: LanguagePack) -> None:
        for level in pack.levels.values():
            assert level.vocabulary_ceiling

    def test_every_scenario_has_required_text(self, pack: LanguagePack) -> None:
        for scenario in pack.scenarios.values():
            assert scenario.objective.strip()
            assert scenario.persona.strip()
            assert scenario.opening_line.strip()

    def test_language_fields_are_bcp47_shaped(self, pack: LanguagePack) -> None:
        assert "-" in pack.target_language
        assert "-" in pack.source_language

    def test_scenario_lookup_by_id_matches_dict_key(self, pack: LanguagePack) -> None:
        for scenario_id, scenario in pack.scenarios.items():
            assert pack.scenario(scenario_id) is scenario

    def test_level_lookup_by_code_matches_dict_key(self, pack: LanguagePack) -> None:
        for code, level in pack.levels.items():
            assert pack.level(code) is level

    def test_unknown_scenario_id_raises_with_available_list(self, pack: LanguagePack) -> None:
        with pytest.raises(KeyError, match="no such thing"):
            pack.scenario("no such thing")

    def test_unknown_level_code_raises_with_available_list(self, pack: LanguagePack) -> None:
        with pytest.raises(KeyError, match="no such thing"):
            pack.level("no such thing")


class TestZhHskSpecifics:
    """Assertions specific to the primary pack -- not part of the generic
    conformance suite because they encode facts about HSK's structure
    (cumulative levels), not facts every pack must satisfy."""

    def test_levels_are_cumulative(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        hsk1, hsk2 = pack.level("HSK1"), pack.level("HSK2")
        assert hsk1.vocabulary_ceiling <= hsk2.vocabulary_ceiling
        assert "我" in hsk2.vocabulary_ceiling  # an HSK1 word survives into HSK2

    def test_correction_strategy_shifts_from_none_to_recast(self) -> None:
        pack = load_builtin_pack("zh_hsk")
        from app.pedagogy.models import CorrectionStrategy

        assert pack.level("HSK1").correction_strategy is CorrectionStrategy.NONE
        assert pack.level("HSK3").correction_strategy is CorrectionStrategy.RECAST


class TestPackLoadErrors:
    def test_missing_directory_raises(self) -> None:
        with pytest.raises(PackLoadError, match="not found"):
            load_builtin_pack("does_not_exist")

    def test_missing_language_yaml_field_raises(self, tmp_path) -> None:
        from app.pedagogy.packs import load_pack

        pack_dir = tmp_path / "broken"
        pack_dir.mkdir()
        (pack_dir / "language.yaml").write_text(
            "target_language: en-US\nsource_language: en-US\n", encoding="utf-8"
        )  # missing level_model, tokenizer, tts_voice
        (pack_dir / "levels").mkdir()
        (pack_dir / "scenarios").mkdir()

        with pytest.raises(PackLoadError, match="level_model"):
            load_pack(pack_dir)

    def test_missing_vocabulary_file_raises(self, tmp_path) -> None:
        from app.pedagogy.packs import load_pack

        pack_dir = tmp_path / "broken2"
        (pack_dir / "levels").mkdir(parents=True)
        (pack_dir / "scenarios").mkdir()
        (pack_dir / "vocab").mkdir()
        (pack_dir / "language.yaml").write_text(
            "target_language: en-US\nsource_language: en-US\n"
            "level_model: cefr\ntokenizer: whitespace\ntts_voice: x\n",
            encoding="utf-8",
        )
        (pack_dir / "levels" / "a1.yaml").write_text(
            "code: A1\nlevel_model: cefr\nvocabulary_file: missing.txt\n"
            "max_sentence_words: 5\nspeaking_rate: 1.0\ncorrection_strategy: none\n"
            "l1_scaffolding_allowed: true\ntarget_agent_turn_words: 5\n",
            encoding="utf-8",
        )
        (pack_dir / "scenarios" / "s.yaml").write_text(
            "id: s\nobjective: x\npersona: x\nopening_line: x\n", encoding="utf-8"
        )

        with pytest.raises(PackLoadError, match="vocabulary file not found"):
            load_pack(pack_dir)
