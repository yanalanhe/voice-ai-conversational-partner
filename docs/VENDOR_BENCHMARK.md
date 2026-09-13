# Vendor Benchmark

## Status: design argument, not a measured benchmark

The original plan (PRD Sec 4.6) called for a table comparing cascaded vs. realtime pipelines,
and multiple STT/LLM/TTS vendor combinations, on TTFA, vocabulary-ceiling violation rate,
judge score, and cost. **None of that has been measured**, because no real vendor adapter
(Azure OpenAI, Azure AI Speech, Gemini, Deepgram, ElevenLabs) was built in this compressed
build window — see ADR-003 and the PRD's Sep 10 amendment, which explicitly traded the
vendor benchmark away to protect the eval harness.

What follows is the reasoning that benchmark was meant to test, stated as a design argument
instead of evidence. Presenting synthetic or estimated numbers as "benchmark results" would
misrepresent what this repo actually demonstrates; this page says plainly what was reasoned
about versus what was run.

## The hypothesis (PRD Sec 4.6.1)

> Realtime buys latency and pays in pedagogical control.

In cascaded mode, agent text exists before it is spoken — a vocabulary-ceiling violation
(`app/pedagogy/ceiling.py`) could in principle be caught and the reply regenerated before TTS
ever runs. In realtime mode there is no such checkpoint (see ADR-004): the ceiling can only be
*requested* in the system prompt and *measured* after the fact from whatever transcript the
vendor surfaces.

If this holds under real measurement, the expected shape is:

| Metric | Expected direction |
|---|---|
| TTFA p50 / p95 | Realtime substantially better |
| Vocabulary-ceiling violation rate | Cascaded substantially better |
| Judge score — level appropriateness | Cascaded better |
| Judge score — conversational naturalness | Realtime better (prosody, faster turn-taking) |

**The implied recommendation, if the hypothesis holds:** route by learner level — realtime for
advanced learners where fluency dominates and the ceiling barely binds, cascaded for
beginners where staying inside a small vocabulary is the entire pedagogical point.

## What would be needed to actually run this

1. A real LLM adapter (Azure OpenAI or Gemini) satisfying `LLMProvider`
   (`app/providers/protocols.py`), passing the existing conformance suite
   (`server/tests/conformance/test_provider_conformance.py`).
2. A real `RealtimeProvider` adapter (ADR-004) — currently zero exist.
3. Running `eval/latency_replay.py`-equivalent measurement against both, and
   `eval/deterministic.py` + `eval/judge.py` against the same golden set
   (`eval/datasets/golden_turns.jsonl`), per level.
4. Reporting the resulting table here, replacing this page's "expected direction" column with
   measured numbers and a citation of the run that produced them.

## Azure region availability finding

One real, concrete finding from this build: verify whether realtime voice models are
available in `canadacentral` before assuming both modes can share the same region-pinned
deployment (`infra/main.bicep`) — see `docs/COMPLIANCE.md`. If they are not, that is a direct
conflict between the latency goal and the data-residency requirement, which is exactly the
kind of constraint a federal client would actually hit. This has not been verified in this
build window and is listed here as required follow-up, not resolved.
