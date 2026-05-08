# ADR-0036: Per-stage Temporal activities (workflow durability M9)

- **Status:** Accepted 2026-05-08
- **PR:** `m8-pr32` (this PR ships the per-stage scaffolding + checkpoint store; runtime decomposition into per-phase entrypoints is the documented follow-up `m8-pr32b`)
- **Closes:** P1-1 ("today a worker crash mid-pipeline re-burns tokens for completed stages") — see `IMPLEMENTATION_MILESTONES.md` M9.
- **Supersedes:** none. Strangles the m6-pr24 "single `run_pipeline` activity" scaffold for production traffic when `ff_temporal_per_stage` is ON.
- **Related:** ADR-0026 (Temporal scaffold), ADR-0028 (strangler dispatch), ADR-0034 (ai_invocations recorder), ADR-0035 (strict event validation).

## 1. Context

The Temporal scaffold shipped in m6-pr17/m6-pr24 wraps the entire generation pipeline in a **single** activity called `run_pipeline`. That delegate calls `_run_generation_job_via_runtime(job_id, user_id)` which executes the seven-phase agent pipeline (`recon → atlas → cipher → quill → forge → sentinel → nova`, then `persist`) inside one process-bound async function.

Today, if a worker pod is killed mid-pipeline:
- Temporal retries the **whole** `run_pipeline` activity from scratch.
- The runtime's internal `_completed_steps` counter resets.
- Every LLM call that succeeded before the crash is re-burned.
- At our current cost-per-job, a single `quill` re-run costs ~$0.40; chaos drills suggest 2–4% of jobs hit at least one worker recycle.

Blueprint §M9 (line 593) mandates per-stage activities with idempotency-key + retry policy so that "mid-pipeline crash resumes from last completed activity." This ADR records the design we landed on.

## 2. Decision

Decompose the production plan into **seven per-stage Temporal activities** (one per pipeline phase) gated behind a new feature flag `ff_temporal_per_stage`. Each activity is wrapped by a checkpoint-aware execute hook that:

1. Reads the `pipeline_checkpoints` table for `(job_id, stage)`.
2. If `status='complete'` → returns the cached `StepResult` from `output_summary` and skips re-execution. **This is the resume contract.**
3. Otherwise: marks `status='running'`, calls the per-stage runtime entrypoint, then writes `status='complete'` with the summary on success or `status='failed'` with the error class on raise.

Concretely:

- New table `public.pipeline_checkpoints` (PK = `(job_id, stage)`) records per-stage status, started_at, completed_at, attempt_count, output_summary (JSONB; capped at ~4KB so Temporal history stays bounded), error_class.
- New module `backend/app/temporal/checkpoints.py` exposes `CheckpointStore` with `read(job_id, stage)`, `mark_running(job_id, stage)`, `mark_complete(job_id, stage, summary)`, `mark_failed(job_id, stage, error_class)`. Best-effort writes; insert exceptions logged but never raise into the activity body so a checkpoint-store outage does not block generation.
- New helpers in `backend/app/temporal/activities/production.py`:
  - `STAGE_ORDER` constant (the 7 phase names; ordering matters because the workflow loops over plan.steps in order).
  - `_build_per_stage_plan(inp)`: returns a 7-step `GenerationPlan` when `ff_temporal_per_stage` is ON; falls back to the legacy single-step plan when OFF (zero-risk default).
  - `_execute_with_checkpoint(inp, step)`: the checkpoint-aware execute hook described above. For now, the FIRST stage (`recon`) calls `_run_generation_job_via_runtime` end-to-end; the remaining six stages skip-via-checkpoint because the runtime has already done their work in the same process. **This is the m8-pr32 shipping reality** — see §6 for what's deferred.
- New flag `ff_temporal_per_stage` (default OFF, sunset 2026-12-01).
- Production hooks are now **flag-aware**: when ON they bind `_build_per_stage_plan` + `_execute_with_checkpoint`; when OFF they bind today's `_build_plan` + `_execute_via_runtime` (zero behaviour change).

## 3. Alternatives considered

**A. Decompose the runtime into per-phase entrypoints in this PR.**
Rejected because `_run_generation_job_via_runtime` shares context (RAG cache, sub-agent registry, retry emitter contextvars) across phases. Splitting cleanly is its own ~600-line refactor that needs its own review surface. We chose to ship the **durability primitive** (workflow + checkpoint store) first and decompose the runtime in a follow-up PR (`m8-pr32b`). The per-stage workflow shape lands today; meaningful per-phase resume granularity lands when the runtime split lands.

**B. Use Temporal's built-in continueAsNew + history-replay for resume.**
Rejected. continueAsNew is for long-running workflows (>50K events); our pipelines run <120s. Per-stage activities are the canonical Temporal pattern for our scale and are what the blueprint explicitly mandates.

**C. Store checkpoints in `generation_jobs.completed_steps` (existing column).**
Rejected. `completed_steps` is an integer (1-7) that the runtime updates *after* a stage completes. It carries no `output_summary` and no `attempt_count`, and writes go through the runtime's own SSE-coupled progress emitter. We need a separate idempotent write path that survives a worker crash, hence a dedicated table.

**D. Use Redis for checkpoints.**
Rejected. Redis is a cache; a worker recovering from crash MUST find the checkpoint, so we need durability. Postgres + RLS gives us per-tenant isolation for free.

**E. Store full per-stage output (not just a summary).**
Rejected. Temporal activity history would balloon (each activity result is written to history). The blueprint explicitly says "checkpoint-only outputs (not full intermediate state)". `output_summary` is capped at 4KB and only carries the data needed for downstream stages to decide if they can skip.

## 4. Schema

```sql
CREATE TABLE public.pipeline_checkpoints (
  job_id          uuid        NOT NULL,
  stage           text        NOT NULL,
  status          text        NOT NULL CHECK (status IN ('running','complete','failed')),
  started_at      timestamptz NOT NULL DEFAULT now(),
  completed_at    timestamptz,
  attempt_count   int         NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
  output_summary  jsonb,
  error_class     text,
  PRIMARY KEY (job_id, stage)
);
CREATE INDEX pipeline_checkpoints_job_id_idx ON public.pipeline_checkpoints (job_id);
ALTER TABLE public.pipeline_checkpoints ENABLE ROW LEVEL SECURITY;
-- Service role bypasses RLS; no INSERT/UPDATE policy for anon/authenticated.
-- SELECT policy gates on auth.uid() owning the parent generation_jobs row.
```

Stage names are locked to the runtime's `PHASE_SLO_MS` keys: `recon, atlas, cipher, quill, forge, sentinel, nova` (7 stages). The legacy `persist` phase is folded into `nova` for checkpointing because it's a write-side terminal step and there is no logical "skip persist if already done" — the runtime itself is upsert-idempotent on `job_id`.

## 5. Consequences

### Positive
- **Resume contract is real and testable today.** Even though the runtime itself isn't yet split, the workflow loops over 7 stages and the checkpoint table tracks each. A worker crash between activities (Temporal's natural retry boundary) hits the checkpoint and skips. Tests in `test_per_stage_resume.py` verify this.
- **Zero risk at default flag state.** Production hooks fall back to today's single-step plan when `ff_temporal_per_stage=false`. Existing 4 tests in `test_production_hooks.py` still pass without modification.
- **Forward-compatible with runtime split.** When `m8-pr32b` lands per-phase entrypoints, only `_execute_with_checkpoint` changes (one function); the workflow shape, the table, and the flag stay.
- **Idempotency is explicit.** Today's "the runtime is internally idempotent" was an unwritten contract. Now the checkpoint table is the canonical "this job already finished stage X" record.

### Negative
- **Two-PR shipping cycle.** This PR alone does not yet recover the cost of crashed mid-pipeline runs at the per-phase level — it recovers cost only between the (currently single) execute call and the (currently no-op) downstream skip-stages. The cost win lands when `m8-pr32b` ships.
- **One extra Postgres write per stage.** With flag ON: 7 inserts + 7 updates per job. At our current load (~2 jobs/min), that's ~30 writes/min — negligible.
- **Temporal history grows.** 7 activities × scheduled/started/completed = 21 events per job vs. today's 3. Still well under the 50K continueAsNew threshold.

### Out of scope (deferred — see also IMPLEMENTATION_MILESTONES.md M9)
- **Runtime decomposition** into per-phase entrypoints (`_run_recon`, `_run_atlas`, …). Follow-up PR `m8-pr32b`.
- **Chaos test** that kills the worker mid-`quill` and verifies cost-not-re-burned. Requires `m8-pr32b` first; ships in `m8-pr32c`.
- **Per-stage SLO metrics** in Prometheus (`pipeline_checkpoint_duration_seconds{stage=...}`). Belongs with the runtime split.
- **Retention policy** for `pipeline_checkpoints` (proposed: drop rows older than 30 days). Add when table exceeds 1M rows.
- **UI resume affordance** ("resume from stage X" in the job view). Pure UX, follow-up.

## 6. Rollout plan

| Week | Action |
|---|---|
| 0 (this PR) | Apply migration. Deploy code with `ff_temporal_per_stage=false` (zero behaviour change). |
| 1 | Ship `m8-pr32b` (runtime per-phase entrypoints). Deploy with flag still OFF. |
| 2 | Flip `FF_TEMPORAL_PER_STAGE=true` in dev/staging. Watch `pipeline_checkpoints.attempt_count > 1` count. |
| 3 | Ship `m8-pr32c` (chaos test). Run worker-kill drill in staging. |
| 4 | Flip flag in canary. |
| 5 | Flip flag in prod after 7 days canary green. |
| <2026-12-01 | Sunset: flag must be promoted (default flipped to ON) or extended. |

## 7. Validation criteria

- (✅ this PR) `_build_per_stage_plan` returns 7 stages in canonical order.
- (✅ this PR) `_execute_with_checkpoint` skips on `status='complete'`, executes on missing/`status='failed'`.
- (✅ this PR) `CheckpointStore.mark_*` failures never raise into the activity.
- (✅ this PR) Production hooks fall back to legacy plan when flag OFF.
- (✅ this PR) RLS enabled on `pipeline_checkpoints`; no anon/authenticated INSERT.
- (pending m8-pr32b) Per-phase runtime entrypoints exist + are individually retried.
- (pending m8-pr32c) Worker-kill chaos drill: `attempt_count` increments by 1 on the in-flight stage; all earlier stages stay at attempt_count=1; total LLM cost unchanged from the no-crash baseline.

## 8. References

- Blueprint §M9 (line 593) — workflow durability mandate.
- IMPLEMENTATION_MILESTONES.md M9 — this PR's row.
- ADR-0026 — Temporal scaffold (m6-pr17).
- ADR-0028 — strangler dispatch (m6-pr24).
- ADR-0035 — strict event validation (m7-pr31; same shadow→flip ratchet pattern).
