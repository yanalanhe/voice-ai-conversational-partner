# Architecture

## Topology

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser client (TypeScript + Vite, no framework)                │
│  AudioWorklet capture (16kHz PCM) · energy-based VAD              │
│  jitter-buffered playback with instant local flush on barge-in    │
│  live TTFA + stage-breakdown HUD                                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │  WebSocket: binary PCM frames + JSON control
┌──────────────────────────▼───────────────────────────────────────┐
│  FastAPI gateway (server/app/main.py)                             │
│  Thin transport shim -- translates wire protocol <-> orchestrator │
│  method calls. Contains no turn-taking or pedagogy logic itself.  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  SessionOrchestrator (server/app/session/orchestrator.py)         │
│  Transport-agnostic turn state machine: listening <-> speaking,   │
│  barge-in via asyncio.Task cancellation (ADR-005), message        │
│  history, an optional on_turn_complete hook for pedagogy checks   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
        ┌──────────────────┴───────────────────┐
        │  Cascaded pipeline (ADR-004)          │
        │  STT --stream--> LLM --stream-->      │
        │  ClauseChunker --stream--> TTS         │
        │  (clause-level pipelining, see         │
        │  LATENCY.md 5.4.1)                     │
        └──────────────────┬────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  Provider layer (typing.Protocol, ADR-002)                        │
│  STTProvider · LLMProvider · TTSProvider · PronunciationProvider  │
│  Mock implementations (ADR-003) ship and are fully tested;        │
│  no real vendor adapter (Azure, Gemini) is wired up in this build │
└────────────────────────────────────────────────────────────────────┘

        ┌───────────────────────────────────────────────┐
        │  Pedagogy layer (server/app/pedagogy/)         │
        │  LanguagePack loader · vocabulary-ceiling check │
        │  versioned prompt builder · zh_hsk & fr_sle     │
        │  packs (data, not code -- see PD-0 in the PRD)  │
        └───────────────────────────────────────────────┘

        ┌───────────────────────────────────────────────┐
        │  Eval harness (eval/)                          │
        │  Golden set -> generate -> deterministic +      │
        │  judge scoring -> quality gates -> report       │
        │  (see EVALUATION.md)                            │
        └───────────────────────────────────────────────┘
```

## Design principles that show up everywhere in the code

**Language is configuration, never a branch in pipeline code.** No file under
`app/pipeline/` or `app/session/` contains a language identifier. The pedagogy layer
(`app/pedagogy/packs.py`) is the only place a language string is read and turned into
behavior — see PD-0 in the PRD and the two shipped packs, `zh_hsk` and `fr_sle`.

**Providers are structurally typed, not inherited.** See ADR-002. A vendor adapter is a class
that satisfies a `Protocol`, verified by a shared conformance suite
(`server/tests/conformance/`), not a subclass of a framework base.

**Every provider used in CI is a real, deterministic implementation of its contract, not a
patched-over test double.** See ADR-003. This is what makes the eval harness and the full
test suite runnable with zero credentials and zero API spend.

**Barge-in is a first-class state, not an afterthought.** `SessionOrchestrator` buffers
learner audio captured while the agent is speaking and replays it into the interrupting
utterance; the interrupted turn is never partially recorded into conversation history (ADR-005).

## What is real vs. what is a documented design

| Component | Status |
|---|---|
| Cascaded pipeline, barge-in, clause-level TTS pipelining | Fully implemented, tested |
| Provider Protocol contracts + conformance suite | Fully implemented, tested |
| Mock STT/LLM/TTS/Pronunciation providers | Fully implemented, tested |
| Pedagogy layer, both language packs | Fully implemented, tested |
| Eval harness (golden set, deterministic checks, judge, gates) | Fully implemented, tested |
| Browser client (capture, VAD, playback, HUD) | Fully implemented |
| Real vendor adapters (Azure, Gemini) | **Not built** — see ADR-003 |
| Realtime pipeline mode | **Interface only, no adapter** — see ADR-004 |
| Pronunciation assessment wired to a real provider | **Not built** — see ADR-006 |
| RAG / curriculum retrieval | **Cut** — see PRD Sec 8.0 amendment |

This table exists so nothing in this repo is discovered to be a stub by surprise.
