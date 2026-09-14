# PRD — Parlons: Bilingual Voice AI Conversation Partner

**Status:** Draft v1.0
**Author:** Yan He
**Date:** 2026-09-07
**Build window:** 2026-09-07 → 2026-09-14 (7 days, solo)
**Repo:** `voice-ai-pipeline` (public GitHub)
**Purpose of this document:** Scope and specify a portfolio-grade MVP that demonstrates end-to-end voice AI engineering capability.

---

## 1. Context & Strategy

### 1.1 What the hiring team is actually screening for

The posting is unusually explicit about what it rejects: *"AI strategy consultants," "ML researchers without production shipping experience," "prompt engineers whose portfolio is UI-layer only," "anyone whose recent work is architecture diagrams and not code."*

This inverts the normal portfolio calculus. A polished demo video with a thin backend loses to a modest demo backed by a real pipeline, real tests, and real measurements. **The repo is the artifact; this PRD is scaffolding for it.**

### 1.2 Inferred client domain

Signals in the posting — Montreal, "federal-scale language training platform," seventeen years, French proficiency as a nice-to-have, Canadian federal data residency — point to **Government of Canada Second Language Evaluation (SLE) training**: public servants reaching oral proficiency levels **A / B / C** in their second official language.

**Design consequence:** the system is built **language-pair agnostic**, with CEFR as the default proficiency model and a **GC SLE A/B/C profile shipped alongside it as a configuration pack**. Domain specificity is demonstrated without over-committing to an inference that may be wrong.

### 1.3 A constraint that shapes the design: the author does not speak French

The JD lists French proficiency under *nice to have*; the must-have is *"strong written and verbal English."* But the constraint has a real engineering consequence, and pretending otherwise would be the wrong move:

**Quality cannot be claimed where it cannot be evaluated.** Judge validation (§6.4) requires human ground truth. Hand-labeling French turns without French competence would produce a number that looks rigorous and means nothing.

**The resolution is architectural, not cosmetic.** Everything language-specific — target language, vocabulary ceiling wordlists, level policies, scenario cards, correction strategies, TTS voice and rate — is **data, not code**. The primary demo and all judge validation run on **EN→ZH (Mandarin), where the author is fluent**; a **French pack (EN→FR, GC SLE levels) ships alongside it** to prove the configuration path works end-to-end.

This is a stronger position than a hardcoded French build. It mirrors exactly the portability discipline the JD demands of model vendors, and it makes the honest interview answer a design argument: *"the language pair is configuration; adding French was a YAML file, and I'd take pedagogical ground truth from your Innovation team — which is how the role is scoped anyway."*

### 1.4 Requirement → evidence map

Every JD requirement must be answerable by pointing at a file, not a paragraph.


| JD requirement                                                    | Evidence in repo                                                                                                                          |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Voice pipeline end-to-end, cascaded **and/or** native realtime    | `server/app/pipeline/` — both modes, one interface, runtime switch                                                                        |
| Model portability across Azure OpenAI / Gemini / specialist voice | `server/app/providers/` — Protocol-based adapters + conformance suite                                                                     |
| Integrate LLM with portal and learner-state layer                 | `server/app/state/`, `server/app/portal/`                                                                                                 |
| Pedagogical calibration in the prompt layer                       | `server/app/pedagogy/` — level policies, versioned prompts                                                                                |
| *(French nice-to-have, unmet)*                                    | `server/app/pedagogy/langpacks/` — language pair as config; French pack ships as proof                                                    |
| Automated eval harness: rubrics, held-out sets, quality gates     | `eval/` + `.github/workflows/eval.yml`                                                                                                    |
| Vendor benchmarking and architecture decisions                    | `bench/`, `docs/VENDOR_BENCHMARK.md`, `docs/adr/`                                                                                         |
| RAG patterns                                                      | **Cut** (see §8.0 amendment) — curriculum embedded directly in `server/app/pedagogy/prompts.py` instead of a separate retrieval layer     |
| Cloud, Azure preferred                                            | `infra/` — Bicep, Container Apps, Canada Central                                                                                          |
| Code the team can maintain                                        | typing, ruff/mypy strict, pytest, ADRs, CONTRIBUTING                                                                                      |
| Data residency / compliance                                       | `docs/COMPLIANCE.md`, region pinning, PII redaction                                                                                       |


---

## 2. Product Definition

### 2.1 One-line

A voice-first conversation partner that lets a learner practice spoken conversation against structured pedagogical scenarios, calibrated to their proficiency level, with **the language pair, level model, and pedagogy supplied as configuration** — demonstrated with measurable pedagogical quality and sub-second response latency.

### 2.2 Primary user story

> As a learner at CEFR **B1**, I open a scenario ("Book a meeting room with a colleague"), speak naturally, and hold a real spoken conversation with a partner that stays inside my vocabulary ceiling, gently recasts my errors without derailing the conversation, keeps me talking rather than lecturing me, and gives me a written feedback report at the end.

### 2.3 Secondary story — the one that proves the architecture

> As an engineer, I add a new language pair by writing one language pack (level policies, vocabulary ceilings, scenario cards, voice config) and changing zero lines of pipeline code. The repo ships a **French pack (EN→FR, GC SLE A/B/C)** alongside the primary demo pack to prove this.

### 2.4 Why the primary pack is EN→ZH (Mandarin)

Chosen because the author is fluent and can supply defensible ground truth — but it earns its place on technical merit, and **strengthens two requirements that would otherwise be soft**:

**1. The vocabulary ceiling becomes objectively verifiable.** CEFR has no single canonical wordlist; a "B1 vocabulary ceiling" check is inevitably hand-waved. **HSK levels 1–6 have official, published, graded wordlists** (150 / 300 / 600 / 1200 / 2500 / 5000 words). The deterministic ceiling check in EV-3 becomes a real membership test against an authoritative list rather than a heuristic — turning the strongest deterministic metric from plausible into provable.

**2. It forces genuinely voice-native pedagogy.** Mandarin is tonal, so pronunciation feedback is not decoration — it is the core pedagogical value, and it is **impossible in a text pipeline**. This is the single clearest available demonstration that the author builds *voice* AI rather than an LLM app with audio attached. **Azure AI Speech Pronunciation Assessment** supports `zh-CN` with phoneme- and tone-level scoring, which means the feature is both cheap to build and Azure-native — satisfying the JD's cloud preference with the same work.

Two secondary benefits:

- **Three level models ship** — HSK, CEFR, and GC SLE — which proves the pluggable level-model claim far more convincingly than two would.
- **Chinese has no orthographic word boundaries**, so the ceiling check requires real segmentation (`jieba`). A small thing, but it makes the deterministic evaluator non-trivial engineering rather than a `split()` call.

**The framing for the interview:** the demo language is incidental; the architecture is the point. Leading with Mandarin and shipping French proves the pair is configuration — which is a considerably stronger claim than a French build alone would have made.

### 2.5 Explicit non-goals for the MVP

- Not a full LMS, user management system, or learner-facing production UI
- Not multi-tenant, not horizontally scaled, no SLA
- No fine-tuning or model training
- No mobile clients
- Browser UI is deliberately utilitarian — the JD penalizes UI-layer portfolios; polish goes into the pipeline and eval harness instead

---

## 3. System Architecture

### 3.1 Topology

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser client (TypeScript / Vite)                              │
│  AudioWorklet capture 16k PCM · client VAD · jitter buffer       │
│  playback · barge-in signal · live latency HUD                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │  WebSocket (bidi binary audio + JSON control)
┌──────────────────────────▼───────────────────────────────────────┐
│  FastAPI Gateway  ·  SessionOrchestrator (async turn state machine)│
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  PIPELINE INTERFACE  (one contract, two implementations)     │ │
│  │                                                              │ │
│  │  CascadedPipeline          │  RealtimePipeline               │ │
│  │  STT ─stream→ LLM ─stream→ │  single duplex WS to            │ │
│  │  sentence chunker → TTS    │  Azure Realtime / Gemini Live   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                           │                                       │
│  ┌────────────┬───────────┴────┬──────────────┬────────────────┐ │
│  │ Pedagogy   │ Learner State  │  RAG         │  Telemetry     │ │
│  │ level      │ profile,       │  curriculum  │  span timers   │ │
│  │ policies,  │ error log,     │  retrieval   │  TTFA metrics  │ │
│  │ scenarios, │ mastery,       │  over units  │  transcripts   │ │
│  │ prompts    │ resumable      │              │                │ │
│  └────────────┴────────────────┴──────────────┴────────────────┘ │
└──────────────────────────┬───────────────────────────────────────┘
                           │
        ┌──────────────────┴───────────────────┐
        │  PROVIDER ADAPTER LAYER (Protocols)   │
        │  STT   Azure Speech · Deepgram · Mock │
        │  LLM   Azure OpenAI · Gemini · Mock   │
        │  TTS   Azure Speech · ElevenLabs·Mock │
        │  RT    Azure Realtime · Gemini Live   │
        └───────────────────────────────────────┘
```

### 3.2 Key architectural decisions (each becomes an ADR)

**ADR-001 — Hand-built transport instead of LiveKit/Vapi.**
LiveKit Agents would deliver a working voice loop in a day, but it *hides the exact competency being assessed*. The JD asks for someone who can "design and build the voice AI pipeline end-to-end." Building on raw WebSocket + AudioWorklet demonstrates the endpointing, chunking, and barge-in mechanics that managed platforms abstract away. LiveKit is documented as the production scaling path (WebRTC, TURN, SFU, telephony) and a `LiveKitTransport` adapter is a stretch item. *This is a deliberate trade-off and should be stated in the interview, not defended.*

**ADR-002 — Provider abstraction via** `typing.Protocol`**, not inheritance.**
Adapters are structurally typed and independently testable. A shared **conformance test suite** runs against every adapter, so adding a vendor means passing an existing contract rather than reading a wiki.

**ADR-003 — Mock providers are first-class, not test doubles.**
`MockSTT`/`MockLLM`/`MockTTS` are deterministic, seedable, and support **scripted latency injection**. This lets the entire eval harness and CI run with zero API keys and zero cost, and makes latency regression tests reproducible. This is the load-bearing decision that makes CI quality gates viable.

**ADR-004 — Both pipeline modes ship.**
Cascaded gives control, observability, cost management, and per-stage vendor swap. Realtime gives latency and prosody but weaker text-layer control (harder to enforce a vocabulary ceiling mid-stream). Shipping both with a runtime feature flag directly answers "cascaded and/or native realtime" and produces a genuine benchmark comparison.

**ADR-006 — Pronunciation assessment taps the raw audio, not the pipeline.**
Realtime APIs (Gemini Live, Azure Realtime) do STT internally and expose no stage to hook. If pronunciation feedback were built as a cascaded-pipeline stage, it would vanish the moment the mode switched.

Instead, learner audio is **forked at the transport layer** and sent to Azure Pronunciation Assessment on a side channel, in parallel with whichever pipeline is active. Results land in the learner error log asynchronously — they inform the end-of-session report and the *next* turn's prompt, never blocking the current response.

Two consequences worth stating:

- **Pedagogical features survive the mode switch.** This is the concrete answer to "how do you keep control in realtime mode."
- **It costs zero latency.** The assessment call runs off the critical path; TTFA is unaffected.

This is also why Azure AI Speech stays in the stack even when Gemini Live is handling the conversation — the two are not competing, they occupy different layers.

**ADR-005 — Truncate assistant context to audio actually delivered.**
On barge-in, the model must not believe it said words the learner never heard. Assistant turns are truncated in history at the byte offset of TTS playback interruption. Getting this wrong causes conversational drift that is invisible in testing and obvious in production.

### 3.3 Stack


| Layer              | Choice                                                      | Rationale                                    |
| ------------------ | ----------------------------------------------------------- | -------------------------------------------- |
| Server             | Python 3.12, FastAPI, asyncio                               | Matches JD stack; best async voice ecosystem |
| Client             | TypeScript, Vite, AudioWorklet                              | Demonstrates second JD language              |
| Primary cloud      | Azure — OpenAI, AI Speech, Container Apps, Canada Central   | JD: Azure-centric                            |
| Portable providers | Gemini 2.x Live + Flash, Deepgram, ElevenLabs, OpenAI       | JD: intentional portability                  |
| Storage            | SQLite (dev) → Postgres + pgvector (prod path)              | Same SQLAlchemy layer both ways              |
| Quality            | pytest, pytest-asyncio, ruff, mypy --strict, GitHub Actions | "code the team can maintain"                 |


---

## 4. Functional Requirements

### 4.1 Voice pipeline (P0)


| ID   | Requirement                                                                                                                                         |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| VP-1 | Continuous 16 kHz mono PCM capture, streamed in ≤20 ms frames over WebSocket                                                                        |
| VP-2 | Streaming STT with interim + final hypotheses; interims drive UI, finals drive turns                                                                |
| VP-3 | Endpointing: energy/webrtcvad baseline with configurable silence threshold (default 500 ms), plus a semantic endpointing hook                       |
| VP-4 | LLM response streamed token-by-token, chunked at clause/sentence boundaries and dispatched to TTS **before** generation completes                   |
| VP-5 | TTS audio streamed back and played through a jitter buffer; playback begins on first chunk                                                          |
| VP-6 | **Barge-in:** learner speech during agent playback cancels the LLM stream, flushes TTS, stops playback, and truncates assistant context per ADR-005 |
| VP-7 | Runtime mode switch (`cascaded`                                                                                                                     |
| VP-8 | Per-turn latency spans emitted for every stage boundary                                                                                             |


### 4.2 Pedagogical layer (P0)


| ID    | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PD-0  | **Language pack abstraction.** A pack is a directory of data — `language.yaml` (target/source language, TTS voice, STT locale hints), `levels/*.yaml`, `vocab/*.txt` ceilings, `scenarios/*.yaml`. Loading a pack is the only language-specific act in the system; **no language identifier appears in pipeline code**                                                                                                                                                                                                                                           |
| PD-1  | Level policies keyed to a **pluggable level model** — **three profiles ship: HSK 1–6, CEFR A1–C1, and GC SLE A/B/C**, each with an explicit cross-mapping table. Each level defines: vocabulary ceiling, max sentence complexity, TTS speaking rate, correction strategy, L1 scaffolding allowance, target agent turn length                                                                                                                                                                                                                                     |
| PD-2  | ≥3 scenario cards per pack as structured YAML: objective, target vocabulary, target grammatical structures, persona, opening line, success criteria, turn budget                                                                                                                                                                                                                                                                                                                                                                                                 |
| PD-2b | **Two packs ship:** `zh_hsk` (EN→ZH, primary — drives all demos and judge validation) and `fr_sle` (EN→FR, proving the config path). A pack-loading conformance test runs against both                                                                                                                                                                                                                                                                                                                                                                           |
| PD-6  | **Pronunciation & tone feedback (P1, voice-native).** Azure AI Speech Pronunciation Assessment scores each learner utterance for accuracy, fluency, completeness, and prosody at word and phoneme level. For `zh_hsk`, **tone errors are extracted and tracked as a distinct error category**. Scores feed the learner error log and the end-of-session report; below-threshold words are candidates for conversational recast. The pack declares whether pronunciation assessment is enabled and which locale to use — **the pipeline stays language-agnostic** |
| PD-3  | Composable, **versioned** prompt builder (`level × scenario × learner_state × retrieved_curriculum`); every prompt version is hashed and logged with each turn                                                                                                                                                                                                                                                                                                                                                                                                   |
| PD-4  | Corrective feedback policy: errors are logged silently during flow and surfaced as **conversational recasts** (level B+) or an end-of-session report — never mid-utterance interruption                                                                                                                                                                                                                                                                                                                                                                          |
| PD-5  | End-of-session report: errors by category, target-structure usage, learner talk-time ratio, level-appropriate next steps                                                                                                                                                                                                                                                                                                                                                                                                                                         |


### 4.3 Learner state & portal integration (P0/P1)


| ID   | Requirement                                                                                              | Pri |
| ---- | -------------------------------------------------------------------------------------------------------- | --- |
| LS-1 | Learner profile: id, target language, SLE level, scenario history, persistent error log, mastery signals | P0  |
| LS-2 | Sessions are resumable — reconnect restores conversation context                                         | P0  |
| LS-3 | Mock portal auth: JWT bearer with learner claims, OIDC-shaped, swappable for real Entra ID               | P1  |
| LS-4 | Feature-flag service gating pipeline mode, provider selection, and prompt version per cohort             | P1  |
| LS-5 | Outbound webhook posting session summary back to the portal                                              | P1  |


### 4.4 RAG over pedagogical content (P1)


| ID   | Requirement                                                                                                     |
| ---- | ----------------------------------------------------------------------------------------------------------------- |
| RG-1 | Small curriculum corpus (~30 units: grammar notes, functional phrases, vocabulary sets) indexed with embeddings |
| RG-2 | Retrieval keyed on scenario + learner's active error categories, injected into the system prompt                |
| RG-3 | Retrieved unit ids logged per turn for traceability — answers "why did it teach that?"                          |
| RG-4 | Grounding guard: agent must not invent grammar rules absent from the corpus (checked by eval)                   |


### 4.5 Evaluation harness (P0 — the differentiator)


| ID    | Requirement                                                                                                                                                                                                                                                                                          |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| EV-1  | Held-out golden set: ≥50 conversation turns across levels/scenarios, with expected-behavior annotations, versioned in-repo and **never used for prompt tuning**                                                                                                                                      |
| EV-2  | LLM-as-judge scoring on the rubric in §6.2, structured output, temperature 0, judge prompt versioned                                                                                                                                                                                                 |
| EV-3  | Deterministic checks needing no LLM: **vocabulary-ceiling violation rate — for** `zh_hsk`**, a true membership test against official HSK graded wordlists after** `jieba` **segmentation**; agent words-per-turn, learner:agent talk ratio, target-structure elicitation rate, language-leakage rate |
| EV-3b | **Pronunciation metrics** from Azure assessment on the L2 audio set: mean accuracy score, tone-error rate (`zh_hsk`), and their stability across STT providers                                                                                                                                       |
| EV-4  | Latency replay: mock providers with recorded per-stage latency distributions produce reproducible TTFA percentiles in CI                                                                                                                                                                             |
| EV-5  | **Judge validation:** ~50 hand-labeled turns; report Spearman ρ and exact-agreement between judge and human. Target ρ ≥ 0.7                                                                                                                                                                          |
| EV-6  | Quality gates fail CI on regression (thresholds in §6.3)                                                                                                                                                                                                                                             |
| EV-7  | STT accuracy on **L2/accented speech** — WER measured on a small learner-speech set, reported per provider                                                                                                                                                                                           |
| EV-8  | HTML + Markdown report artifact per run, committed under `eval/reports/`                                                                                                                                                                                                                             |


### 4.6 Vendor benchmark (P1)

`bench/` CLI runs a fixed conversation set across provider combinations and emits `docs/VENDOR_BENCHMARK.md`:


| Combination                          | TTFA p50 | TTFA p95 | WER (L2) | Judge score | $/10-min session |
| ------------------------------------ | -------- | -------- | -------- | ----------- | ---------------- |
| Azure STT + Azure OpenAI + Azure TTS |          |          |          |             |                  |
| Deepgram + Azure OpenAI + ElevenLabs |          |          |          |             |                  |
| Azure OpenAI Realtime (native)       |          |          |          |             |                  |
| Gemini Live (native)                 |          |          |          |             |                  |


Deliverable is the **filled-in table plus a written recommendation** — that is what "contribute to vendor benchmarking and architecture decisions" means in practice.

### 4.6.1 The hypothesis the benchmark is built to test

> **Realtime buys latency and pays in pedagogical control.**

In cascaded mode the vocabulary ceiling is enforceable — agent text exists before it is spoken, so it can be checked and, if needed, regenerated. In realtime mode there is no text checkpoint: the ceiling can only be *requested* in the system prompt and *measured* after the fact from the output transcript.

The benchmark should therefore report, per mode:


| Metric                                   | Expectation                                   |
| ----------------------------------------- | ---------------------------------------------- |
| TTFA p50 / p95                           | Realtime substantially better                 |
| Vocabulary-ceiling violation rate        | Cascaded substantially better                 |
| Judge score — level appropriateness      | Cascaded better                               |
| Judge score — conversational naturalness | Realtime better (prosody, faster turn-taking) |


**If that tradeoff holds, the recommendation writes itself:** realtime for advanced learners where fluency practice dominates and the ceiling barely binds; cascaded for beginners where staying inside 300 words is the entire pedagogical point. Routed per learner level by feature flag.

A defended per-cohort recommendation is a materially stronger artifact than "realtime is faster."

---

## 5. Latency Budget

The single most credible signal of having shipped voice is a measured, decomposed latency budget.

### 5.1 Definition

**TTFA (Time To First Audio)** = wall-clock from *end-of-learner-speech detection* to *first audio sample played in the browser*. Measured client-side; server spans reconcile against it.

### 5.2 Cascaded budget


| Stage                       | Target p50   | Notes                                                    |
| --------------------------- | ------------ | -------------------------------------------------------- |
| Endpoint decision           | 250 ms       | Dominant, tunable; trades latency against false cut-offs |
| STT final after endpoint    | 100 ms       | Streaming means partials already transmitted             |
| Prompt assembly + RAG       | 30 ms        | Cached embeddings, warm index                            |
| LLM time-to-first-token     | 300 ms       | Warm connection, streaming                               |
| First clause → TTS dispatch | 60 ms        | Chunk on first clause boundary, not full response        |
| TTS first audio chunk       | 180 ms       | Pre-warmed persistent connection                         |
| Network + jitter buffer     | 80 ms        |                                                          |
| **Total**                   | **~1000 ms** |                                                          |


### 5.3 Targets


| Mode              | TTFA p50 | TTFA p95  |
| ----------------- | -------- | --------- |
| Cascaded          | ≤ 900 ms | ≤ 1400 ms |
| Realtime (native) | ≤ 450 ms | ≤ 800 ms  |


These are honest targets for a one-week build on commodity endpoints, not aspirational marketing numbers. Reporting a real p95 of 1300 ms with a decomposition is stronger than claiming 500 ms without one.

### 5.4 Optimizations implemented (and named in the docs)

1. **Clause-level TTS pipelining** — dispatch to TTS on the first clause boundary rather than awaiting full generation. Largest single win in cascaded mode.
2. **Persistent pre-warmed provider connections** — pooled STT/TTS sockets; cold connection setup is ~200–400 ms of hidden latency.
3. **Eager speculative generation with cancellation** — begin LLM generation on a high-confidence interim transcript, cancel if the final differs materially.
4. **Scenario opener caching** — first agent utterance per scenario is pre-synthesized; session start feels instant.
5. **Adaptive endpointing** — longer silence threshold at level A (learners hesitate mid-sentence), shorter at level C. Pedagogically motivated *and* a latency lever.

### 5.5 L2 speech handling (domain-specific risk)

Learner speech is accented, disfluent, self-correcting, and code-switched. Generic STT degrades badly, and hallucinated transcripts are worse than none.

For `zh_hsk` this is sharper than usual: **a wrong tone is a different word.** An L2 learner saying *mǎi* (买, buy) as *mài* (卖, sell) produces a transcript that is fluent, plausible, and wrong — and an STT engine's language model will often silently "correct" it to whatever fits context, erasing the exact error the learner needs to hear about. This is why pronunciation assessment (PD-6) runs on the **audio**, in parallel with STT, rather than being inferred from the transcript. Naming this failure mode is itself a strong signal of voice-specific experience.

- Phrase-list / custom-vocabulary biasing seeded from scenario target vocabulary
- Explicit expected-language hint with code-switch tolerance
- Confidence thresholding → agent asks a natural clarification (`"Pardon, peux-tu répéter ?"`) instead of responding to a garbled transcript
- WER on the L2 set is a first-class benchmark column, not an afterthought

---

## 6. Evaluation Design

### 6.1 Layers


| Layer                            | What it catches                                    | Cost    | Runs                         |
| -------------------------------- | -------------------------------------------------- | ------- | ---------------------------- |
| Unit / conformance               | Adapter contract breaks                            | free    | every push                   |
| Deterministic pedagogical checks | Vocabulary ceiling, turn economy, language leakage | free    | every push                   |
| Latency replay                   | Performance regressions                            | free    | every push                   |
| LLM-judge rubric                 | Pedagogical quality                                | ~$1/run | PR + nightly                 |
| Judge validation                 | Whether the judge itself is trustworthy            | manual  | once, re-run on judge change |
| Live smoke                       | Real provider integration                          | ~$0.50  | nightly                      |


### 6.2 Rubric (0–4 per dimension)


| Dimension                       | Question                                                                          |
| -------------------------------- | ----------------------------------------------------------------------------------- |
| **Level appropriateness**       | Does vocabulary and syntax stay within the learner's ceiling?                     |
| **Corrective feedback quality** | Are errors handled with appropriate strategy, neither ignored nor over-corrected? |
| **Task progression**            | Did the turn advance the scenario's pedagogical objective?                        |
| **Conversational naturalness**  | Does it converse rather than lecture? Is turn economy right?                      |
| **Language & persona fidelity** | Stays in target language and role; no unsolicited L1                              |
| **Groundedness & safety**       | No invented grammar rules; no off-curriculum drift                                |


### 6.3 CI quality gates

```yaml
composite_judge_score:        ">= 3.2 / 4.0"
min_any_dimension:            ">= 2.8 / 4.0"
vocab_ceiling_violation_rate: "<= 5%"
language_leakage_rate:        "<= 2%"
ttfa_p95_cascaded_replay:     "<= 1400 ms"
ttfa_p95_regression:          "<= +15% vs main"
adapter_conformance:          "100% pass"
```

### 6.4 Why judge validation matters

Most LLM-eval portfolios stop at "we use an LLM judge." Almost none ask whether the judge agrees with a human. Hand-labeling 50 turns and reporting correlation is a few hours of work and is the strongest available signal of eval maturity — it is the difference between having a metric and having a *trustworthy* metric.

### 6.5 Evaluation scope, stated honestly

The eval harness is language-agnostic; the **ground truth is not**.


| Pack             | Deterministic checks                                                                                 | LLM-judge rubric  | Human-validated judge                |
| ---------------- | ---------------------------------------------------------------------------------------------------- | ----------------- | ------------------------------------- |
| `zh_hsk` (EN→ZH) | ✅ **strongest** — official HSK wordlists make the ceiling check authoritative                        | ✅                 | ✅ ~50 hand-labeled turns, ρ reported |
| `fr_sle` (EN→FR) | ✅ — leakage/turn-economy checks are language-independent; ceiling check uses a best-effort CEFR list | ✅ scores produced | ❌ **not human-validated**            |


`docs/EVALUATION.md` states this limitation in plain language, and the French report carries an "unvalidated judge" banner rather than a bare score.

This is a feature of the write-up, not an apology. Knowing which of your numbers you can defend — and labeling the ones you can't — is a senior signal.

---

## 7. Compliance & Data Residency

Addresses the "Canadian federal data residency" nice-to-have. Documented in `docs/COMPLIANCE.md`.

- **Region pinning:** all Azure resources in `canadacentral`; startup assertion fails fast on a non-Canadian endpoint
- **PII redaction:** learner utterances pass a redaction filter before any log write or third-party judge call
- **Audio retention:** `RETAIN_AUDIO` defaults to `false`; audio is processed in-memory and discarded post-turn
- **Provider data-handling matrix:** per-vendor table of training-data-usage, retention, and available regions — the exact analysis a federal client requires before vendor approval
- **Deletion path:** learner-scoped hard delete endpoint

Framed honestly as *"what a real deployment would require, prototyped"* — not as a compliance claim.

---

## 8. Delivery Plan

### 8.0 Amendment — 2026-09-10

Original window was Sep 7–14. Build started Sep 10, so this is a **5-day plan**, re-scoped around a deployed public demo.

**Deployment (new requirement).**


| Tier     | Host                                      | Note                                                           |
| -------- | ------------------------------------------ | ---------------------------------------------------------------- |
| Frontend | **Vercel**                                | Static Vite build; account already held                        |
| Backend  | **Azure Container Apps**, `canadacentral` | WebSocket-capable; serves the Azure + data-residency narrative |


**Finding to document in** `COMPLIANCE.md`**, not hide:** Vercel's serverless and edge runtimes do not support persistent WebSocket servers, so the audio transport cannot live there. This is a real platform constraint that forced a split deployment — exactly the kind of tradeoff worth showing the reasoning for. The rejected alternative (browser connects directly to Gemini Live via ephemeral token) would deploy entirely on Vercel but removes the server-side pipeline, which is the competency being demonstrated.

**Public-demo hardening (new, ~30 min).** A public voice endpoint spends real API credits for anyone who finds it. Required before the URL is shared: shared access code, per-session turn cap, per-IP rate limit, and a global daily spend ceiling that fails closed.

**Scope change — realtime mode is deferred.**

`RealtimeProvider` ships as a **protocol and a documented design**, with no adapter implemented. Consequences, stated plainly so the repo does not overclaim:

- **ADR-004 weakens** from "both modes ship" to "the interface admits both; cascaded is implemented." The contract is real and the seam is visible, but the second implementation is future work.
- **§4.6.1's benchmark hypothesis becomes a stated design question rather than a measured result.** The control-vs-latency tradeoff is argued in `docs/ARCHITECTURE.md`; it is not claimed as evidence.
- If Day 5 runs ahead, a Gemini Live adapter is ~3h and restores both. Highest-value stretch item in the plan.

**Also cut:** RAG (degrades to curriculum embedded in the prompt), vendor benchmark (reduced to a cost/latency table from the cascaded path only).

**Explicitly retained:** provider abstraction, barge-in, latency instrumentation, **the full eval harness including judge validation**, and both language packs. The harness is the rarest artifact in the repo and runs offline in CI.

**Revised schedule**


| Day    | Scope                                                                  |
| ------ | ---------------------------------------------------------------------- |
| Sep 10 | Skeleton, Protocols, mock providers, text loop, tests, CI              |
| Sep 11 | Real audio, streaming STT/TTS, barge-in, latency spans, browser client |
| Sep 12 | Pedagogy layer, `zh_hsk` + `fr_sle` packs, learner state               |
| Sep 13 | Eval harness, CI gates, judge validation                               |
| Sep 14 | Deploy (Vercel + ACA), demo hardening, README, demo recording          |


---

### 8.1 Original plan (superseded)

Anchored to the original window: **Mon Sep 7 → Mon Sep 14, 2026**.


| Day               | Milestone                                                    | Definition of done                                                                                                                                                                                                        |
| ----------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** (Sep 7)     | Skeleton + provider abstraction + **mock providers**         | End-to-end *text* loop runs on mocks with zero API keys; conformance suite green                                                                                                                                          |
| **2** (Sep 8)     | Real audio in/out, streaming STT + TTS                       | Spoken turn works end-to-end in browser; TTFA instrumented and printed                                                                                                                                                    |
| **3** (Sep 9)     | Barge-in, turn state machine, latency optimizations          | Interruption works cleanly; context truncation correct; clause-level TTS pipelining live                                                                                                                                  |
| **4** (Sep 10)    | Pedagogy layer + **language packs** + learner state          | `zh_hsk` pack (3 scenarios, HSK 1–4 policies, official wordlists, jieba ceiling check), versioned prompts, resumable sessions, end-of-session report. `fr_sle` **stubbed and loading green in the pack conformance test** |
| **5** (Sep 11)    | **Eval harness + CI gates**                                  | Golden set, judge, deterministic checks, latency replay, GitHub Actions green with gates enforced                                                                                                                         |
| **6** (Sep 12)    | Realtime mode + RAG + **pronunciation feedback** + benchmark | Both pipeline modes switchable; curriculum retrieval live; Azure Pronunciation Assessment wired with tone-error tracking in the session report; benchmark table populated                                                |
| **7** (Sep 13–14) | Docs, ADRs, judge validation, French pack, deploy, demo      | README with GIF, ADRs written, judge correlation reported **on the primary pack with scope stated**, French pack completed and its (unvalidated) eval report published, deployed to Container Apps, 3-min demo video      |


### 8.1 Risk register


| Risk                                              | Impact                             | Mitigation                                                                                                                                                                 |
| ------------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Browser audio plumbing consumes 2+ days           | Critical — starves the eval work   | **Day 1 is mock-based text loop.** Audio is swapped into a working system, never blocking it                                                                               |
| Realtime API access/quota unavailable             | Loses a headline feature           | Cascaded is P0 and complete on its own; realtime is P1 behind a flag                                                                                                       |
| Eval harness gets cut for time                    | Loses the strongest differentiator | Scheduled Day 5, *before* realtime and RAG. If time runs out, realtime is cut instead                                                                                      |
| API spend                                         | Minor                              | Mocks for all CI; budget ~$40 for development and benchmarking                                                                                                             |
| Scope creep into UI polish                        | Directly penalized by JD           | UI is capped at: scenario picker, transcript, latency HUD, session report                                                                                                  |
| Pronunciation assessment turns into a rabbit hole | Loses Day 6                        | Strictly P1, strictly Azure's managed API — no custom acoustic modeling. If it slips, tone errors degrade to an LLM-judged transcript heuristic with the limitation stated |
| HSK wordlist licensing / sourcing                 | Minor                              | Use openly published HSK 1–4 lists, cite the source in the pack README, ship the list file in-repo for reproducibility                                                     |


### 8.2 Cut order if the week compresses

Cut from the bottom, never the top:

1. Native realtime mode → cascaded alone still satisfies "and/or"
2. RAG → prompt-embedded curriculum instead
3. Vendor benchmark → reduce to two combinations
4. Azure deployment → local Docker Compose + recorded demo
5. **Never cut:** eval harness, latency instrumentation, provider abstraction, barge-in, **the French pack** — it is a few YAML files and it is the entire answer to the one nice-to-have you don't meet

---

## 9. Repository Layout

```
voice-ai-pipeline/
├── README.md                    demo GIF, quickstart, measured results table
├── docs/
│   ├── PRD.md  ARCHITECTURE.md  LATENCY.md
│   ├── EVALUATION.md  VENDOR_BENCHMARK.md  COMPLIANCE.md
│   └── adr/0001…0005.md
├── server/app/
│   ├── providers/   protocols.py · azure/ gemini/ deepgram/ elevenlabs/ mock/
│   ├── pipeline/    cascaded.py · realtime.py · chunker.py · endpointing.py
│   ├── session/     orchestrator.py · turn_state.py · bargein.py
│   ├── pedagogy/    levels.py · prompts/ · feedback.py · pronunciation.py
│   │   └── langpacks/
│   │        ├── zh_hsk/   language.yaml · levels/hsk1-4.yaml
│   │        │              vocab/hsk{1..4}.txt (official) · scenarios/*.yaml
│   │        └── fr_sle/   ← proves pack path, zero pipeline code change
│   │   └── levelmodels/  hsk.yaml · cefr.yaml · gc_sle.yaml · crossmap.yaml
│   ├── rag/         index.py · retriever.py · corpus/
│   ├── state/       models.py · learner_store.py · session_store.py
│   ├── portal/      auth.py · flags.py · webhooks.py
│   └── telemetry/   spans.py · metrics.py
├── server/tests/    unit · conformance · integration
├── eval/
│   ├── datasets/    golden_turns.jsonl · human_labels.jsonl · l2_audio/
│   ├── rubrics/     pedagogical_v1.yaml
│   ├── runners/     judge.py · deterministic.py · latency_replay.py · validate_judge.py
│   └── reports/
├── bench/           run_benchmark.py · configs/
├── web/             AudioWorklet capture · VAD · player · latency HUD
├── infra/           Dockerfile · compose.yaml · main.bicep
└── .github/workflows/  ci.yml · eval.yml · nightly.yml
```

---

## 10. Success Criteria

The MVP succeeds if an engineer cloning the repo can, in under ten minutes:

1. Run a full voice conversation locally
2. Switch cascaded ↔ realtime with one config change
3. Swap a provider by adding one adapter file
4. Run `make eval` and see rubric scores, deterministic metrics, and latency percentiles
5. See CI enforcing quality gates on every PR
6. Read `docs/VENDOR_BENCHMARK.md` and find a measured recommendation with numbers behind it

And critically: **every claim in the README is backed by a number produced by code in the repo.**
