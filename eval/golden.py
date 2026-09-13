"""Loads the held-out golden set (PRD EV-1).

`datasets/golden_turns.jsonl` is versioned in-repo and never used for prompt
tuning -- editing it to make a failing eval pass defeats its entire purpose.
If a turn's expected behavior turns out to be wrong, fix the annotation and
say so in the commit message; don't quietly loosen it to dodge a red gate.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.schema import GoldenTurn

DATASETS_ROOT = Path(__file__).parent / "datasets"


class GoldenSetError(Exception):
    pass


def _turn_from_dict(data: dict[str, object], line_no: int, path: Path) -> GoldenTurn:
    try:
        history_raw = data.get("history", [])
        if not isinstance(history_raw, list):
            raise GoldenSetError(f"{path}:{line_no}: 'history' must be a list")
        history = tuple((str(pair[0]), str(pair[1])) for pair in history_raw)

        return GoldenTurn(
            id=str(data["id"]),
            pack=str(data["pack"]),
            level=str(data["level"]),
            scenario=str(data["scenario"]),
            learner_utterance=str(data["learner_utterance"]),
            history=history,
            expected_behavior=str(data.get("expected_behavior", "")),
            human_labels=data.get("human_labels"),  # type: ignore[arg-type]
        )
    except KeyError as exc:
        raise GoldenSetError(f"{path}:{line_no}: missing required field {exc}") from exc


def load_golden_set(path: str | Path | None = None) -> list[GoldenTurn]:
    """Load every turn from a JSONL golden-set file.

    Blank lines and lines starting with '#' are skipped, so the file can
    carry section-header comments without breaking JSONL parsers that expect
    one JSON value per non-blank line -- this loader is intentionally more
    lenient than strict JSONL for that one case.
    """
    path = Path(path) if path is not None else DATASETS_ROOT / "golden_turns.jsonl"
    if not path.is_file():
        raise GoldenSetError(f"golden set not found: {path}")

    turns: list[GoldenTurn] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GoldenSetError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        turns.append(_turn_from_dict(data, line_no, path))

    if not turns:
        raise GoldenSetError(f"{path} contains no golden turns")

    ids = [t.id for t in turns]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise GoldenSetError(f"{path} has duplicate turn ids: {dupes}")

    return turns


def turns_with_human_labels(turns: list[GoldenTurn]) -> list[GoldenTurn]:
    """The subset used for judge validation (EV-5)."""
    return [t for t in turns if t.human_labels]
