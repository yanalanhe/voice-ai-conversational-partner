# ADR-005: Truncate assistant context to audio actually delivered on barge-in

**Status:** Accepted

## Context

When a learner interrupts the agent mid-reply, the agent's conversation history
(`SessionOrchestrator._messages`) must not record the full text of a turn that was never
fully spoken. If it does, the model's next turn is built on a false premise — it believes it
already said things the learner never heard, which produces confusing, repetitive, or
inconsistent follow-up replies that are invisible in text-only testing and glaring in a real
spoken conversation.

## Decision

On barge-in, the assistant message for the interrupted turn is never appended to
conversation history at all. `SessionOrchestrator._run_turn` only calls
`self._messages.append(Message(role=Role.ASSISTANT, ...))` after the full reply has streamed
through `run_turn()` to completion (`app/session/orchestrator.py`); a cancelled turn's
`async for` loop never reaches that line, so nothing is appended.

## Rationale

This is simpler and more robust than the originally-envisioned approach (truncating the
assistant message to the exact character offset the TTS had reached at interrupt time,
tracked via `SynthesisChunk.text` — see `app/providers/types.py`'s docstring on that field,
which was designed to make offset tracking possible). The simpler policy — omit the turn
entirely rather than truncate it — avoids ever inserting a mid-sentence fragment into history
that could itself confuse the next turn's prompt. `SynthesisChunk.text` remains available for
a future, more granular truncation strategy if partial-turn credit turns out to matter in
practice.

## Consequences

- `server/tests/unit/test_orchestrator.py::TestBargeIn
  ::test_interrupted_turn_does_not_pollute_history` asserts this directly: after a barge-in,
  history contains only the learner's turn, never a partial or garbled assistant reply.
- The learner's interrupting speech is not lost either: `on_speech_start` buffers up to
  `_BARGE_IN_BUFFER_FRAMES` (~2s) of audio captured while the agent was still speaking and
  replays it into the new utterance's STT stream — see
  `test_buffered_audio_during_speaking_is_replayed_after_bargein`.
- Cancellation itself is delivered via `asyncio.Task.cancel()`, which surfaces at the
  orchestrator's call site as a plain `asyncio.CancelledError` regardless of whether
  `run_turn()` raised the more specific `BargeInError` internally — Task-boundary
  cancellation collapses any `CancelledError` subclass into the base type. The orchestrator
  does not need the subclass's identity to know why it cancelled the task (it initiated the
  cancellation itself), so this is a non-issue in practice, but it is a real asyncio
  subtlety worth documenting: `BargeInError` is only observable as itself when caught
  *inline within the same task*, never across a Task boundary — see
  `test_cascaded_pipeline.py`'s two barge-in tests for a worked demonstration of both cases.
