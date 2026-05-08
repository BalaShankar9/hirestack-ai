# Production Readiness Checklist

**Status:** Canonical · Required per-release gate
**Companion to:** [`WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md`](./WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md)

> Every production deploy must pass every gate in this checklist.
> A failed gate stops the deploy. There is no "we'll fix it next deploy" exception.

Use this as the body of the release issue / PR description for any change touching production.

---

## A · Pre-Merge Gates (PR-level)

These gates run on every PR. Failure blocks merge.

- [ ] **Lint** (ruff, eslint) — green
- [ ] **Typecheck** (mypy on changed packages, tsc) — green
- [ ] **Unit tests** — green; coverage ≥ 70% on changed packages (Stage A end requirement)
- [ ] **Integration tests** (testcontainers: Postgres, Redis, Temporal) — green
- [ ] **Contract tests** (event schemas, API schemas) — green
- [ ] **Tenancy isolation** regression test — green
- [ ] **Security scan** (secrets, dependency CVE) — green or risk-accepted by security
- [ ] **Migration safety linter** (if migration touched) — green
- [ ] **Eval gate** (if any prompt or model-routing change) — passes vs gold corpus baseline
- [ ] **`import-linter`** (bounded-context contracts) — green
- [ ] **Architecture Impact PR checklist** present and complete (blueprint §24)
- [ ] **ADR linked** if architectural decision

---

## B · Pre-Deploy Gates (release candidate)

Run after PR merge, before promoting build to production.

### B1 · Build & artifact
- [ ] Image built with pinned base + reproducible builder
- [ ] Image SBOM generated and stored
- [ ] Image scanned by Trivy / Grype — no critical CVEs
- [ ] Frontend bundle size within budget (Lighthouse CI gate)

### B2 · Schema & migration
- [ ] Any DB migration is **expand-only** in this release (no rename/drop)
- [ ] Migration tested against a copy of prod schema in CI
- [ ] Rollback migration committed alongside forward migration
- [ ] If a partitioned table is touched: `pg_partman` config updated and verified

### B3 · Configuration
- [ ] All required-in-prod env vars present in target environment
- [ ] Feature flag for new behavior created, defaulted **off**, owner + sunset date set
- [ ] Secrets rotated if new secret introduced

### B4 · Observability
- [ ] New code path emits required metrics / spans / logs / events (blueprint §13.2)
- [ ] New failure modes have alerts wired
- [ ] Runbook present for any new alert

### B5 · Cost
- [ ] Cost projection for new LLM call paths
- [ ] Cost regression alert thresholds updated if needed
- [ ] Per-customer cost dashboard reflects new code path

### B6 · Security
- [ ] New tables have RLS enabled (CI test)
- [ ] New routes have auth dependency
- [ ] New tools have sandbox tier classified
- [ ] Tenancy isolation test still green against prod-shaped fixtures

---

## C · Deploy-Time Gates

Run during deploy. Auto-rollback on failure.

- [ ] **Preview environment** deployed and smoke-tested
- [ ] **Canary 5%** for ≥ 5 min — SLO burn within budget
- [ ] **Canary 25%** for ≥ 10 min — SLO burn within budget
- [ ] **100%** rollout
- [ ] **Smoke suite** green (login, generate, fetch result, billing endpoint)
- [ ] **No alert firing** for the deployed services

If any of canary gates trip the SLO burn alert → **automatic rollback** + page on-call.

---

## D · Post-Deploy Verification (within 1 hour)

- [ ] Generation success rate within SLO over the last 30 min
- [ ] Generation p95 within SLO over the last 30 min
- [ ] API availability within SLO
- [ ] LLM cost per generation within budget
- [ ] No new Sentry error class with > 10 occurrences
- [ ] DLQ depth not increasing
- [ ] Outbox lag < 30s
- [ ] Temporal worker queue depth not increasing

---

## E · Post-Deploy Observability Window (24 hours)

- [ ] No SLO error budget burn > 5% from this deploy alone
- [ ] No customer-reported regression
- [ ] Cost-per-generation rolling-7d not regressed > 10%
- [ ] No security alert from `audit_log` patterns
- [ ] Feature flag adoption metrics emitting (if applicable)

---

## F · Stage-Specific Additional Gates

### Stage A only
- [ ] Single Postgres instance load < 70% CPU rolling-24h
- [ ] Redis hit rate ≥ 80% for cache namespace

### Stage B+
- [ ] Cross-cell consistency check (for any change touching cell-router data)
- [ ] Per-region SLO independently green
- [ ] WorkOS / Stripe / external SLA dashboards green
- [ ] Audit log emitted for any admin-class action

### Stage C+
- [ ] Multi-region failover test executed within last 30 days
- [ ] Cold-storage tier read sanity check

---

## G · Quarterly Production Health Review

Run quarterly. Failure of any item creates a P1 ticket with named owner.

- [ ] DR drill executed; RPO/RTO targets met
- [ ] Chaos drill executed; SLO unaffected
- [ ] All P0 register entries closed or actively in flight
- [ ] All P1 register entries with owner + ETA
- [ ] Risk matrix reviewed; no risk score ≥ 12 without mitigation in flight
- [ ] Tech debt register reviewed; one item retired
- [ ] Architecture decision log up to date with all material decisions of last quarter
- [ ] Postmortems for all Sev1/Sev2 published; action items on track
- [ ] Blueprint quarterly review timestamp updated
- [ ] Feature flag cleanup workflow ran; stale flags removed
- [ ] Dependency audit (CVE, unused, EOL) ran; PRs in flight

---

## H · "Hard No" Conditions (deploy stops, regardless of urgency)

Even in a hotfix scenario, these are absolute blockers:

- ❌ Migration with rename/drop in single step
- ❌ New table without RLS
- ❌ Secret in source
- ❌ Tenancy isolation test red
- ❌ Tool registered without sandbox tier
- ❌ Native `EventSource` introduced in frontend
- ❌ `code_ref` outside `RESOLVERS` allowlist
- ❌ Single-LLM-provider dispatch reintroduced
- ❌ Long-running task added to web pod
- ❌ `--no-verify` commit on the release branch

If any is present, the deploy is **cancelled** and the offending change is reverted before any further work.

---

## I · Approval Sign-offs (per release)

- [ ] Engineering: ___ (DRI for the release)
- [ ] Architecture-WG: ___ (if blueprint touched)
- [ ] Security: ___ (if security surface touched)
- [ ] AI team: ___ (if prompts / models / tools touched)
- [ ] On-call: ___ (acknowledges paged status during deploy window)

The release issue is not closed until all sign-offs are recorded.
