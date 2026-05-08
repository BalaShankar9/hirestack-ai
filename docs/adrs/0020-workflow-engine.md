# ADR 0020: Workflow engine for long-running generation pipelines

Status: Accepted (PR m6-pr17)
Date: 2026-05-07
Deciders: Platform team

## Context

Generation pipelines (resume → critique → persist → emit) currently run
inside a single FastAPI request, with ad-hoc background tasks for the
slow paths. As we add more agentic substeps the failure surface grows:

* Long-tail provider latency (Anthropic / OpenAI > 30s) holds workers.
* Mid-pipeline crashes leak partial state into Postgres; reconciliation
  is manual.
* Critic-driven retries are coded as inline loops; they don't survive a
  pod restart.
* The inbox/outbox plumbing handles event delivery but not the
  *workflow state machine* itself.

We need a durable execution layer that:

1. Persists workflow position so restarts resume mid-flight.
2. Retries failed activities with bounded backoff outside the request
   path.
3. Versions workflows so old runs don't break when the code evolves.
4. Plays nicely with our existing outbox (events still fan out via
   Redis Streams; the workflow only triggers them).

## Decision

Adopt **Temporal** (Temporal Cloud for hosted control plane, fall back
to self-hosted dev server for local + CI).

* Python SDK: `temporalio` (>= 1.7).
* Workflows live in `backend/app/temporal/workflows/`.
* Activities live in `backend/app/temporal/activities/`.
* Worker entrypoint: `backend/app/temporal/worker.py`, surfaced as a
  `temporal_worker` Procfile process.
* Task queue: `hirestack-generation` for the first workflow.
* Strangler rollout: PR-18 routes `/generate` through Temporal behind
  `ff_temporal_generation` (default OFF; ramp dev → 5% → 50% → 100%).

## Alternatives rejected

* **Celery / RQ** — no native workflow concept, no replay, no
  versioning. We already lean on Redis Streams for events; doubling
  down on it for workflows reinvents Temporal poorly.
* **Step Functions / Cloud Workflows** — vendor lock to AWS/GCP and
  much weaker local-dev story.
* **Custom state machine on Postgres** — possible but expensive to
  maintain (replay, history, signals, queries — Temporal solves all of
  this for free).
* **Kafka** — explicitly forbidden by the build plan.

## Consequences

Positive
* First-class durable retries, signals, queries, and replay.
* Workers scale independently from the API tier.
* Critic-loop retries become a first-class workflow construct
  (`workflow.execute_activity(..., retry_policy=...)`).

Negative
* New runtime dependency (Temporal Cloud or self-hosted server).
* Engineers must internalise determinism rules for `@workflow.defn`
  code (no random, no I/O, no time.time()).
* CI gains a new dimension: workflow tests use
  `temporalio.testing.WorkflowEnvironment` (in-process, no server).

## Rollback

Two layers:

1. Per-flow: clear `ff_temporal_generation` to bypass the workflow
   path (PR-18).
2. Worldwide: stop the `temporal_worker` Procfile process and unset
   `TEMPORAL_HOST`. Existing API code paths keep functioning unchanged.

## References

* Build plan: `M6 / PR-17` in `BUILD_PLAN_M1_M6.md`.
* Temporal Python SDK: https://python.temporal.io/
