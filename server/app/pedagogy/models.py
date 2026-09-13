"""Data shapes for the pedagogy layer (PRD PD-0..PD-2b).

Everything language-specific is data, not code. A `LanguagePack` is loaded
from a directory of YAML + wordlist files (see packs.py); pipeline code
downstream (the orchestrator, the cascaded pipeline) never branches on a
language identifier -- it only ever sees a `LevelPolicy` or a `Scenario`
object handed to it by whatever pack was configured. Swapping the target
language is swapping which directory gets loaded, nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CorrectionStrategy(str, Enum):
    """When and how the agent surfaces a learner's errors (PD-4).

    Never mid-utterance interruption -- see PRD PD-4. RECAST folds a
    correction into the next conversational turn ("Ah, you WENT to the
    store?"); END_OF_SESSION defers everything to the session report; NONE
    disables corrective feedback entirely (used at the lowest levels, where
    interrupting flow to correct grammar does more harm than good).
    """

    RECAST = "recast"
    END_OF_SESSION = "end_of_session"
    NONE = "none"


class Tokenizer(str, Enum):
    """How a pack's text is split into words for the vocabulary-ceiling check.

    A pack declares which strategy applies to it; ceiling.py dispatches on
    this declared property, not on a hardcoded language name -- see
    ceiling.py's module docstring for why that distinction matters.
    """

    WHITESPACE = "whitespace"
    JIEBA = "jieba"  # required for CJK packs, which have no word boundaries


@dataclass(frozen=True, slots=True)
class LevelPolicy:
    """Pedagogical calibration for one proficiency level (PD-1).

    `vocabulary_ceiling` is already cumulative by the time this object
    exists -- packs.py resolves "everything up to and including this level"
    at load time, so callers never need to know the level ordering.
    """

    code: str  # e.g. "HSK2", "B", "B1" -- meaningful only within level_model
    level_model: str  # "hsk" | "gc_sle" | "cefr"
    vocabulary_ceiling: frozenset[str]
    max_sentence_words: int
    speaking_rate: float
    correction_strategy: CorrectionStrategy
    l1_scaffolding_allowed: bool
    target_agent_turn_words: int


@dataclass(frozen=True, slots=True)
class Scenario:
    """One structured pedagogical scenario card (PD-2)."""

    id: str
    objective: str
    persona: str
    opening_line: str
    target_vocabulary: tuple[str, ...] = ()
    target_structures: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    turn_budget: int = 12


@dataclass(frozen=True, slots=True)
class LanguagePack:
    """A fully loaded language pack (PD-0).

    `name` is the pack's directory name (e.g. "zh_hsk") and is the only place
    in the running system a language identifier lives as a first-class,
    human-chosen string -- everywhere else it's an opaque key into this
    object's fields.
    """

    name: str
    target_language: str  # BCP-47, e.g. "zh-CN"
    source_language: str  # BCP-47, e.g. "en-US"
    level_model: str
    tokenizer: Tokenizer
    tts_voice: str
    levels: dict[str, LevelPolicy] = field(default_factory=dict)
    scenarios: dict[str, Scenario] = field(default_factory=dict)

    def level(self, code: str) -> LevelPolicy:
        try:
            return self.levels[code]
        except KeyError:
            raise KeyError(
                f"pack {self.name!r} has no level {code!r}; available: "
                f"{sorted(self.levels)}"
            ) from None

    def scenario(self, scenario_id: str) -> Scenario:
        try:
            return self.scenarios[scenario_id]
        except KeyError:
            raise KeyError(
                f"pack {self.name!r} has no scenario {scenario_id!r}; available: "
                f"{sorted(self.scenarios)}"
            ) from None
