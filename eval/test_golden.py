from __future__ import annotations

from pathlib import Path

import pytest
from app.pedagogy.packs import load_builtin_pack

from eval.golden import GoldenSetError, load_golden_set, turns_with_human_labels


class TestLoadGoldenSetRealFile:
    def test_loads_the_shipped_dataset(self) -> None:
        turns = load_golden_set()
        assert len(turns) >= 30

    def test_every_turn_references_a_loadable_pack(self) -> None:
        turns = load_golden_set()
        for turn in turns:
            pack = load_builtin_pack(turn.pack)
            assert turn.level in pack.levels
            assert turn.scenario in pack.scenarios

    def test_covers_both_packs(self) -> None:
        turns = load_golden_set()
        packs = {t.pack for t in turns}
        assert packs == {"zh_hsk", "fr_sle"}

    def test_ids_are_unique(self) -> None:
        turns = load_golden_set()
        ids = [t.id for t in turns]
        assert len(ids) == len(set(ids))

    def test_human_labeled_subset_is_zh_hsk_only(self) -> None:
        """Matches the project's documented honesty stance: fr_sle carries no
        human labels because nobody on this project can validate French."""
        turns = load_golden_set()
        labeled = turns_with_human_labels(turns)
        assert labeled  # the subset is non-empty
        assert all(t.pack == "zh_hsk" for t in labeled)


class TestLoadGoldenSetErrors:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GoldenSetError, match="not found"):
            load_golden_set(tmp_path / "nope.jsonl")

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        with pytest.raises(GoldenSetError, match="no golden turns"):
            load_golden_set(path)

    def test_comment_and_blank_lines_are_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "with_comments.jsonl"
        path.write_text(
            "# a header comment\n"
            "\n"
            '{"id": "a", "pack": "zh_hsk", "level": "HSK1", "scenario": "s", '
            '"learner_utterance": "hi"}\n',
            encoding="utf-8",
        )
        turns = load_golden_set(path)
        assert len(turns) == 1
        assert turns[0].id == "a"

    def test_invalid_json_line_raises_with_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.jsonl"
        path.write_text("not json\n", encoding="utf-8")
        with pytest.raises(GoldenSetError, match=r"bad\.jsonl:1"):
            load_golden_set(path)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "incomplete.jsonl"
        path.write_text('{"id": "a", "pack": "zh_hsk"}\n', encoding="utf-8")
        with pytest.raises(GoldenSetError, match="missing required field"):
            load_golden_set(path)

    def test_duplicate_ids_raise(self, tmp_path: Path) -> None:
        path = tmp_path / "dupes.jsonl"
        entry = (
            '{"id": "a", "pack": "zh_hsk", "level": "HSK1", "scenario": "s", '
            '"learner_utterance": "hi"}\n'
        )
        path.write_text(entry + entry, encoding="utf-8")
        with pytest.raises(GoldenSetError, match="duplicate turn ids"):
            load_golden_set(path)

    def test_history_must_be_a_list(self, tmp_path: Path) -> None:
        path = tmp_path / "bad_history.jsonl"
        path.write_text(
            '{"id": "a", "pack": "zh_hsk", "level": "HSK1", "scenario": "s", '
            '"learner_utterance": "hi", "history": "not a list"}\n',
            encoding="utf-8",
        )
        with pytest.raises(GoldenSetError, match="'history' must be a list"):
            load_golden_set(path)


class TestTurnsWithHumanLabels:
    def test_filters_correctly(self) -> None:
        from eval.schema import GoldenTurn

        turns = [
            GoldenTurn(id="a", pack="p", level="L", scenario="s", learner_utterance="x"),
            GoldenTurn(
                id="b", pack="p", level="L", scenario="s", learner_utterance="x",
                human_labels={"level_appropriateness": 3},
            ),
        ]
        labeled = turns_with_human_labels(turns)
        assert [t.id for t in labeled] == ["b"]
