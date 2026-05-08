# ADR-0038 — Eliminate the in-process dispatch fallback in production

- **Status:** Accepted
- **Date:** 2026-05-08
- **Owners:** Platform Core squad — DRI: @BalaShankar9
- **Related:** ADR-0014 (worker dispatch), ADR-0037 (partition rotation),
  blueprint §6 (durability invariants), §11 (feature-flag lifecycle).
  Closes **P0-2** on the production risk register.

## Context

Today `_start_generation_job` in
`backend/app/api/routes/generate/jobs.py` implements a **three-tier**
dispatch ladder:

```
Tier-1: Temporal (when ff_temporal_generation AND TEMPORAL_HOST set)
   ↓ on dispatch error / not configured
Tier-2: Redis Streams (enqueue_generation_job)
   ↓ on Redis unavailable / no active consumers
Tier-3: in-process asyncio.create_task running the FULL generation
        pipeline inside the FastAPI web process — UNBOUNDED.
```

Tier-3 is the source of the P0-2 incident class:

1. **No backpressure.** A Redis outage silently relocates the entire
   generation workload onto the API web pods. Each in-process job runs
   the full PipelineRuntime (heavy LLM calls, DB writes, ~minutes of
   walltime). With no concurrency cap, a 30-second Redis blip can spawn
   hundreds of concurrent in-process pipelines and OOM the web fleet.
2. **Loss of durability.** The web process is preempted on deploy
   (rolling restart), on autoscaling (Railway scale-down), and on OOM.
   In-process jobs in flight at that instant are lost — the
   `generation_jobs` row sits at `status='running'` and only the
   30-minute watchdog reaps it. From the user's perspective the job
   simply hangs.
3. **Hidden from operators.** The fallback is invisible in dashboards
   except for the `generation_job_inprocess_fallback` log line. There
   is no metric, no alert, no rate limit.
4. **Violates Reliability > Cost > FeatureVelocity priority.** Trading
   silent unreliability for "the request didn't immediately fail" is a
   FeatureVelocity decision dressed up as a reliability decision.

The bootstrap coroutines `_try_temporal()` and `_try_enqueue()` are
also fire-and-forget `asyncio.create_task` calls that nobody owns. On
shutdown they are not cancelled cleanly. (Orphan-task ownership is a
secondary concern and is recorded as **deferred follow-up** below — see
"Out of scope".)

## Decision

**Collapse the dispatch ladder to two tiers in production. Gate the
in-process tier behind an explicit, sunset-bound feature flag, and
bound it.**

```
Tier-1: Temporal (when ff_temporal_generation AND TEMPORAL_HOST set)
   ↓ on dispatch error
Tier-2: Redis Streams (enqueue_generation_job)
   ↓ on Redis unavailable
   ├── ff_inprocess_fallback = false (PRODUCTION DEFAULT) → mark job
   │       failed with retryable error_message. The client retries
   │       cleanly, and the failure is durable in `generation_jobs`.
   └── ff_inprocess_fallback = true (DEV / single-process deploys) →
           bounded in-process execution: refuse to start when
           `len(_ACTIVE_GENERATION_TASKS) >= inprocess_max_concurrent`
           and mark the job failed with an explicit "saturated"
           message instead of queueing forever.
```

### What we add

1. **`config/feature_flags.yaml`**: register `ff_inprocess_fallback`
   with sunset **2026-08-31**. Owner: `@BalaShankar9`. Past sunset
   the flag must be removed and the in-process path deleted; by then
   every prod-shaped environment runs Temporal or a Redis worker.
2. **`backend/app/core/config.py`**:
   - `ff_inprocess_fallback: bool = False`
   - `inprocess_max_concurrent: int = 4` (clamped to ≥1)
3. **`backend/app/api/routes/generate/jobs.py`**:
   - `_start_generation_job_legacy` checks `ff_inprocess_fallback`
     before invoking `_start_generation_job_inprocess`. When the flag
     is off and Redis is unavailable, it marks the job failed via
     `_finalize_orphaned_job` with a retryable message.
   - `_start_generation_job_inprocess` enforces the
     `inprocess_max_concurrent` cap up front. Over-cap → mark failed,
     do not start a task.
4. **`backend/tests/temporal/test_strangler.py`** (new test cases) +
   a focused new file
   `backend/tests/unit/test_inprocess_fallback_gate.py` covering:
   - Flag off + Redis unavailable → job marked failed, no in-process
     task started.
   - Flag on + saturated semaphore → job marked failed, no new task
     started.
   - Flag on + capacity available → in-process task starts (existing
     behaviour preserved).

### What we explicitly do not change

- The Tier-1 strangler bootstrap (`_try_temporal()`) still uses
  `asyncio.create_task`. The coroutine is bounded and cheap (one
  network RPC). Wiring it into a managed task registry is a separate
  follow-up and is captured in **Out of scope** below.
- The PipelineRuntime semantics are untouched.

## Consequences

### Positive

- **Production safety**: no Redis outage can silently load up to N
  pipelines onto the web fleet anymore. Failures are durable and
  observable.
- **Visible**: every fallback path now writes a `failed` row with an
  unambiguous message instead of swallowing the symptom.
- **Reversible**: setting `ff_inprocess_fallback=true` reactivates the
  legacy path for dev or for an emergency rollback. Sunset date forces
  the conversation by 2026-08-31.
- **Closes P0-2** on the production risk register.

### Negative / accepted trade-offs

- During a Redis outage, the user sees an immediate failure rather
  than a slow success. That is the **intended** trade-off — failing
  fast on a durability outage is correct behaviour.
- The dev-mode in-process path now has a hard cap (`4`). Local heavy
  load may queue at the API layer with explicit `429`-shaped
  failures. Operators can raise the cap via env var.

### Out of scope (deferred — written down so they don't get lost)

- Wiring `_try_temporal()` and `_try_enqueue()` bootstrap coroutines
  into a managed task registry for graceful shutdown. Tracked as
  follow-up **m7-pr27d** (orphan task hygiene). Lives in M7-D.
- Adding a Prometheus counter `generation_dispatch_fallback_total{tier=...}`
  and a Grafana panel. Tracked under M11 observability uplift.

## Considered alternatives

### A. Delete the in-process tier entirely

Tempting and clean, but breaks `make dev`/single-process developer
ergonomics where there is no Redis worker process. We keep the path,
gate it, bound it, and sunset it.

### B. Keep three-tier, just add a semaphore

Insufficient. The defect is *silent unreliability*, not just unbounded
fan-out. Without the explicit flag and the explicit failure path,
operators still cannot tell the difference between "Redis is fine" and
"Redis fell over and we're running everything on web". The flag makes
the regression mode legible.

### C. Bound via uvicorn `--limit-concurrency`

Limits *all* requests, not the dispatch path. Same OOM risk for any
job already past the dispatch boundary. Wrong layer.

## Validation

- Unit tests:
  `backend/tests/unit/test_inprocess_fallback_gate.py` (new) and
  expanded coverage in `backend/tests/temporal/test_strangler.py`.
- Governance: `scripts/governance/check_feature_flags.py` enforces
  `ff_inprocess_fallback` sunset compliance.
- Architecture: no new import-linter contract needed (no boundary
  added).

## Stage-B revisit triggers

Revisit this ADR when **any** of the following hold:

- We move to a multi-region deployment where the API and the queue
  worker are deployed independently. The "dev fallback" rationale
  weakens further — consider deleting the path.
- We introduce a second job class that uses the same dispatch ladder.
  The flag must apply per-class or be split.
- The sunset date (2026-08-31) approaches without prod telemetry
  showing the flag stayed `false`.
