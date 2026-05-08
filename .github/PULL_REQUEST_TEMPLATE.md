<!--
PR template — every PR uses it. The Architecture Impact section is enforced
by .github/workflows/architecture.yml (the `pr-template-check` job will fail
the build if the section is removed or its required checkboxes are missing).
Canonical reference: docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md
-->

## Scope

- **Domain / bounded context:** <!-- e.g., ai_engine, identity, billing, generation, realtime, eventing -->
- **Type:** feat | fix | refactor | chore | security | migration | infra
- **Linked issue / ADR:**

## Summary

<!-- One paragraph: what changes and why now. Not a changelog. -->

---

## Architecture Impact (REQUIRED — do not delete)

> Triggers required: any PR that touches `ai_engine/`, `backend/app/services/`,
> `backend/app/api/`, `backend/app/core/`, `backend/app/temporal/`,
> `packages/events/`, `supabase/migrations/`,
> `frontend/src/lib/sse/**`, or `docs/architecture/`.
>
> If none apply, tick "No architecture impact" below and skip the rest.

- [ ] **No architecture impact** (single-file fix, copy change, dependency bump <1 minor, internal-only refactor with zero call-site changes).

If unticked, every item below MUST be addressed:

- [ ] **Bounded context boundary:** lists every cross-context import added/removed.
- [ ] **Contract impact:** lists every new/changed event type, API route, DB table, prompt version.
- [ ] **Schema migration safety:** expand-only; no rename/drop in same step; rollback migration committed.
- [ ] **Forbidden anti-patterns:** confirmed none of `WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md` §17 (AP-1..AP-18) violated.
- [ ] **Observability:** new code path emits required metrics / spans / logs / events (blueprint §13.2).
- [ ] **Cost impact:** projected $/generation delta is `<5%` OR explained below.
- [ ] **Security:** RLS + auth dependency + capability checks where applicable; tenancy isolation test still green.
- [ ] **Tests:** unit + integration + (if applicable) contract / chaos / eval added.
- [ ] **Blueprint update:** if architecture changed, blueprint section ___ updated **in this PR**.
- [ ] **ADR:** if decision-class change (new dep, new boundary, new workflow type, breaking event change, new sandbox tier), ADR-____ added/updated using `docs/architecture/ADR_TEMPLATE.md`.
- [ ] **Runbook:** if new failure mode or new alert, `docs/runbooks/` updated.

---

## Risk

- [ ] No DB schema change
- [ ] No public API change
- [ ] Behind feature flag: `ff_____` (flag must be in `config/feature_flags.yaml` with sunset date)
- [ ] Tenancy isolation test passes
- [ ] No new `TODO` without expiration in `TODO(YYYY-MM-DD): description` format

**Blast radius (max scope of breakage if this PR is wrong):**
<!-- e.g., "single endpoint", "all generation jobs for one tenant", "all tenants" -->

## Rollback

- **Reversal mechanism:** revert PR | flag-off | data fix | re-deploy previous tag
- **Data state on rollback:** lossless | requires backfill | irreversible (forbidden — split PR)
- **Time to rollback:** _seconds_ (flag), _minutes_ (revert), _hours_ (data restore)

## Verification

- [ ] Unit tests
- [ ] Integration tests (testcontainers: Postgres / Redis / Temporal)
- [ ] Contract tests (event schemas, API schemas)
- [ ] Manual smoke against preview environment
- [ ] Eval gate (if prompt or model-routing change)
- [ ] Tenancy isolation regression (auto)

## Operational notes

- **New env vars:**
- **New required-in-prod settings:**
- **New alerts / dashboards:**
- **Owner / on-call DRI for the new code:**
