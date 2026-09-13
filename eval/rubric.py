"""Loads the rubric YAML (eval/rubrics/*.yaml) into a typed structure.

Separated from judge.py so both the judge and any future rubric-authoring
tooling share one loader, and so the rubric file format has exactly one place
that understands it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

RUBRICS_ROOT = Path(__file__).parent / "rubrics"


@dataclass(frozen=True, slots=True)
class RubricDimension:
    id: str
    question: str


@dataclass(frozen=True, slots=True)
class Rubric:
    version: int
    scale: str
    dimensions: tuple[RubricDimension, ...]

    @property
    def dimension_ids(self) -> tuple[str, ...]:
        return tuple(d.id for d in self.dimensions)


def load_rubric(name: str = "pedagogical_v1") -> Rubric:
    path = RUBRICS_ROOT / f"{name}.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    dimensions = tuple(
        RubricDimension(id=str(d["id"]), question=str(d["question"])) for d in data["dimensions"]
    )
    return Rubric(version=int(data["version"]), scale=str(data["scale"]), dimensions=dimensions)
