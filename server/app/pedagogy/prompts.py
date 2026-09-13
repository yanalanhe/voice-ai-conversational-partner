"""Composable, versioned system-prompt builder (PRD PD-3).

`build_system_prompt` is pure: (pack, level, scenario, learner) -> prompt text
+ a content hash of that exact text. Logging the hash alongside every turn
(see session/orchestrator.py) means a later regression can always be traced
to "which exact prompt template produced this" without diffing timestamps.

RAG-retrieved curriculum content is accepted as an optional parameter and
appended verbatim if given, but is not required -- PRD Sec 8.0 amendment cuts
RAG to a stretch item; this function does not need to change when that lands,
which is the point of keeping it as an optional parameter now rather than
bolting it on later.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.pedagogy.models import CorrectionStrategy, LanguagePack, LevelPolicy, Scenario

# Bump this when the template WORDING changes in a way that should be
# distinguishable in eval history even if the hash of a specific rendering
# happens to collide (it won't, in practice, but this keeps intent explicit).
TEMPLATE_VERSION = 1

_CORRECTION_INSTRUCTIONS = {
    CorrectionStrategy.RECAST: (
        "If the learner makes a grammar or vocabulary error, do not correct it "
        "directly. Instead, naturally recast the correct form back into your "
        "next reply, the way a native speaker would in casual conversation."
    ),
    CorrectionStrategy.END_OF_SESSION: (
        "Do not correct the learner's errors during the conversation. Keep the "
        "conversation flowing naturally; errors will be reviewed afterward."
    ),
    CorrectionStrategy.NONE: (
        "Do not correct the learner's errors in any way. Focus entirely on "
        "keeping the conversation simple, warm, and easy to follow."
    ),
}


@dataclass(frozen=True, slots=True)
class BuiltPrompt:
    text: str
    version_hash: str


def build_system_prompt(
    pack: LanguagePack,
    level: LevelPolicy,
    scenario: Scenario,
    *,
    learner_name: str | None = None,
    retrieved_curriculum: str | None = None,
) -> BuiltPrompt:
    lines = [
        f"You are a conversation partner helping a learner practice {pack.target_language}.",
        f"Persona: {scenario.persona}",
        f"Scenario objective: {scenario.objective}",
        "",
        f"The learner's proficiency level is {level.code} ({level.level_model}). "
        f"Stay strictly within their vocabulary: use only words a {level.code} "
        f"learner would know, and keep sentences to roughly "
        f"{level.max_sentence_words} words or fewer.",
        f"Keep your own turns short -- aim for about {level.target_agent_turn_words} "
        "words per reply. The learner should be doing most of the talking.",
        _CORRECTION_INSTRUCTIONS[level.correction_strategy],
    ]

    if not level.l1_scaffolding_allowed:
        lines.append(
            f"Stay entirely in {pack.target_language}. Do not switch to "
            f"{pack.source_language}, even if the learner does."
        )

    if scenario.target_vocabulary:
        lines.append(
            "Try to naturally elicit these words or phrases from the learner: "
            + ", ".join(scenario.target_vocabulary)
        )
    if scenario.target_structures:
        lines.append(
            "Try to naturally elicit these grammatical structures: "
            + ", ".join(scenario.target_structures)
        )

    lines.append(f"Budget roughly {scenario.turn_budget} conversational turns for this scenario.")

    if learner_name:
        lines.append(f"The learner's name is {learner_name}.")

    if retrieved_curriculum:
        lines.append("")
        lines.append("Relevant curriculum material to draw on:")
        lines.append(retrieved_curriculum)

    text = "\n".join(lines)
    version_hash = hashlib.sha256(f"v{TEMPLATE_VERSION}:{text}".encode()).hexdigest()[:16]
    return BuiltPrompt(text=text, version_hash=version_hash)
