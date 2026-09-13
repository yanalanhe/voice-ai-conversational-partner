# ADR-004: One pipeline interface, two intended implementations — cascaded shipped, realtime deferred

**Status:** Accepted (revised 2026-09-10)

## Context

The JD asks for a pipeline that is "cascaded (STT + LLM + TTS) and/or native realtime." The
original plan (PRD Sec 3, pre-amendment) was to ship both modes behind a runtime switch, with
a benchmark comparing them. The build window compressed from 7 days to 5 partway through
(PRD Sec 8.0), which forced a scope cut.

## Decision

Ship the cascaded pipeline (`app/pipeline/cascaded.py`) fully implemented and tested.
Ship the `RealtimeProvider` contract (ADR-002) as a complete, documented interface with zero
adapters implementing it — no Gemini Live or Azure Realtime integration in this build.

## Rationale (original, for the record)

Cascaded mode buys a text checkpoint: agent text exists before it is spoken, so a
vocabulary-ceiling check can in principle regenerate a bad reply before it reaches TTS (see
`app/pedagogy/ceiling.py` and PRD Sec 4.6.1). Realtime mode gives up that checkpoint for
lower latency — there is no stage at which text exists to check. The intended benchmark
(PRD Sec 4.6.1) would have measured this trade-off directly: TTFA and vocabulary-ceiling
violation rate, cascaded vs. realtime, per learner level.

## What actually shipped

- **Cascaded**: fully implemented, with the clause-level TTS pipelining that produces its
  main latency win (`app/pipeline/chunker.py`, `app/pipeline/cascaded.py`), barge-in via task
  cancellation (ADR-005), and 63+ tests across the pipeline, orchestrator, and gateway layers.
- **Realtime**: the `RealtimeProvider` Protocol is written and documented
  (`app/providers/protocols.py`) with a clear statement of what it would need to guarantee
  (full-duplex audio, server-side interrupt handling). No adapter exists. The control-vs-
  latency trade-off argued above is therefore a **design argument**, not a measured result —
  `docs/VENDOR_BENCHMARK.md` states this plainly rather than presenting synthetic or
  extrapolated numbers as a benchmark.

## Consequences

- The repo does not demonstrate a working realtime voice loop. This is disclosed, not hidden,
  in the PRD amendment, this ADR, and `docs/VENDOR_BENCHMARK.md`.
- A Gemini Live adapter is the highest-value remaining stretch item: the interface is proven
  correct by its own conformance expectations (ADR-002), and `SessionOrchestrator` was
  designed to accept either pipeline mode without its turn-taking or barge-in logic changing
  — see `app/session/orchestrator.py`'s docstring on transport-agnosticism.
- ADR-006 (pronunciation assessment taps raw audio at the transport layer, not inside either
  pipeline) was written specifically so this cut would not also break tone/pronunciation
  feedback if realtime mode is added later — that feature does not live inside
  `cascaded.py` and would not need to be duplicated inside a future realtime pipeline.
