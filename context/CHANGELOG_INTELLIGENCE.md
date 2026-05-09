---
title: Changelog Intelligence
last_synced: 2026-05-09
watch_paths:
  - CHANGELOG.md
  - .github/workflows
canonical_sources:
  - CHANGELOG.md
  - /memories/repo (m*-pr*-shipped notes)
update_when:
  - a PR ships (append entry)
  - a milestone closes (rollup the milestone)
  - the cross-ref policy changes
---

# Changelog Intelligence

> The bridge between code history and intent. CHANGELOG.md is the
> consumer-facing list of changes; this file is the engineering-facing
> ledger that links each change to its memory note, ADRs, and the parts
> of `/context` it touched.

---

## TL;DR — 10 lines

1. **CHANGELOG.md** is canonical for users. **`/memories/repo/m<N>-pr<NN>
   -shipped.md`** notes are canonical for engineers.
2. **Every PR creates a memory note** with: scope, files touched, tests
   added, ADRs created/updated, follow-ups.
3. **This file rolls them up** so a new contributor can scan the trajectory
   without opening 70 individual notes.
4. **Every entry has cross-refs:** CHANGELOG line, memory note,
   `/context` files updated, ADRs.
5. **Milestones map to contexts:** m6 (foundation), m7 (queue + provider
   resilience), m8 (per-stage activities), m9 (SSE hardening), m10
   (governance machinery), m11 (event deprecation), m12 (test stability +
   docs).
6. **PR sizes ≤ 600 LOC** per the stacked-PR convention. Doc PRs (this
   one) are exempt and flag the exception.
7. **Stacked branches:** `m12-pr<NN>-<slug>`. Each PR rebases on the
   previous one and lands in order.
8. **Reverts are explicit:** a revert PR carries `m<N>-pr<NN>-revert`
   slug and updates the memory note of the reverted PR with status
   = REVERTED.
9. **The PR ledger is the official "did we ship X?" oracle.** If it's
   not in the ledger, it didn't ship.
10. **Drift detection:** `/context` files have `last_synced`; PRs that
    touch a watched path should bump the relevant `/context` file in the
    same PR.

---

## How to read this file

For each milestone, this file lists every PR that shipped in order, with:

- **PR slug** — `m<N>-pr<NN>-<slug>`
- **Headline** — one line.
- **Memory note** — the `/memories/repo/...` file.
- **Touched contexts** — which `/context/*.md` files changed (or should).
- **ADRs** — if any.

Use it as an index, not a transcript. The full story lives in the memory
notes and the PRs themselves.

---

## Milestone m6 — foundation

| PR | Headline | Memory | Contexts | ADRs |
|---|---|---|---|---|
| m6-pr17 | Establish modular monolith + ai_engine boundary | (legacy; pre-ledger) | ARCHITECTURE, AI_CONTEXT | ADR-0013 |

(m6 predates the formal PR ledger; entries are reconstructive.)

---

## Milestone m7 — queue + provider resilience

| PR | Headline | Memory | Contexts | ADRs |
|---|---|---|---|---|
| m7-pr27a | Partition rotation Temporal workflow | `m7-pr27a-partition-rotation-shipped.md` | DEVOPS_INFRA, DATABASE_CONTEXT | ADR-0033 |
| m7-pr27b | In-process fallback gated by `ff_inprocess_fallback` (off in prod) | `m7-pr27b-inprocess-fallback-shipped.md` | DEVOPS_INFRA, KNOWN_ISSUES (W3) | ADR-0038 |
| m7-pr27c | ACK on success only; XPEL claim path | `m7-pr27c-ack-on-success-shipped.md` | KNOWN_ISSUES (W4) | — |
| m7-pr27d | Bootstrap registry on cold start | `m7-pr27d-bootstrap-registry-shipped.md` | AI_CONTEXT, AUTH_SECURITY_CONTEXT | — |
| m7-pr28 | Anthropic provider behind `ff_anthropic_provider` | `m7-pr28-anthropic-provider-shipped.md` | AI_CONTEXT (model_router) | ADR-0034 |
| m7-pr29 | Capability tokens + sandbox tier dispatch | `m7-pr29-capability-tokens-sandbox-shipped.md` | AUTH_SECURITY_CONTEXT, AI_CONTEXT | ADR-0035 |
| m7-pr30 | `ai_invocations` flight recorder + cost rollup | `m7-pr30-ai-invocations-shipped.md` | AI_CONTEXT, PERFORMANCE_CONTEXT | — |
| m7-pr31 | Strict event schema validation | `m7-pr31-strict-event-validation-shipped.md` | API_CONTEXT, TESTING_CONTEXT | ADR-0037 |

---

## Milestone m8 — per-stage activities

| PR | Headline | Memory | Contexts | ADRs |
|---|---|---|---|---|
| m8-pr32 | Per-stage Temporal activities (P1-1) | `m8-pr32-per-stage-activities-shipped.md` | AI_CONTEXT, ARCHITECTURE | ADR-0040 |

---

## Milestone m9 — SSE hardening

| PR | Headline | Memory | Contexts | ADRs |
|---|---|---|---|---|
| m9-pr33 | SSE hardening — phase 1 | `m9-pr33-shipped.md` | API_CONTEXT, FRONTEND_CONTEXT | — |
| m9-pr34 | SSE resume + Last-Event-ID | `m9-pr34-pr36-shipped.md` | API_CONTEXT, FRONTEND_CONTEXT | ADR-0039 |
| m9-pr35 | SSE backpressure + drop semantics | `m9-pr35-shipped.md` | API_CONTEXT, KNOWN_ISSUES (W10) | — |
| m9-pr36 | (rolled into pr34 release) | `m9-pr34-pr36-shipped.md` | — | — |

---

## Milestone m10 — governance machinery

| PR | Headline | Memory | Contexts | ADRs |
|---|---|---|---|---|
| (governance) | Governance machinery rollup | `governance-machinery-2026-05-08.md` | TESTING_CONTEXT, RELEASE_READINESS | — |

---

## Milestone m11 — event schema deprecation window

| PR | Headline | Memory | Contexts | ADRs |
|---|---|---|---|---|
| m11-pr37 | Dual-emit deprecation window for event schemas | `m11-pr37-shipped.md` | API_CONTEXT, TESTING_CONTEXT | — |

---

## Milestone m12 — test stability, docs, hardening

| PR | Headline | Memory | Contexts | ADRs |
|---|---|---|---|---|
| m12-pr01 | Triage 9 baseline failures (P1-11) — phase 1 | (rolled into pr05) | TESTING_CONTEXT | — |
| m12-pr02 | Coverage gate (backend ≥ 75%, frontend ≥ 70%) | (per ledger) | TESTING_CONTEXT | — |
| m12-pr03 | Import-linter contract for `ai_engine` boundary | (per ledger) | AI_CONTEXT, ARCHITECTURE | — |
| m12-pr04 | Dependency audit promoted to required | (per ledger) | AUTH_SECURITY_CONTEXT, TESTING_CONTEXT | — |
| m12-pr05 | Triage remaining baseline failures (P1-11) | (per ledger) | TESTING_CONTEXT, RELEASE_READINESS | — |
| m12-pr06 | Sentry redaction depth = 16 (TD-2) | (per ledger) | AUTH_SECURITY_CONTEXT, TECH_DEBT | — |
| m12-pr07 | OpenAPI drift gate | (per ledger) | API_CONTEXT, TESTING_CONTEXT | — |
| m12-pr08 | Per-org daily cost cap (`usage_guard`) — P0-4 | (per ledger) | AUTH_SECURITY_CONTEXT, PERFORMANCE_CONTEXT | — |
| m12-pr09 | Tenancy isolation gate hardening | (per ledger) | AUTH_SECURITY_CONTEXT, TESTING_CONTEXT | — |
| m12-pr10 | Migrations dry-run gate | (per ledger) | DEVOPS_INFRA, TESTING_CONTEXT | — |
| m12-pr11 | Secret-scan gate | (per ledger) | AUTH_SECURITY_CONTEXT, TESTING_CONTEXT | — |
| m12-pr12 | Provider failover test stable | (per ledger) | AI_CONTEXT, TESTING_CONTEXT | — |
| m12-pr13 | `/context` Living Engineering Brain (19 files) | `m12-pr13-context-docs-shipped.md` | (introduces all 18) | PR #31 |
| m12-pr14 | Requirements lockfile (TD-4 partial) | `m12-pr14-requirements-lockfile-shipped.md` | TECH_DEBT, TESTING_CONTEXT | PR #32 |
| m12-pr15 | DLQ contract pin (`tests/queue/test_dlq.py`, 8 tests) | `m12-pr15-test-dlq-shipped.md` | TESTING_CONTEXT | PR #33 |
| m12-pr16 | Partition rotation health (`tests/db/test_partition_health.py`, 15 tests) | `m12-pr16-test-partition-health-shipped.md` | TESTING_CONTEXT | PR #34 |
| m12-pr17 | Action-gate contract (`tests/ai/test_action_gate.py`, 21 tests) | `m12-pr17-test-action-gate-shipped.md` | TESTING_CONTEXT | PR #35 |
| m12-pr18 | Temporal resume contract (`tests/temporal/test_resume.py`, 19 tests) | `m12-pr18-test-temporal-resume-shipped.md` | TESTING_CONTEXT | PR #36 |
| m12-pr19 | TD-1 first cut: extract `_module_state.py` from `routes/generate/jobs.py` (2496 → 2358 LOC) | `m12-pr19-td1-split-jobs-shipped.md` | (none) | (this PR) |

(Memory notes for m12-pr01..pr12 referenced in the PR ledger / repo
memory; this file's intent is the index, not the transcripts.)

---

## How a new entry gets added

In the PR that ships:

1. Append a row to the relevant milestone table above (or open a new
   milestone heading if it's a new milestone).
2. Update CHANGELOG.md with the user-facing line.
3. Write `/memories/repo/m<N>-pr<NN>-<slug>-shipped.md` with:
   - what shipped
   - files touched
   - tests added
   - ADRs created or referenced
   - follow-ups (link to KNOWN_ISSUES W item if applicable)
4. Bump `last_synced` on every `/context` file in the "Touched contexts"
   column.

---

## Cross-reference policy

- A PR that adds a feature without updating the relevant `/context`
  file = blocked in review.
- A PR that adds a public API change without an OpenAPI bump = blocked.
- A PR that touches the AI runtime without bumping AI_CONTEXT
  `last_synced` = warned (advisory until W14 is promoted to required).
- A PR that ships a P0/P1 item must mark RELEASE_READINESS update in
  the same PR.

---

## Reverts

A revert PR slug is `m<N>-pr<NN>-revert-of-pr<MM>`.

In the same PR:

1. Append a row to the milestone table with `Headline = "Revert of pr<MM>
   — <reason>"`.
2. Update the memory note of pr<MM> with `STATUS: REVERTED at pr<NN>`.
3. Reopen any KNOWN_ISSUES W items that the original PR closed.
4. Update RELEASE_READINESS if a P0/P1 status reverts.

---

## Health metrics for the PR ledger itself

- **PRs without a memory note:** 0 (target).
- **PRs without a CHANGELOG entry:** 0 (target).
- **PRs that touched watched paths without a `/context` bump:** tracked
  by the governance script (m12-pr13 advisory output).

---

## What "good changelog hygiene" looks like

- [ ] PR title matches `m<N>-pr<NN>: <slug>` exactly.
- [ ] CHANGELOG.md updated.
- [ ] Memory note written.
- [ ] This file's milestone table row added.
- [ ] Touched `/context` files bumped.
- [ ] ADRs referenced.
- [ ] If reverting: previous note marked REVERTED.
