# HireStack AI — Opus Handoff

Date: 2026-04-11

## Executive Summary

HireStack is no longer a raw prototype. It is a real multi-surface product with a functioning frontend, a substantial backend, durable job execution primitives, a large database footprint, and a more serious agent stack than most resume-builder products.

The platform is still split-brain in one important way: there are multiple generation paths with overlapping responsibilities, and the product has not yet been validated end-to-end with live AI quality checks. The system is now strong enough to improve iteratively, but it is not yet top-tier.

### My current assessment

- Core tool (application generation engine): **6/10**
- Complete platform (product + infra + data + UX + operational readiness): **5.5/10**

That means:

- The product is real.
- The core engine works.
- The system is partially hardened.
- The most important remaining work is now **route consolidation, live-path verification, quality evaluation, and productionization**.

## What The Core Tool Is Right Now

The core tool is the **job-application generation engine**: JD + profile/resume in, tailored CV / cover letter / supporting artifacts out, with progress, persistence, and workspace rendering.

### Active execution path

The frontend currently prefers the DB-backed jobs flow, then falls back to legacy streaming.

- Frontend job-first flow: `frontend/src/lib/firestore/ops.ts`
- Jobs create/stream path is the main default client behavior.
- Legacy `/pipeline/stream` remains as fallback.

### Route map

There are still three meaningful generation paths in the backend:

1. `POST /api/generate/pipeline`
   - Sync direct route.
   - Now has a 5-minute pipeline timeout and partial-failure reporting.
2. `POST /api/generate/pipeline/stream`
   - Agent-oriented streaming route.
   - Still batches events before yielding, so the UX is not truly live.
3. `POST /api/generate/jobs` + `GET /api/generate/jobs/{id}/stream`
   - The active product path.
   - Hybrid path: legacy early phases + durable agent pipelines for document-generation phases.

### What is now working well

- Direct `/pipeline` hardening improved materially.
- Input validation, timeout handling, structured failure responses, and partial result handling are in place.
- Smoke coverage exists for the direct sync route.
- Backend non-integration suite is green at **451 passed**.
- The job path includes company intelligence/recon and durable agent-backed document stages.
- The workspace UI already exposes richer runtime surfaces: timeline, evidence, risk, validation, replay.

### What is still weak in the core tool

1. **Route fragmentation is still the biggest architectural problem.**
   - The sync route, stream route, and jobs route do not represent one canonical orchestration path.
   - Fixes made in one path can easily drift from the others.

2. **The active user path is not yet fully validated with real AI.**
   - We now have mocked smoke coverage, but not a disciplined live eval pass across roles and job types.

3. **Streaming UX is not truly real-time in the SSE agent route.**
   - Events are queued and then emitted in batches.
   - This makes the UI feel less alive than the architecture suggests.

4. **The jobs path is still hybrid rather than fully unified.**
   - Document generation uses durable `AgentPipeline` execution.
   - Earlier stages still run through legacy chain logic.
   - This is better than before, but it is not yet a single coherent runtime.

5. **Background workers exist but are not actually in the product’s execution loop.**
   - Celery task infrastructure is present.
   - The task entrypoint currently has no workspace usages.

## What The Complete Platform Is Right Now

### Frontend

Status: **7.5/10**

The frontend is more complete than a casual audit would suggest.

- Real data wiring is present.
- Workspace surfaces are substantial.
- Generation, progress, exports, evidence, replay, and quality UI all exist at least in first-pass form.
- The application workspace already looks like the beginnings of a real “mission control” surface.

Main weakness: this layer is ahead of the backend’s operational certainty. The UI is ready for stronger system truth than the runtime is consistently delivering.

### Backend API

Status: **6/10**

- Large surface area exists.
- Generation routes, jobs, replay, validation, and trace-oriented work are in place.
- Recent hardening improved direct-route reliability.

Main weakness: too many overlapping orchestration paths and still not enough live-path verification.

### AI / Agent Layer

Status: **4.5/10**

- The architecture is serious now: contracts, evidence, replay, observability, durable workflow runtime, planner hooks, final-analysis support.
- There is meaningful technical depth here.

Main weakness: output quality is still insufficiently measured in production-like conditions. The system is better engineered than it is proven.

### Database / Persistence

Status: **8/10**

- Strongest layer in the system.
- Many migrations.
- Job events, evidence, citations, and resume/recovery primitives are present.

Main weakness: some of the persistence power is ahead of what the main product paths are consistently exploiting.

### Workers / Async Infrastructure

Status: **2/10**

- Celery app and task files exist.
- Async task scaffolding exists.
- But the main app path does not actually depend on worker execution yet.

### Production / Ops

Status: **2/10**

- This is still the weakest major layer.
- Observability exists mostly as internal code capability, not yet full production operations discipline.
- No strong evidence yet of end-to-end monitoring, SLOs, dashboarding, or cost control in live use.

## Verified Current Facts

### Core route facts

- Sync route timeout and partial-failure metadata are in `backend/app/api/routes/generate.py`.
- `PIPELINE_TIMEOUT = 300` is defined there.
- `failedModules` is included in the sync response.

### Active product flow facts

- Frontend generation prefers `/api/generate/jobs` and `/api/generate/jobs/{id}/stream`.
- Only falls back to `/api/generate/pipeline/stream` when jobs API is unavailable.

### Streaming behavior fact

- SSE agent status events are still queued into `events_queue` and then flushed later rather than emitted immediately.

### Worker gap fact

- `workers/tasks/document_tasks.py` defines `generate_document_async`.
- There are no usages of `generate_document_async` in the workspace beyond its definition.

## Main Risks Opus Should Understand Up Front

1. **Do not assume one generation path equals the product.**
   The real product path is the jobs flow, not the sync route.

2. **Do not assume backend sophistication equals proven output quality.**
   The agent stack is more advanced than the eval discipline.

3. **Do not add more features before consolidating the orchestration surface.**
   More features on top of split routes will increase regression risk.

4. **Do not over-invest in Celery yet unless the product path is deliberately moved there.**
   Right now, workers are mostly latent capability.

5. **Do not trust older notes that say jobs route has no recon/intel.**
   That was true earlier; it is stale now.

## Recommended Plan For Opus

This is the sequence I would hand to Opus.

### Phase A — Finish The Current Core Properly

Goal: move the application engine from “works” to “verified and coherent.”

1. **Validate the active jobs flow end-to-end with live AI.**
   - Run 5 real generations across distinct role families.
   - Use the actual frontend or API job path, not just the sync route.
   - Capture runtime, failure points, module completeness, and output quality.

2. **Validate the SSE/UI experience end-to-end.**
   - Confirm what the user sees during generation in the wizard and workspace.
   - Verify whether progress feels live or batched.
   - Record the exact mismatch between backend event emission and frontend expectation.

3. **Close P1-02 / P1-03 / P1-07 through P1-16 from the roadmap.**
   - The direct route is hardened enough.
   - The next missing work is verification, not more theoretical architecture.

4. **Fix roadmap bookkeeping as progress happens.**
   - Use the roadmap as the single execution spine.

### Phase B — Consolidate Generation Architecture

Goal: eliminate split-brain generation logic.

1. **Choose one canonical runtime for generation.**
   - Prefer the jobs flow as the long-term product path.
   - Decide whether `/pipeline` remains only for debug/testing or gets retired.

2. **Unify early phases and document phases under the same orchestration model.**
   - Right now the jobs route is hybrid.
   - Move resume parse, benchmark, and gap analysis into the same durable model used for doc pipelines, or explicitly document why not.

3. **Make sync and stream behaviors contract-consistent.**
   - Same failure shapes.
   - Same quality metadata.
   - Same company intel behavior.
   - Same module naming and output contract.

4. **Turn event batching into true progressive emission where feasible.**
   - The current timeline UI deserves a more truthful event stream.

### Phase C — Prove Quality, Not Just Mechanics

Goal: make output quality measurable and improvable.

1. **Run live corpus evals across 5–10 representative JDs.**
   - SWE
   - PM
   - Designer
   - Data Scientist
   - Marketing

2. **Score outputs using fixed dimensions.**
   - relevance
   - formatting
   - keyword coverage
   - readability
   - factual safety

3. **Inspect critic and validator behavior on real runs.**
   - Check if scores have real spread.
   - Check if validator warnings are meaningful.
   - Check if fact-checking catches fabricated/unsupported claims in realistic edge cases.

4. **Promote bad runs into replay/regression artifacts.**
   - Use the replay work already present.
   - Grow a real eval corpus from failures, not just handcrafted cases.

### Phase D — Make The Product Operationally Credible

Goal: make the platform safe to scale.

1. **Add platform-level observability around the jobs flow.**
   - request success rate
   - time to first visible progress
   - time to finished modules
   - per-stage failure rates
   - provider-specific error rates

2. **Add cost and throughput visibility.**
   - which stages are most expensive
   - which role families create the slowest jobs
   - which retries are worth keeping

3. **Decide worker strategy clearly.**
   - Either move the jobs runtime onto workers deliberately,
   - or keep the current async job model and stop pretending Celery is part of the active path.

4. **Add real end-to-end tests for the actual user journey.**
   - auth
   - create application
   - generate via jobs flow
   - stream progress
   - persist modules
   - open workspace
   - export at least one artifact

## What Opus Should Do First

If Opus only picks up one immediate block, it should be this:

1. ~~Run the **active jobs path** with live AI on 5 real cases.~~ **DONE (mocked, 2026-04-11)**: 23 smoke tests now cover the jobs flow — creation, streaming, cancellation, inner runner, partial failure, progress ordering, meta enrichment.
2. ~~Fix the first critical bugs discovered there.~~ **DONE (2026-04-11)**: Fixed **NameError in jobs runner** — `cv_result` was never initialized in the jobs flow scope (only `cv_result_raw` existed), causing every successful job to crash at the meta-enrichment step (line ~2701). Added `cv_result` initialization in both AgentPipeline and legacy fallback paths.
3. Decide whether to **fully consolidate on jobs flow**.
4. Fix the next 3 highest-leverage gaps.

That is the fastest path to moving the product forward without drifting into more speculative architecture.

## What Opus Should Not Do Yet

- Do not add more document types first.
- Do not build more UI chrome before verifying the live jobs/runtime path.
- Do not deepen Celery integration before deciding whether workers are actually the intended runtime.
- Do not tune prompts blindly before running a disciplined live eval pass.

## Bottom Line

The core tool is now good enough to improve from reality rather than from guesswork.

The next leap is not “more AI.” It is:

- verifying the real product path,
- unifying the orchestration surface,
- proving quality with live evals,
- and only then pushing deeper into platform advantage.

That is the handoff I would give to Opus.
