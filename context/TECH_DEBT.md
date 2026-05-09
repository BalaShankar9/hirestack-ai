---
title: Tech Debt Ledger
last_synced: 2026-05-08
watch_paths:
  - backend/app/api/routes/generate
  - backend/main.py
  - requirements.txt
  - backend/requirements.txt
  - frontend/package.json
canonical_sources:
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#22-explicit-tech-debt
  - /memories/repo (PR ledger)
update_when:
  - a TD item ships
  - a new TD item is acknowledged
  - the priority order changes
  - a TD item gets a deadline (linked PR)
---

# Tech Debt Ledger

> Acknowledged debt only. Not a wish list. Each item has a state, a
> reason, and (if scheduled) a target PR. Adding an item without
> documenting all three is forbidden.

---

## TL;DR — 10 lines

1. **Total tracked items:** 10. **Shipped:** 2 (TD-2, TD-7).
   **Open:** 8.
2. **Highest priority open:** TD-1 (split `routes/generate/jobs.py` —
   1500+ lines). Blocks reviewability.
3. **Risk-adjacent:** TD-4 (unpinned `requirements.txt` — supply chain
   reproducibility risk).
4. **Stage B blockers:** TD-9 (per-region observability), TD-10 (dual-
   namespace lazy imports).
5. **Quality next:** TD-3 (replace hand-rolled `/metrics` with Prometheus
   instrumentor).
6. **Quality eventually:** TD-8 (no mutation testing).
7. **Cross-version drift:** TD-5 (Python 3.11 in CI vs 3.13 local) — needs
   matrix CI.
8. **Order of operations:** ship the highest-blocking ones first; the
   rest get scheduled after Stage A close.
9. **Anti-pattern:** retiring debt by writing more code on top. Each TD
   item shipping must come with the associated tests and runbooks.
10. **No invisible debt.** If you find debt that is not on this list, add
    a TD entry in the same PR.

---

## TD-1 — Split `backend/app/api/routes/generate/jobs.py` (OPEN, **highest**)

**Symptom:** single file is 1500+ lines, with 11 endpoints, all the
streaming logic, and three different orchestration entry points.

**Why it matters:**

- Reviewability: PRs that touch this file have a high false-positive rate
  in code review.
- Test surface: a regression in one endpoint is easy to miss because the
  test file has the same shape.
- Onboarding: new contributors take longer to load mental model.

**Plan:**

- Split into:
  - `routes/generate/jobs.py` — POST/GET/DELETE /jobs (CRUD)
  - `routes/generate/streaming.py` — SSE `agentic-stream`
  - `routes/generate/cancel.py` — cancellation + resume
  - `routes/generate/admin.py` — admin replays / DLQ ops
- Tests follow the new shape one-to-one.
- Import-linter contract preserved.

**Target:** scheduled post m12-pr13. ~3 PRs of ≤ 600 LOC each.

---

## TD-2 — Sentry redaction depth (SHIPPED — m12-pr06)

**Was:** Sentry `before_send` redacted PII at depth 3; nested resume
bodies and JD bodies leaked through nested context dicts.

**Now:** depth = 16; explicit allowlist of safe fields; per-event
re-validation in CI.

**Anchor:** `backend/app/observability/sentry.py` + tests under
`backend/tests/observability/test_sentry_redaction.py`.

---

## TD-3 — Replace hand-rolled `/metrics` with Prometheus instrumentor (OPEN)

**Symptom:** `backend/app/api/routes/metrics.py` builds Prometheus text
by hand. Easy to drift, hard to add labels consistently.

**Plan:** swap to `prometheus-fastapi-instrumentator` + a small custom
collector for the AI-engine counters that have non-trivial label sets.
Output is byte-compatible with current Grafana dashboards.

**Target:** post m12-pr13.

---

## TD-4 — Lockfile for `requirements.txt` (OPEN, **risk-adjacent**)

**Symptom:** `requirements.txt` and `backend/requirements.txt` use `>=`
ranges. Two builds five minutes apart can resolve to different versions.

**Why it matters:**

- Supply chain: a new transitive dep with a CVE can land silently.
- Reproducibility: bisecting a regression past a deploy is harder.

**Plan:**

- Adopt `uv pip compile` (or `pip-tools`) to produce `requirements.lock`
  and `backend/requirements.lock`.
- CI uses the lockfile; humans edit the source and re-compile.
- Renovate (or Dependabot) opens lockfile-bump PRs weekly.

**Target:** scheduled. Likely first PR after m12-pr13.

---

## TD-5 — Python 3.11 (CI) vs 3.13 (local) drift (OPEN)

**Symptom:** CI runs on Python 3.11 (Railway runtime). Several local
machines run 3.13.13. Pylance and runtime sometimes disagree (e.g.
`StrEnum` shape, `typing` reductions).

**Plan:**

- Either:
  - Pin local to 3.11 via `.python-version` and document; OR
  - Add 3.13 to CI matrix and migrate Railway to 3.13 when it goes GA on
    Railway's runtime catalogue.
- Decision needed (ADR draft).

**Target:** Stage A close.

---

## TD-6 — (RESERVED, see ADR-0036)

Placeholder; do not reuse the number.

---

## TD-7 — Per-stage Temporal activities (SHIPPED — m8-pr32)

**Was:** the entire pipeline ran in a single Temporal activity. Crash mid-
pipeline meant the whole thing re-ran (re-burning tokens).

**Now:** each phase is a separate activity. Restart resumes from last
green stage. ADR-0040.

**Anchor:** `backend/app/temporal/workflows/generation.py`.

---

## TD-8 — No mutation testing (OPEN)

**Symptom:** coverage thresholds are met but mutation kill rate is
unknown. Coverage is necessary, not sufficient — a 100% covered function
can still have arithmetic bugs that no assertion catches.

**Plan:**

- `mutmut` for `backend/app/api/middleware/`,
  `backend/app/services/usage_guard.py`, `ai_engine/registry/`.
- `stryker` for `frontend/src/lib/api`.
- Initial: nightly job; post results to a Slack channel.
- Promote to PR-blocking once kill rate baseline is established (>= 70%).

**Target:** Stage B.

---

## TD-9 — No per-region observability (OPEN, Stage B blocker)

**Symptom:** metrics and traces aggregate globally. When we cell-shard
in Stage B (ADR-0030), per-region root cause will be hard.

**Plan:**

- Add `cell_id` and `region` to every span attribute (today only on
  some).
- Per-cell dashboards in Grafana.
- Per-region SLOs separate from global.

**Target:** before first cell split.

---

## TD-10 — Dual-namespace lazy imports (OPEN)

**Symptom:** the dual-namespace shim (`backend.app` and `app`) is held
together by lazy imports in a few hot modules. Removing the dual
namespace would let us drop the lazy imports.

**Plan:**

- Choose one namespace (`backend.app` is canonical).
- Codemod the rest.
- Remove the shim and the lazy imports.

**Target:** Stage A close. Codemod helper under `tools/codemods/`.

---

## How to add a new TD item

1. Number it (next available; reserve numbers do not get reused).
2. Title — symptom in 4-7 words.
3. **Symptom** — observable behavior + measurable evidence.
4. **Why it matters** — concrete consequence.
5. **Plan** — bullet list, scoped to PRs.
6. **Target** — Stage A close, Stage B, or "post m12-prNN".
7. Anchor commit/PR if known.
8. Update this file in the same PR that introduces the debt.

---

## Anti-patterns we explicitly rejected

From blueprint §22:

- **Sprinkled `# TODO`s.** Not tracked unless they appear here.
- **"We'll fix it in v2."** v2 is not a plan; a TD item with a target is.
- **Renaming and calling it refactor.** A rename without behavior change
  is fine but doesn't retire debt.
- **Over-engineering for unproven scale.** TD-9 is acknowledged but not
  worked until Stage B is on the calendar.
