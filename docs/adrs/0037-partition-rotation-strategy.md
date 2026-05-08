# ADR-0037: Automated partition rotation for `events_outbox`

Status: Accepted — 2026-05-08 (M7-A / m7-pr27a)
Owners: Platform Core squad (@BalaShankar9)
Supersedes: none
Superseded by: none
Related: ADR-0014 (Event bus and outbox), blueprint §6, §7, §17 (P0-1)

## Context

`public.events_outbox` is partitioned `BY RANGE (occurred_at)` with monthly
partitions named `events_outbox_YYYY_MM`. The original migration
(`20260521010000_events_outbox.sql`) seeded **three** partitions
(current + next two) inside a one-shot `DO` block. There is no
automation that creates the next partition before the current
trailing partition is exhausted.

This is the highest-blast-radius defect on the production register
(P0-1). Concretely:

- The seed migration ran at deployment. As of 2026-05-08, partitions
  exist for 2026-05, 2026-06, 2026-07.
- On 2026-08-01 00:00 UTC, every `INSERT` into `events_outbox` will
  fail with `no partition of relation "events_outbox" found for row`.
- The outbox is in the synchronous write path of every domain event.
  Failure mode: business writes succeed; outbox row insert raises;
  the application transaction rolls back; user sees 500.

The blueprint §17 originally listed `pg_partman` as the chosen tool.
We evaluated this option and rejected it for the reasons in the
"Considered alternatives" section below.

## Decision

Install `pg_cron` and a small native PL/pgSQL function:

1. **Extension**: `CREATE EXTENSION IF NOT EXISTS pg_cron;` — Supabase
   exposes pg_cron as a first-class extension, no separate provisioning.
2. **Function**: `public.ensure_events_outbox_partitions(p_months_ahead int)`
   — idempotent, creates any missing monthly partition between the
   current month and `p_months_ahead` months in the future. Naming
   convention `events_outbox_YYYY_MM` is preserved (no rename of
   existing partitions).
3. **Schedule**: `cron.schedule('events-outbox-rotation', '1 0 * * *', ...)`
   — runs daily at 00:01 UTC, calls the function with `p_months_ahead := 4`.
4. **Bootstrap**: the migration calls the function once during deploy
   to immediately ensure 4 months of headroom, closing the P0 gap on
   the same migration that lands.
5. **Observability**: the function increments a counter row in
   `public.partition_rotation_audit` on each invocation. An alert fires
   if the most recent row is older than 36 hours.

## Considered alternatives

### A. `pg_partman`
- ✗ Default child-table naming (`events_outbox_pYYYYMMDD`) is
  incompatible with the existing `events_outbox_YYYY_MM` partitions.
  Adopting requires either renaming live partitions (table-level lock
  during rename, plus violation of expand-only discipline) or running
  pg_partman alongside legacy partitions — which produces overlapping
  bound conflicts during the cutover month.
- ✗ ~7,000 LOC of PL/pgSQL operational surface for a use case that
  fits in a 50-line function.
- ✗ Stage-A scale (single Postgres, single fanout) does not require
  pg_partman's advanced features: retention by sub-partitioning,
  sub-partition templates, multi-table maintenance jobs.
- Status: **Revisit at Stage B** — when we exceed any of (a) >5
  partitioned tables, (b) >100 partitions per table, (c) cross-shard
  rotation. Captured in `docs/architecture/SCALING_PHASES.md`.

### B. Application-level cron (Celery / Temporal scheduled workflow)
- ✗ Couples a database-availability concern to an application-tier
  scheduler. If the worker is down, the partition is not created and
  the symptom appears at the database boundary anyway.
- ✗ Adds a network hop and credential surface.
- ✗ Harder to validate in `psql` during incident response.

### C. Status quo + manual operator runbook
- ✗ Already failed: P0-1 was logged because no operator ran the manual
  step. Reliance on humans for a deterministic, periodic, in-database
  task is not acceptable.

## Consequences

### Positive
- P0-1 closed on this PR. No insert can fail because of a missing
  partition for at least 4 months ahead at any point in time.
- Zero application-tier dependency. The rotation runs even if the API,
  workers, and Temporal cluster are all down.
- `pg_cron` is now available for other periodic database jobs (e.g.,
  cache eviction audits, metric materialization). Existing usage limited
  by ADR-NNNN gate (any new cron job requires its own ADR).

### Negative
- One additional Postgres extension. Audited surface, low risk on
  Supabase managed.
- `cron.schedule` runs in the `postgres` superuser context; we
  `REVOKE ALL` then `GRANT EXECUTE` on the function to `service_role`
  only. Documented in the migration.
- Operator must remember to migrate this scheduling out of pg_cron at
  Stage B if we move to Aurora (Aurora supports `pg_cron` only on
  Aurora Postgres Standard since 2023; gated in M11).

### Validation evidence
- Migration applied to local dev: `psql -c 'SELECT
  public.ensure_events_outbox_partitions(4)'` returns count of partitions
  created.
- `SELECT * FROM cron.job WHERE jobname = 'events-outbox-rotation'`
  shows the schedule on staging.
- Integration test
  `backend/tests/integration/test_outbox_partitions.py::test_next_four_months_exist`
  passes against staging.

## Sunset and review

Stage-B review trigger (per `SCALING_PHASES.md`):
- > 5 partitioned tables in Postgres, OR
- > 100 partitions on `events_outbox`, OR
- migration to Aurora.

At that point, re-evaluate `pg_partman` adoption (with controlled
rename of historical partitions during a maintenance window).

## References
- Blueprint §6 (event bus), §7 (outbox), §17 (anti-pattern register P0-1)
- ADR-0014 (event bus and outbox)
- Runbook: `docs/runbooks/outbox-partitions.md`
- Migration: `supabase/migrations/20260508120000_outbox_partition_rotation.sql`
