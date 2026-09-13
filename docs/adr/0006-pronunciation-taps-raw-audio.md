# ADR-006: Pronunciation assessment taps the raw audio, not the pipeline

**Status:** Accepted (feature not yet wired to a real provider — see Consequences)

## Context

Mandarin is tonal: a wrong tone produces a different word, not a mispronounced one (买 "buy"
vs. 卖 "sell"), and a general-purpose STT engine's language model will often silently
"correct" the transcript to whatever fits context — erasing exactly the error the learner
needs feedback on. Pronunciation and tone feedback therefore cannot be inferred from the STT
transcript; it needs to run on the audio itself.

Realtime voice APIs (Gemini Live, Azure Realtime) do speech recognition internally and expose
no intermediate transcript stage to hook into (see ADR-004). If pronunciation assessment were
built as a stage inside the cascaded pipeline, it would disappear the moment a realtime
adapter was added.

## Decision

Learner audio is forked at the transport layer and sent to a `PronunciationProvider`
(`app/providers/protocols.py`) on a side channel, running in parallel with whichever pipeline
mode is active, never blocking the turn in progress. `PronunciationScore` carries
`tone_errors` as a distinct field, populated only for tonal-language packs that request it.

## Rationale

This keeps pronunciation feedback a transport-layer concern rather than a pipeline-mode
concern, so it survives the cascaded/realtime switch (ADR-004) without duplication, and it
costs zero latency on the turn-taking critical path — the assessment call runs off to the
side and its result is available for the *next* turn's prompt and the end-of-session report
(`app/state/report.py`), not the current one.

## Consequences

- `MockPronunciation` (`app/providers/mock.py`) implements the full contract, including
  scripted tone-error responses used in tests (`test_mock_providers.py
  ::TestMockPronunciation::test_scripted_score_forces_recast`).
- **No real provider is wired up.** Azure AI Speech Pronunciation Assessment is the intended
  target (it supports `zh-CN` phoneme- and tone-level scoring and is Azure-native), but this
  build window did not include Azure credentials or an integration test against the live
  service — see the PRD's Sep 10 amendment and `docs/COMPLIANCE.md` for what a production
  deployment would still need to verify (region availability, latency budget for the side
  channel).
- The transport-layer fork itself (duplicating learner audio to a second consumer without
  affecting the primary STT stream) is not implemented in `server/app/session/orchestrator.py`
  today — `on_audio_frame` routes frames to exactly one destination (the active STT queue).
  Wiring the fork is a small, well-scoped addition once a real `PronunciationProvider` exists
  to send the second copy to.
