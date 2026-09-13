# ADR-003: Mock providers are first-class components, not test doubles

**Status:** Accepted

## Context

Running the full test suite, the eval harness, and the CI quality gates against real Azure
OpenAI / Azure Speech / Gemini endpoints would require every contributor (and every CI run)
to provision credentials and pay per invocation. It would also make latency regression tests
non-deterministic — real providers jitter, so a measured p95 cannot fail a build
reproducibly.

## Decision

`server/app/providers/mock.py` implements `MockSTT`, `MockLLM`, `MockTTS`, and
`MockPronunciation` as complete, deterministic, seedable implementations of the Protocol
contracts (ADR-002) — not `unittest.mock.Mock` objects, not fixtures that happen to satisfy
an interface. Each carries a `LatencyProfile` (mean + stdev) that it samples from a seeded
`random.Random`, so a given seed always requests the same sequence of delays.

## Rationale

This is the single decision that makes everything else in the repo possible without a cloud
account:

- **The entire CI pipeline runs on zero credentials and zero spend** — see
  `.github/workflows/ci.yml`. 217 tests, the full eval harness, and the quality gates
  (`eval/gates.py`) all execute against mocks.
- **Latency regression testing is reproducible.** `eval/latency_replay.py` runs synthetic
  turns through the real cascaded pipeline with seeded mock latency, producing a p50/p95 that
  is stable across runs to within real event-loop scheduling jitter (a few ms — see that
  module's docstring and `eval/test_latency_replay.py`'s determinism test for the exact
  tolerance; `asyncio.sleep()` is a lower bound, not an exact wait, so bit-for-bit identical
  wall-clock output was never achievable and the test asserts the tolerance that is).
- **Deliberately-bad mock output proves the checks actually fire.** `echo_level_check` (Day 1)
  and the `bad_reply` responder in `eval/test_gates.py` construct known-bad output and assert
  the relevant check catches it — a check that has never been observed to fail has never been
  proven to check anything.

## Consequences

- Every mock's `sleep()` calls are real `asyncio.sleep()`, not virtual/instant — this was a
  deliberate choice (see the module docstring: "Every sleep here is deliberate. Removing them
  would make tests faster and worthless") but it does mean latency-simulating test files
  (`test_latency_replay.py`, `test_gates.py`, `test_report_generator.py`) cost real wall-clock
  time and must keep `n` small in unit tests, reserving larger `n` for the actual eval run.
- No real adapter has been built or tested against a live vendor in this build window (see the
  PRD's Sep 10 amendment cutting realtime mode and reprioritizing the eval harness). The
  Protocol contracts and conformance suite (ADR-002) are what make adding one later a matter
  of writing the adapter and passing the existing suite, not inventing new test infrastructure.
