# ADR-002: Provider abstraction via `typing.Protocol`, not inheritance

**Status:** Accepted

## Context

The system needs to swap STT/LLM/TTS vendors (Azure AI Speech, Azure OpenAI, Gemini,
Deepgram, ElevenLabs) without touching the pipeline or orchestrator that consume them. The
JD states this requirement explicitly: "Azure-centric with intentional model portability
across Azure OpenAI, Google Gemini, and specialist voice platforms."

## Decision

Define four structural contracts in `server/app/providers/protocols.py`
(`STTProvider`, `LLMProvider`, `TTSProvider`, `RealtimeProvider`, plus
`PronunciationProvider`) using `typing.Protocol` with `@runtime_checkable`, rather than an
abstract base class hierarchy. An adapter is a plain class that structurally satisfies the
contract — no base class to import, no framework to buy into.

## Rationale

Structural typing means adding a vendor is "write a class with these methods and this
signature," verified by `isinstance(adapter, Protocol)` at runtime and by the shared
conformance suite (`server/tests/conformance/test_provider_conformance.py`) — not "inherit
from `BaseSTTProvider` and implement its abstract hooks in whatever way the base class
expects." This keeps every adapter (mock or real) independently testable and prevents the
protocol from accumulating framework-specific assumptions over time.

Note that `RealtimeProvider`'s contract (`converse(audio) -> AsyncIterator[SynthesisChunk |
Transcript]`) is deliberately *not* expressed as the other three composed together — a native
realtime API does STT, inference, and synthesis inside one connection with no seam between
them, and pretending otherwise would make the abstraction lie about what the vendor does.

## Consequences

- `server/tests/conformance/test_provider_conformance.py` runs the same test suite against
  every STT/LLM/TTS adapter, parametrized by name. Today that means the mock providers only —
  see ADR-003 and the PRD's Sep 10 amendment for why no real adapter (Azure, Gemini) shipped
  in this build window. Adding one means adding it to the parametrize list and making it pass.
- The conformance suite enforces the exact behavioral guarantees the pipeline depends on
  (e.g. "cancellation stops generation promptly" — see `TestLLMConformance
  .test_cancellation_stops_generation_promptly`), not just "the method exists."
- `RealtimeProvider` currently has zero adapters implementing it — see ADR-004. The contract
  exists and is documented; building a Gemini Live adapter against it is the natural next step.
