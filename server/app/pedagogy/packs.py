"""Loads a language pack directory into a `LanguagePack` object.

This module is the ONLY place in the codebase that reads a language
identifier from configuration and turns it into behavior. Everything
downstream (prompts.py, ceiling.py, the orchestrator) operates on the
resulting `LanguagePack`/`LevelPolicy`/`Scenario` objects and never touches a
language string again -- see PD-0.

Expected directory layout (see langpacks/zh_hsk/ and langpacks/fr_sle/ for
worked examples):

    <pack_name>/
        language.yaml           target/source language, level_model, tokenizer, tts voice
        levels/*.yaml           one file per level; order encodes cumulative rank
        vocab/*.txt             wordlists referenced by levels/*.yaml
        scenarios/*.yaml        one file per scenario
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.pedagogy.models import (
    CorrectionStrategy,
    LanguagePack,
    LevelPolicy,
    Scenario,
    Tokenizer,
)


class PackLoadError(Exception):
    """Raised with an actionable message on any malformed pack."""


def _read_yaml(path: Path) -> dict[str, object]:
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        raise PackLoadError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PackLoadError(f"{path} must contain a YAML mapping, got {type(data).__name__}")
    return data


def _read_wordlist(path: Path) -> frozenset[str]:
    """One token per line. Blank lines and '#'-prefixed comments are skipped."""
    if not path.is_file():
        raise PackLoadError(f"vocabulary file not found: {path}")
    words: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            words.add(stripped)
    return frozenset(words)


def _load_levels(pack_dir: Path) -> dict[str, LevelPolicy]:
    """Load levels/*.yaml in filename order, making each level's ceiling
    cumulative over every level that sorts before it.

    Filename order is the deliberate ordering mechanism (e.g. hsk1.yaml <
    hsk2.yaml < hsk3.yaml) -- it is simple, visible in a directory listing,
    and avoids inventing a second, separate "rank" field that could drift out
    of sync with the files themselves.
    """
    levels_dir = pack_dir / "levels"
    if not levels_dir.is_dir():
        raise PackLoadError(f"missing levels/ directory in {pack_dir}")

    levels: dict[str, LevelPolicy] = {}
    cumulative_vocab: set[str] = set()

    for level_file in sorted(levels_dir.glob("*.yaml")):
        data = _read_yaml(level_file)
        try:
            code = str(data["code"])
            level_model = str(data["level_model"])
            vocab_file = str(data["vocabulary_file"])
            max_sentence_words = int(data["max_sentence_words"])  # type: ignore[call-overload]
            speaking_rate = float(data["speaking_rate"])  # type: ignore[arg-type]
            correction_strategy = CorrectionStrategy(data["correction_strategy"])
            l1_scaffolding_allowed = bool(data["l1_scaffolding_allowed"])
            target_agent_turn_words = int(data["target_agent_turn_words"])  # type: ignore[call-overload]
        except KeyError as exc:
            raise PackLoadError(f"{level_file} missing required field {exc}") from exc
        except ValueError as exc:
            raise PackLoadError(f"{level_file} has an invalid value: {exc}") from exc

        cumulative_vocab |= _read_wordlist(pack_dir / "vocab" / vocab_file)

        levels[code] = LevelPolicy(
            code=code,
            level_model=level_model,
            vocabulary_ceiling=frozenset(cumulative_vocab),
            max_sentence_words=max_sentence_words,
            speaking_rate=speaking_rate,
            correction_strategy=correction_strategy,
            l1_scaffolding_allowed=l1_scaffolding_allowed,
            target_agent_turn_words=target_agent_turn_words,
        )

    if not levels:
        raise PackLoadError(f"no levels/*.yaml files found in {pack_dir}")
    return levels


def _load_scenarios(pack_dir: Path) -> dict[str, Scenario]:
    scenarios_dir = pack_dir / "scenarios"
    if not scenarios_dir.is_dir():
        raise PackLoadError(f"missing scenarios/ directory in {pack_dir}")

    scenarios: dict[str, Scenario] = {}
    for scenario_file in sorted(scenarios_dir.glob("*.yaml")):
        data = _read_yaml(scenario_file)
        try:
            scenario = Scenario(
                id=str(data["id"]),
                objective=str(data["objective"]),
                persona=str(data["persona"]),
                opening_line=str(data["opening_line"]),
                target_vocabulary=tuple(data.get("target_vocabulary", ())),  # type: ignore[arg-type]
                target_structures=tuple(data.get("target_structures", ())),  # type: ignore[arg-type]
                success_criteria=tuple(data.get("success_criteria", ())),  # type: ignore[arg-type]
                turn_budget=int(data.get("turn_budget", 12)),  # type: ignore[call-overload]
            )
        except KeyError as exc:
            raise PackLoadError(f"{scenario_file} missing required field {exc}") from exc
        scenarios[scenario.id] = scenario

    if not scenarios:
        raise PackLoadError(f"no scenarios/*.yaml files found in {pack_dir}")
    return scenarios


def load_pack(pack_dir: str | Path) -> LanguagePack:
    """Load a complete language pack from disk.

    Raises `PackLoadError` with a message naming the exact file and field at
    fault -- a pack author should never need to read this module's source to
    fix a typo.
    """
    pack_dir = Path(pack_dir)
    if not pack_dir.is_dir():
        raise PackLoadError(f"pack directory not found: {pack_dir}")

    lang = _read_yaml(pack_dir / "language.yaml")
    try:
        target_language = str(lang["target_language"])
        source_language = str(lang["source_language"])
        level_model = str(lang["level_model"])
        tokenizer = Tokenizer(lang["tokenizer"])
        tts_voice = str(lang["tts_voice"])
    except KeyError as exc:
        raise PackLoadError(f"{pack_dir / 'language.yaml'} missing required field {exc}") from exc

    return LanguagePack(
        name=pack_dir.name,
        target_language=target_language,
        source_language=source_language,
        level_model=level_model,
        tokenizer=tokenizer,
        tts_voice=tts_voice,
        levels=_load_levels(pack_dir),
        scenarios=_load_scenarios(pack_dir),
    )


LANGPACKS_ROOT = Path(__file__).parent / "langpacks"


def load_builtin_pack(name: str) -> LanguagePack:
    """Load one of the packs shipped in server/app/pedagogy/langpacks/."""
    return load_pack(LANGPACKS_ROOT / name)
