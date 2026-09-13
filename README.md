# Parlons

A voice-first AI conversation partner for second-language speaking practice. Demonstrated on
English→Mandarin (HSK 1–4); a second pack (English→French, Government of Canada SLE A/B/C)
ships alongside it to prove the language pair is configuration, not code.

**This README states plainly what is real and what is a documented design, throughout.** See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#what-is-real-vs-what-is-a-documented-design) for
the full breakdown.

## Quickstart

```
git clone <this-repo>
cd voice-ai-pipeline
docker compose up --build
```

Then open **http://localhost:5173**, click Connect, and speak. This runs entirely on mock
providers (see [ADR-003](docs/adr/0003-mock-providers-first-class.md)) — no API keys, no
cloud account, no cost. Verified end-to-end in this repo's own build history: a real
WebSocket client running a full conversation turn against the actual Docker containers,
including a real latency breakdown.

By default the demo speaks HSK1-calibrated Mandarin (the `zh_hsk` pack's `ordering_lunch`
scenario, looping). STT is mocked, so what you say doesn't change what's "recognized" — the
script is fixed regardless. For a plain English scripted conversation with no pedagogy layer
involved (useful for sanity-checking pipeline mechanics without reading Mandarin):

```
DEMO_SCRIPT=generic docker compose up --build
```

Both packs that ship (`zh_hsk`, `fr_sle`) always have English as the *source* language, never
the target — there is no "practice English" mode, since the project's whole point is an
English speaker practicing a foreign language. `generic` is the closest thing to one, and it
is deliberately not pedagogy at all, just a fixed script.

## What this demonstrates

| Capability | Where |
|---|---|
| Voice pipeline end-to-end (cascaded and/or realtime) | `server/app/pipeline/cascaded.py` — cascaded fully built; realtime is an interface with no adapter, see [ADR-004](docs/adr/0004-cascaded-and-realtime-interface.md) |
| Model portability across vendors | `server/app/providers/protocols.py` — structural `Protocol` contracts + a shared conformance suite ([ADR-002](docs/adr/0002-protocol-based-providers.md)) |
| Pedagogical calibration in the prompt layer | `server/app/pedagogy/` — versioned prompt builder, per-level vocabulary ceilings, two language packs |
| Automated evaluation harness | `eval/` — golden set, deterministic checks, LLM judge, judge-validation statistics, CI quality gates |
| RAG patterns | Cut from this build window — see the Sep 10 amendment in the design history |
| Cloud deployment | `infra/main.bicep` — Azure Container Apps, pinned to `canadacentral` |
| Maintainable codebase | 241 tests, `ruff` + `mypy --strict` clean, ADRs for every non-obvious decision |

## Architecture

```
Browser (TS, no framework) --WebSocket--> FastAPI gateway --> SessionOrchestrator
                                                                 |
                                              barge-in via asyncio.Task cancellation
                                                                 |
                                                     Cascaded pipeline (STT|LLM|TTS)
                                                                 |
                                          Protocol-typed providers (mock, ADR-003)
```

Full diagram and the "what's real vs. documented design" table:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Measured results

`eval/reports/example.md` is a committed, real run of the eval harness — not fabricated
numbers. It reports, against a scripted mock model deliberately restricted to
wordlist-safe replies:

- **Deterministic checks** (vocabulary ceiling, language leakage) pass for both packs.
- **Latency replay**: p50 ≈ 540 ms, p95 ≈ 640 ms, against seeded mock provider latency
  modelled on the budget in [`docs/LATENCY.md`](docs/LATENCY.md).
- **Judge validation: not run.** The golden set carries placeholder human labels on 8
  Mandarin turns to prove the correlation math is correct — not genuine validation. The
  report says so explicitly rather than presenting a number that would look real and isn't.

Regenerate it: `python -m eval.report`.

## Honesty notes — the things worth reading before the rest

- **No real vendor adapter (Azure, Gemini) is wired up.** Every provider in this build is a
  deterministic mock (ADR-003). The Protocol contracts and conformance suite exist
  specifically so adding one is additive, not a rewrite.
- **The primary demo language is Mandarin because the author is fluent in it** — human
  judge-validation requires being able to read what the model produced, and a project that
  fabricated validation for a language nobody on the project can check would be worse than
  one that scoped the claim honestly. The French pack proves the same architecture works for
  a language pair added without touching pipeline code.
- **The `zh_hsk` and `fr_sle` vocabulary wordlists are curated demonstration subsets**, not
  the verbatim official HSK list (licensed content) or a real SLE standard (SLE has no
  published wordlist at all). See each pack's own README under
  `server/app/pedagogy/langpacks/`.
- **RAG, native realtime, and the full vendor benchmark were cut** under a compressed build
  window, in that order, to protect the eval harness — the rarest artifact in this repo and
  the one most worth having working. See [`docs/VENDOR_BENCHMARK.md`](docs/VENDOR_BENCHMARK.md)
  for what the realtime-vs-cascaded comparison would need to become a real measurement.

## Repository layout

```
server/app/
  providers/     Protocol contracts + mock STT/LLM/TTS/Pronunciation adapters
  pipeline/      cascaded.py (clause-pipelined STT->LLM->TTS), chunker.py
  session/       orchestrator.py (turn state machine, barge-in), factory.py, events.py
  pedagogy/      packs.py, ceiling.py, prompts.py, langpacks/{zh_hsk,fr_sle}/
  state/         learner.py (profile + store), report.py (end-of-session report)
  security/      demo_guard.py (public-demo hardening)
  main.py        FastAPI WebSocket gateway
server/tests/    unit + conformance suites (159 tests)
eval/            golden set, deterministic checks, judge, gates, report generator (82 tests)
web/             TypeScript + Vite client: AudioWorklet capture, VAD, playback, latency HUD
docs/            ADRs, architecture, latency, evaluation, compliance, vendor benchmark
infra/           Azure Container Apps Bicep template + deployment instructions
```

## Running tests

```
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev,zh]"
pytest server/ eval/ -v
ruff check server/ eval/
mypy server/app server/tests eval

cd web && npm install && npx tsc --noEmit && npx vite build
```

CI (`.github/workflows/ci.yml`) runs all of the above on every push, with zero credentials
required (ADR-003).

## Deployment

**Frontend → Vercel.** Import this repo, set the project root to `web/`, and set the
`VITE_WS_URL` environment variable to the deployed backend's `wss://` URL (Vite inlines it at
build time — see `web/src/main.ts`'s `wsUrl()`).

**Backend → Azure Container Apps**, not Vercel — Vercel's serverless/edge runtimes do not
support the persistent WebSocket connection the backend needs. This was a real constraint
discovered while planning deployment, documented in
[`docs/COMPLIANCE.md`](docs/COMPLIANCE.md). See [`infra/README.md`](infra/README.md) for
step-by-step deployment instructions — **not validated against a live Azure subscription**,
since neither the Azure CLI nor the Bicep CLI was available while this was authored; run
`az bicep build` yourself first.

Before sharing a public URL, set `DEMO_ACCESS_CODE` (see
`server/app/security/demo_guard.py`) — a public voice endpoint spends real API credits for
anyone who finds it. The per-IP rate limit, per-session turn cap, and daily spend ceiling are
on by default; the access code is opt-in via an environment variable because local
development has nothing to protect.

## Documentation index

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design, what's real vs. planned
- [`docs/LATENCY.md`](docs/LATENCY.md) — the TTFA budget, what's optimized, what isn't
- [`docs/EVALUATION.md`](docs/EVALUATION.md) / [`eval/README.md`](eval/README.md) — the eval
  harness in full, including its honesty notes
- [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) — data residency, the Vercel/WebSocket finding
- [`docs/VENDOR_BENCHMARK.md`](docs/VENDOR_BENCHMARK.md) — the cascaded-vs-realtime design
  argument, and what it would take to turn it into a real measurement
- `docs/adr/` — six architecture decision records, one per non-obvious call made in this build
