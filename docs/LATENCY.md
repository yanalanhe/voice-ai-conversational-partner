# Latency

## Definition

**TTFA (Time To First Audio)** = wall-clock from end-of-learner-speech detection to first
audio sample played. Measured client-side in the browser HUD; server-side spans
(`app/telemetry/spans.py`) reconcile against it and decompose it into per-stage durations.

## Cascaded-mode budget (modelled, PRD Sec 5.2)

| Stage | Target p50 | Notes |
|---|---|---|
| Endpoint decision | 250 ms | Client-side VAD (`web/src/audio/vad.ts`), tunable hangover |
| STT final after endpoint | 100 ms | Streaming means partials already transmitted |
| Prompt assembly | 30 ms | Pedagogy prompt build (`app/pedagogy/prompts.py`) |
| LLM time-to-first-token | 300 ms | Streaming, warm connection |
| First clause → TTS dispatch | 60 ms | `ClauseChunker` releases on the first sentence boundary |
| TTS first audio chunk | 180 ms | Pre-warmed connection |
| Network + jitter buffer | 80 ms | |
| **Total** | **~1000 ms** | |

## What is actually measured today

The numbers above are the *modelled* per-stage targets used to configure the mock providers'
`LatencyProfile`s in `eval/latency_replay.py` (`TTFT_PROFILE`, `TTS_TTFB_PROFILE`, etc.) — they
are not a measurement of the real system. `eval/reports/example.md` contains one real,
reproducible run of `eval/latency_replay.py`, which reports the seeded mock-based p50/p95 the
CI quality gate (`eval/gates.py`) actually checks against.

Real Azure adapters now exist (`server/app/providers/azure.py`) and run the deployed English
`generic` demo, so a real number is obtainable but **has not yet been recorded**. The browser
HUD shows live TTFA and a stage breakdown for that deployment. The remaining step is to run a
fixed conversation set against it, record p50/p95, and replace the modelled figures above.
Mandarin (`zh_hsk`) latency stays modelled until the pack path is wired to real providers.

## Optimizations implemented

1. **Clause-level TTS pipelining** (`app/pipeline/chunker.py`, `app/pipeline/cascaded.py`) —
   the largest available win in cascaded mode. TTS synthesis starts on the first complete
   clause while the LLM is still generating the rest, via two overlapped `asyncio.Task`s
   joined by a queue (`cascaded.py`'s `run_turn`).
2. **Local barge-in flush** (`web/src/audio/playback.ts`) — the client stops playback the
   instant its own VAD detects speech, before the server-side cancellation round-trip
   completes. See ADR-005 for the server-side half.

## Optimizations *not* implemented in this build

- Persistent pre-warmed provider connections (the Azure adapters in `providers/azure.py` do
  not pool or pre-warm connections).
- Speculative generation on high-confidence interim transcripts.
- Scenario-opener audio caching.
- Adaptive endpointing by proficiency level. The VAD hangover is a fixed 900 ms
  (`web/src/audio/vad.ts`), configurable but not wired to `LevelPolicy`. It was raised from
  the PRD's 500 ms default because real spontaneous speech has mid-sentence pauses longer than
  that, which fragmented turns; the cost is up to 400 ms more endpointing latency. A hard cap of
  8 s per utterance (`maxSpeechMs`) stops background noise from extending a recording forever.
- Honoring `speaking_rate` in `AzureTTS` (needs SSML), so per-level speech rate is not applied.

These are documented as the next latency work, not silently dropped.

## L2 speech handling

Learner speech is accented, disfluent, and — for `zh_hsk` specifically — a wrong tone
produces a *different word*, not a mispronounced one (see ADR-006 for why pronunciation
assessment therefore has to run on raw audio, not the STT transcript). `AzureSTT` is wired up
for the English `generic` demo, but it has not been benchmarked against accented or L2 speech,
and the Mandarin pack path does not use it yet. `Transcript.is_confident`
(`app/providers/types.py`) is the hook a real STT integration would use to trigger a
clarification request rather than acting on a low-confidence hypothesis; when Azure returns no
match the orchestrator emits a `NoSpeechEvent`, which the UI shows as "didn't catch that".
