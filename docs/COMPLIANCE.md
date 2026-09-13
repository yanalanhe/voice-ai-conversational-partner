# Compliance & Data Residency

Written as "what a real deployment would require, prototyped and reasoned about" — not as a
compliance certification. Nothing here should be read as a claim that this repo meets any
formal Canadian federal data-residency standard; it is the analysis a real engagement would
need to do, done honestly at portfolio scope.

## Platform constraint found during this build

**Vercel's serverless and edge runtimes do not support persistent WebSocket servers.** This
was discovered, not assumed, while planning deployment (see the PRD's Sep 10 amendment): the
audio transport (`server/app/main.py`) holds one long-lived connection per session and cannot
be represented as a serverless function invocation.

**Resolution:** split deployment. The static frontend (`web/`) deploys to Vercel; the
WebSocket-capable backend deploys to Azure Container Apps in `canadacentral`, which is
Azure's stated cloud preference in the JD and also gives the backend a concrete data-residency
story.

**Rejected alternative:** the browser could connect directly to a realtime voice API (Gemini
Live) via an ephemeral token minted by a Vercel API route, which would deploy entirely on
Vercel. This was rejected because it removes the server-side pipeline entirely — it would be
a demo of the vendor's product, not of the system this repo is meant to demonstrate.

## Region pinning

The Azure infra-as-code (`infra/main.bicep`) pins every resource to `canadacentral`. This is
declared in the template, not merely intended — a deployment targeting a different region
would require an explicit parameter change, not silently drift.

## PII and audio handling

- **Audio retention**: no audio frame is written to disk or persisted anywhere in this build.
  `AudioChunk` objects exist only in memory for the duration of a turn
  (`app/providers/types.py`, `app/session/orchestrator.py`) and are discarded once consumed.
  A production system that needed to retain audio (for QA review, dispute resolution) would
  need to add this deliberately and would need a retention policy, not inherit one implicitly.
- **Transcript logging**: turn text flows into `LearnerProfile.messages`
  (`app/state/learner.py`) for session resumability (LS-2), held in an in-memory
  `LearnerStore`. There is no redaction step today, and no persistent storage backend —
  `LearnerStore` is explicitly documented as the interface a Postgres-backed store would need
  to satisfy, not a production data store itself.
- **No PII redaction filter is implemented.** A real deployment handling federal-employee
  data would need one before any transcript reached a third-party LLM-judge call in the eval
  harness (`eval/judge.py`) — this is a known gap, not an oversight papered over.

## Provider data-handling

No vendor has been contracted or integrated in this build (see ADR-003), so there is no
provider data-handling matrix to report with real terms. A production deployment would need
one row per vendor (Azure OpenAI, Azure AI Speech, Gemini, any specialist voice platform)
covering: training-data usage of submitted content, retention period, available regions, and
whether a Business Associate/Data Processing Agreement is in place. This table is a
placeholder for that analysis, not a stand-in for having done it:

| Vendor | Training data usage | Retention | Available in `canadacentral` | DPA in place |
|---|---|---|---|---|
| Azure OpenAI | *not yet reviewed* | *not yet reviewed* | Yes (Azure OpenAI is regionally deployable) | *not yet reviewed* |
| Azure AI Speech | *not yet reviewed* | *not yet reviewed* | Yes | *not yet reviewed* |
| Gemini | *not yet reviewed* | *not yet reviewed* | No (Google Cloud region, not Azure) | *not yet reviewed* |

## Deletion path

Not implemented. `LearnerStore` (`app/state/learner.py`) has no delete method today. A
learner-scoped hard-delete endpoint is listed here as required future work, not shipped.
