---
name: "HireStack 10/10 Execution"
description: "Drive HireStack AI from its current 5.5/10 platform state toward a verified 10/10 product using the roadmap, handoff, and current code paths. Use when continuing core product execution, not for brainstorming."
argument-hint: "Optional focus area, such as jobs flow, SSE, quality evals, route consolidation, or continue"
agent: "agent"
---

Take over HireStack AI as the execution lead and push it toward a real 10/10 product.

Start by reading these files in order:

1. [Opus handoff](../../docs/OPUS_HANDOFF_2026-04-11.md)
2. [Perfection roadmap](../../PERFECTION_ROADMAP.md)
3. [Next development design briefs](../../docs/NEXT_DEVELOPMENT_DESIGN_BRIEFS.md)
4. [Platform advantage roadmap](../../docs/PLATFORM_ADVANTAGE_ROADMAP.md)

Then verify the active code paths before trusting older notes:

- [Backend generation routes](../../backend/app/api/routes/generate.py)
- [Frontend generation flow](../../frontend/src/lib/firestore/ops.ts)
- [Workspace application page](../../frontend/src/app/(dashboard)/applications/[id]/page.tsx)

## Mission

Do not produce another generic strategy document. Ship the next highest-leverage block of real progress.

Current baseline:

- Core tool score: 6/10
- Full platform score: 5.5/10
- Backend non-integration tests last verified green at 451 passing
- Direct `/api/generate/pipeline` route is hardened with timeout + partial failure metadata
- Frontend prefers the DB-backed jobs flow and only falls back to legacy streaming
- The main product risk is still route fragmentation, not lack of features

## Non-Negotiables

1. Treat the jobs flow as the active product path unless code verification proves otherwise.
2. Do not add random new features before verifying and improving the real execution path.
3. Prefer route consolidation and runtime truth over UI polish.
4. Preserve existing worktree changes. Never revert unrelated edits.
5. Every meaningful code change must be tested.
6. Update the roadmap and handoff docs when you materially change reality.

## Execution Order

Follow this order unless the user explicitly overrides it:

1. Verify the active jobs flow end-to-end.
   - Validate create job, stream, completion, persistence, workspace rendering, and failure behavior.
   - If live AI credentials are unavailable, do the strongest possible mocked or partial verification and document the blocker precisely.

2. Finish the highest-leverage open item in Phase 1 or Phase 2 that improves the active path.
   - Prioritize: P1-02, P1-03, P1-07 through P1-16, then Phase 2 resilience items.

3. Reduce route fragmentation.
   - Compare `/pipeline`, `/pipeline/stream`, and `/jobs` behavior.
   - Move toward one canonical orchestration path, most likely the jobs flow.

4. Prove quality, not just mechanics.
   - Run or extend real or replayable evals across representative job families.
   - Check relevance, formatting, keyword coverage, readability, and factual safety.

5. Only after the above, improve platform-level leverage.
   - Observability
   - cost visibility
   - worker strategy
   - broader end-to-end coverage

## What To Deliver In This Session

Complete one meaningful block of work end-to-end:

- identify the next highest-leverage target
- implement the change
- add or update tests
- run the relevant tests
- update roadmap or handoff docs if needed
- summarize what changed, what passed, and what remains risky

Do not stop at analysis unless there is a genuine blocker.

## Decision Rules

When forced to choose, prefer:

1. reliability of the jobs flow over new feature breadth
2. one unified path over multiple inconsistent paths
3. measurable quality improvements over prompt churn
4. backend truth and persistence over frontend cosmetics
5. replayable failures over anecdotal bug notes

## If You Need A Starting Target

Default first target:

- verify the active jobs flow with the strongest possible end-to-end test coverage
- identify the first concrete break or inconsistency between jobs flow and legacy routes
- fix that issue at the root
- update [Perfection roadmap](../../PERFECTION_ROADMAP.md)

## Output Standard

At the end of the session, report only:

- what changed
- what was verified
- what remains broken or unproven
- the exact next best task

Work like the goal is a real 10/10 product, not a demo.