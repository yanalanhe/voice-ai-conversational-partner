# ADR-001: Hand-built transport instead of LiveKit/Vapi/ElevenLabs Agents

**Status:** Accepted

## Context

A managed voice platform (LiveKit Agents, Vapi, ElevenLabs Agents) would deliver a working
voice loop in a fraction of the time this repo took: WebRTC transport, endpointing, and often
barge-in come built in. The JD lists these platforms as qualifying experience, and using one
would be a legitimate, defensible choice for a production system under time pressure.

## Decision

Build the transport layer by hand: raw WebSocket + browser `AudioWorklet`, a hand-rolled
turn state machine (`server/app/session/orchestrator.py`), and barge-in implemented via
explicit `asyncio.Task` cancellation (see ADR-005).

## Rationale

The JD asks for someone who can "design and build the voice AI pipeline end-to-end" and
explicitly filters out portfolios that are "architecture diagrams and not code." A managed
platform would hide exactly the mechanics being assessed: audio framing, endpointing, the
clause-level TTS pipelining that produces the latency win in `app/pipeline/cascaded.py`, and
the barge-in state machine in `app/session/orchestrator.py`. Building it by hand makes those
mechanics visible, testable, and the actual subject of code review.

## Consequences

- No WebRTC, no TURN/STUN, no SFU — the WebSocket transport does not scale to production
  telephony or handle NAT traversal the way LiveKit would. This is an explicit, disclosed
  trade-off, not an oversight.
- Every piece of the transport (capture, VAD, playback, jitter buffering) had to be written
  and tested from scratch — see `web/src/audio/*.ts` and `server/app/session/orchestrator.py`.
- A `LiveKitTransport` adapter is the natural next step for a production deployment; the
  orchestrator's transport-agnostic design (it knows nothing about WebSockets, only about
  `on_audio_frame`/`on_speech_start`/`on_speech_end` and an outbound event queue) means adding
  one would not require touching turn-taking or barge-in logic at all.
