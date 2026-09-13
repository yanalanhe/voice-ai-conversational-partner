"""Outbound events the orchestrator emits.

The orchestrator is transport-agnostic (see orchestrator.py docstring): it
writes these onto an `asyncio.Queue` and knows nothing about WebSockets. The
FastAPI gateway drains the queue and serializes each event onto the wire.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.types import SynthesisChunk


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    """A learner utterance was finalized by STT."""

    text: str


@dataclass(frozen=True, slots=True)
class AssistantAudioEvent:
    """One clause of agent audio, ready to play."""

    chunk: SynthesisChunk


@dataclass(frozen=True, slots=True)
class TurnCompleteEvent:
    """A turn finished normally. `summary` is a TurnTimeline.summary()."""

    summary: dict[str, object]


@dataclass(frozen=True, slots=True)
class TurnInterruptedEvent:
    """A turn was cut short by barge-in. `summary` still carries whatever
    latency marks were captured before cancellation, plus barged_in=True."""

    summary: dict[str, object]


@dataclass(frozen=True, slots=True)
class NoSpeechEvent:
    """STT returned an empty final transcript -- nothing recognizable in the
    utterance. Distinct from simply not emitting anything: a real STT
    provider can legitimately hear silence, noise, or unclear audio, and the
    learner deserves to know their turn wasn't dropped silently (mocks never
    trigger this in practice, since scripted utterances are never empty)."""


OrchestratorEvent = (
    TranscriptEvent | AssistantAudioEvent | TurnCompleteEvent | TurnInterruptedEvent | NoSpeechEvent
)
