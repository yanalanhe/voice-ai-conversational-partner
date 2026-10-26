# Vendor Benchmark

## Status: design argument, not a measured benchmark

The original plan (PRD Sec 4.6) called for a table comparing cascaded vs. realtime pipelines,
and multiple STT/LLM/TTS vendor combinations, on TTFA, vocabulary-ceiling violation rate,
judge score, and cost. **None of that has been measured.** Azure AI Speech (STT and TTS) and
Azure OpenAI adapters were added on Sep 13 (`server/app/providers/azure.py`) and run the
deployed English demo, but that is a single vendor combination, not a comparison. No Gemini,
Deepgram or ElevenLabs adapter exists, and no realtime adapter exists, so there is nothing yet
to benchmark them against. See ADR-003 and the PRD's Sep 10 amendment, which explicitly traded
the vendor benchmark away to protect the eval harness.

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

1. A second real LLM adapter (Gemini) beside the existing `AzureLLM`, satisfying `LLMProvider`
   (`app/providers/protocols.py`) and the conformance suite. The Azure adapters already have
   live conformance tests (`server/tests/conformance/test_azure_live.py`), which run only with
   credentials and are skipped in CI; the shared offline suite
   (`server/tests/conformance/test_provider_conformance.py`) covers the mocks.
2. A real `RealtimeProvider` adapter (ADR-004) — currently zero exist.
3. The Azure adapters wired into the pedagogy path, not just the English `generic` demo, so
   the golden set can run through a real model.
4. Running `eval/latency_replay.py`-equivalent measurement against both modes, and
   `eval/deterministic.py` + `eval/judge.py` against the same golden set
   (`eval/datasets/golden_turns.jsonl`), per level.
5. Reporting the resulting table here, replacing this page's "expected direction" column with
   measured numbers and a citation of the run that produced them.

## Azure region availability finding

Two real, concrete findings from this build:

1. **Azure OpenAI is not offered in `canadacentral`.** The model resource had to be created in
   `canadaeast`, while Azure Speech and the Container App stay in `canadacentral`. A strictly
   single-region deployment is therefore not possible for the LLM; both regions are in Canada,
   so the residency intent holds, but it is a split (stated in `docs/COMPLIANCE.md`).
2. **Model availability and quota differ per subscription.** `gpt-4o-mini` was retired for new
   deployments, `gpt-4.1-nano` had zero quota, and `gpt-4.1-mini` (GlobalStandard) was the
   one that deployed. Check `az cognitiveservices usage list --location canadaeast` before
   choosing a model.

Still unverified: whether realtime voice models are available in either Canadian region. If
they are not, that is a direct conflict between the latency goal and the data-residency
requirement, which is exactly the kind of constraint a federal client would actually hit. It is
listed here as required follow-up, not resolved.
