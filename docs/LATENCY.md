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
are not yet a measurement against a real deployed system, because no real vendor adapter is
wired up (see ADR-003, ADR-004). `eval/reports/example.md` contains one real, reproducible run
of `eval/latency_replay.py`, which reports the seeded mock-based p50/p95 the CI quality gate
(`eval/gates.py`) actually checks against.

**Getting a real, deployed p95** is the natural next measurement once a real STT/LLM/TTS
adapter exists: swap the mock providers for real ones in `_default_orchestrator`
(`server/app/main.py`), run the same conversation set, and report the number this file would
otherwise be estimating.

## Optimizations implemented

1. **Clause-level TTS pipelining** (`app/pipeline/chunker.py`, `app/pipeline/cascaded.py`) —
   the largest available win in cascaded mode. TTS synthesis starts on the first complete
   clause while the LLM is still generating the rest, via two overlapped `asyncio.Task`s
   joined by a queue (`cascaded.py`'s `run_turn`).
2. **Local barge-in flush** (`web/src/audio/playback.ts`) — the client stops playback the
   instant its own VAD detects speech, before the server-side cancellation round-trip
   completes. See ADR-005 for the server-side half.

## Optimizations *not* implemented in this build

- Persistent pre-warmed provider connections (no real provider connections exist yet).
- Speculative generation on high-confidence interim transcripts.
- Scenario-opener audio caching.
- Adaptive endpointing by proficiency level (the VAD hangover is a fixed 500 ms today,
  configurable but not wired to `LevelPolicy`).

These are documented as the next latency work, not silently dropped.

## L2 speech handling

Learner speech is accented, disfluent, and — for `zh_hsk` specifically — a wrong tone
produces a *different word*, not a mispronounced one (see ADR-006 for why pronunciation
assessment therefore has to run on raw audio, not the STT transcript). No real STT adapter has
been benchmarked against accented or L2 speech in this build; `Transcript.is_confident`
(`app/providers/types.py`) is the hook a real STT integration would use to trigger a
clarification request rather than acting on a low-confidence hypothesis.
