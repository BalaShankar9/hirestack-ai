---
title: Database Context
last_synced: 2026-05-08
watch_paths:
  - supabase/migrations
  - supabase/seed.sql
  - supabase/config.toml
canonical_sources:
  - supabase/migrations
  - docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md#10-data-architecture
  - docs/runbooks/outbox-partitions.md
  - docs/runbooks/staging-schema-sync.md
update_when:
  - a new migration is added (always)
  - a table's RLS policy changes
  - a new partitioned table is introduced (must use pg_partman)
  - a column rename / drop is staged (expand -> migrate -> contract)
  - retention policy changes
---

# Database Context

> Single source of truth: **Supabase Postgres**. Single migration root:
> [`supabase/migrations/`](../supabase/migrations) (P1-5 SHIPPED — the
> legacy `database/` root is removed). Every change to schema is a
> migration in this folder; nothing is hand-applied.

---

## TL;DR — 12 lines

1. **Postgres-of-record.** All durable state lives here. Redis is a cache
   and bus, never the source of truth.
2. **Single migration root.** [`supabase/migrations/`](../supabase/migrations)
   contains 61 migrations from `20260206000000_*.sql` to
   `20260502010000_*.sql`. Naming: `YYYYMMDDHHMMSS_<slug>.sql`.
3. **64 / 64 multi-tenant tables enforce RLS** keyed on `org_id`. CI test
   `tests/security/test_tenancy_isolation.py` blocks regressions.
4. **Partitioned tables use `pg_partman`** (P0-1 SHIPPED — m7-pr27a).
   `PartitionMaintenanceWorkflow` (Temporal cron) verifies health and
   warns 14 days before any partition expires.
5. **Outbox table** `events_outbox` is partitioned monthly. Producers and
   consumers use `FOR UPDATE SKIP LOCKED`. ACK on success only (P0-3).
6. **AI flight recorder** `ai_invocations` is partitioned monthly,
   84-month retention for compliance. Every model call writes one row, no
   exceptions (blueprint §6.7).
7. **`org_cost_hourly` materialized view** refreshes every 60s via
   `pg_cron` (P1-8 SHIPPED — m12-pr07). Powers `usage_guard` cap checks.
8. **Schema discipline:** **expand → migrate → contract**. No rename or
   drop in the same migration that introduces a new column. Multi-step
   guarantees zero-downtime deploys.
9. **Backups:** Supabase automated daily snapshots; PITR enabled for
   production. DR drill quarterly (`DRDrillWorkflow`).
10. **Vector store:** `pgvector` extension; lives in tables alongside the
    relational data (e.g. `aim_source_embeddings`). Migration off pgvector
    to Turbopuffer/Qdrant is Stage C (blueprint §10.6).
11. **`feature_flag_audit`** append-only history (P1-9 SHIPPED — m12-pr09).
    Idempotent (skips when value unchanged); fed by both runtime flips and
    per-deploy snapshots.
12. **Idempotency keys** stored in `idempotency_keys` (24h TTL). Hit by the
    middleware on every POST/PATCH/DELETE.

---

## Migration discipline

```
supabase/migrations/
  20260206000000_init.sql
  20260207HHMMSS_<slug>.sql
  ...
  20260502010000_<slug>.sql            # latest at last sync
```

Every migration is one file, one transaction (`BEGIN ... COMMIT`), and
includes:

1. The schema change (CREATE/ALTER/DROP).
2. RLS enablement (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`).
3. RLS policies (`CREATE POLICY ...`).
4. Indexes if any.
5. Comments (`COMMENT ON TABLE / COLUMN`).

Forbidden in a single migration:

- Adding a column AND writing to it AND making it NOT NULL.
- Renaming a column read by deployed code (split into two migrations).
- Dropping a column read by deployed code (split into two migrations).
- Adding a partitioned table without a `pg_partman` `part_config` row.
- Adding a multi-tenant table without RLS in the same migration.

Local reset / apply:

```
cd "<repo root>"
supabase db reset                              # local only
supabase migration new <slug>                  # author new migration
supabase db push                               # apply locally
```

CI applies migrations against a fresh container before running tests.
Production rolls forward via Supabase managed migration runner.

---

## Tenancy and RLS

Every multi-tenant table:

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;

CREATE POLICY <t>_org_isolation ON <t>
  USING (org_id = current_setting('request.jwt.claims', true)::jsonb ->> 'org_id'::text)
  WITH CHECK (org_id = current_setting('request.jwt.claims', true)::jsonb ->> 'org_id'::text);
```

The JWT signed by Supabase Auth carries `org_id` (and now `cell_id` per
blueprint §5.2). The backend sets the JWT into `request.jwt.claims` so
RLS sees the user's tenancy on every query.

Service-role queries (background jobs) explicitly set `request.jwt.claims`
or use a service role key with care. Background workers MUST scope queries
by `org_id` even when bypassing RLS, to keep query plans efficient.

CI guard:

- `backend/tests/security/test_tenancy_isolation.py` creates two orgs and
  asserts user A sees zero rows of user B's data across every multi-tenant
  table. New table without RLS = red.

---

## Key tables (current inventory)

This list is illustrative — the canonical inventory is the migration
folder. Read the most recent migrations to see the working set.

### Core domain

| Table | Purpose |
|---|---|
| `users` | account profile, preferences |
| `orgs` | multi-tenant root; tier, plan, cell_id |
| `org_members` | RBAC: user_id × org_id × role |
| `applications` | a job application the user is working on |
| `application_versions` | A/B variants per application |
| `document_library` | 3-tier docs: benchmark / fixed / tailored |
| `document_catalog` | indexable catalog of documents |
| `profiles` | candidate profiles (parsed resume snapshot) |
| `profiles_embeddings` | pgvector embeddings of profile chunks |

### Generation pipeline

| Table | Purpose |
|---|---|
| `generation_jobs` | top-level row per generation; status machine |
| `generation_job_events` | per-stage events (started/completed/error) |
| `generation_artifacts` | per-stage output references |
| `evidence_items` | raw evidence chunks (source, span, extracted text) |
| `evidence_ledger_items` | classified evidence: VERBATIM > DERIVED > INFERRED > USER_STATED |

### AI runtime + observability

| Table | Purpose |
|---|---|
| `ai_invocations` | flight recorder: one row per model call (partitioned monthly) |
| `ai_tool_invocations` | tool call audit (sandbox tier, capability token, result) |
| `ai_tools` | tool registry: name, code_ref, sandbox_tier, schema |
| `org_cost_hourly` | materialized view: $ spent per org per hour (refreshed by pg_cron) |
| `prompt_versions` | content hash + metadata per prompt template |

### Eventing

| Table | Purpose |
|---|---|
| `events_outbox` | outbox pattern; partitioned monthly; FOR UPDATE SKIP LOCKED |
| `events_archive` | S3-archived monthly partitions (after 90d) |
| `event_dlq` | poison messages awaiting `DLQReplayWorkflow` |

### Other surfaces

| Table | Purpose |
|---|---|
| `tasks` | TODO/Mission tasks for the user |
| `ats_scans` | per-application ATS scoring history |
| `interview_sessions` | LongLivedSessionWorkflow state mirror |
| `salary_analyses` | salary coach output |
| `learning_streaks` | daily learning tracker |
| `tracked_companies` | watchlist + auto-prep |
| `job_sync_runs` | job board pull history |
| `feature_flag_audit` | append-only flag flip history (P1-9) |
| `idempotency_keys` | API idempotency cache (24h TTL) |
| `org_cost_caps` | per-org daily $ cap overrides (P0-4) |

There are ~64 tables in total today; the migration folder is canonical.

---

## Partitioned tables

Both `events_outbox` and `ai_invocations` (and `ai_tool_invocations`) are
range-partitioned by `created_at`, monthly. Managed by `pg_partman`.

Discipline (P0-1 SHIPPED — m7-pr27a):

- Migration `20260508120000_outbox_partition_rotation.sql` registers the
  table with `pg_partman`.
- `PartitionMaintenanceWorkflow` runs daily:
  - creates the next 6 months of partitions in advance,
  - emits a metric `db.partition.next_expiry_days`,
  - alerts if `<14`.
- Old partitions move to `events_archive` via `EventArchiveWorkflow`
  monthly; raw partition is dropped after archive succeeds.

`ai_invocations` keeps **84 months** of partitions live (compliance
window — see blueprint §6.7). Older partitions are exported to S3
Parquet for cold queries.

Future test (blueprint §21): `tests/db/test_partition_health.py` to assert
the next-expiry alert fires.

---

## Schema-change discipline (expand → migrate → contract)

Every breaking change is **three** migrations:

1. **Expand:** add the new column / table / index. Old code keeps working.
2. **Migrate:** ship code that reads/writes the new shape. Backfill data
   if needed.
3. **Contract:** drop the old column / table / index after one full deploy
   cycle.

Examples:

- Renaming `applications.title` to `applications.role_title`:
  expand (add new), migrate (dual-write + read new), contract (drop old).
- Splitting `document_library` into 3 tiered tables: same dance, three PRs.

Reviewers reject single-PR rename/drop migrations that touch deployed code.

---

## Materialized views and `pg_cron`

`org_cost_hourly` (P1-8 SHIPPED — m12-pr07):

```sql
CREATE MATERIALIZED VIEW org_cost_hourly AS
  SELECT org_id, date_trunc('hour', created_at) AS hour,
         sum(cost_cents) AS cost_cents,
         count(*) AS calls
  FROM ai_invocations
  GROUP BY org_id, date_trunc('hour', created_at);

SELECT cron.schedule('org-cost-hourly-refresh', '* * * * *',
                     'REFRESH MATERIALIZED VIEW CONCURRENTLY org_cost_hourly');
```

`usage_guard` reads this view (not raw `ai_invocations`) to keep the
per-request cost check O(1).

---

## Vector storage

`pgvector` extension is enabled. Embedding tables follow the pattern:

```sql
CREATE TABLE <thing>_embeddings (
  id uuid PRIMARY KEY,
  <thing>_id uuid NOT NULL REFERENCES <thing>(id) ON DELETE CASCADE,
  org_id uuid NOT NULL,
  chunk_text text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(1536) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON <thing>_embeddings USING ivfflat (embedding vector_cosine_ops);
ALTER TABLE <thing>_embeddings ENABLE ROW LEVEL SECURITY;
```

Per blueprint §6.2, every embedding row carries `provenance` so RAG
results can travel to the prompt and the post-output guard knows the
source.

Migration off pgvector is Stage C (blueprint §22 / SCALABILITY_ROADMAP).

---

## Backups, DR, retention

| Concern | Strategy |
|---|---|
| Daily backup | Supabase automated; 7-day rolling snapshot |
| PITR | Supabase managed (production only) |
| DR drill | Quarterly via `DRDrillWorkflow`: restore latest snapshot to staging, run smoke pipeline, assert pass |
| `events_outbox` retention | 90 days online, then `EventArchiveWorkflow` exports monthly partition to S3 Parquet |
| `ai_invocations` retention | 84 months online (compliance), then S3 Parquet |
| User-initiated deletion | GDPR right-to-erase: `DeleteOrgWorkflow` (cascade per ADR / org_delete cascade work 2026-04-10) |

---

## Cross-cell uniformity

Every cell has the same schema. Migrations apply identically across cells.
Adding a per-cell-only table is forbidden — promote to a global pattern
or use `org_id` partitioning instead.

---

## "How do I…" cheat sheet

| Task | Recipe |
|---|---|
| Add a multi-tenant table | new migration; `org_id NOT NULL`; enable RLS; isolation policy; CI test must pass |
| Add a partitioned table | new migration; `PARTITION BY RANGE (created_at)`; `pg_partman` `part_config` row; future-partitions cron |
| Rename a column | three migrations: expand / migrate / contract |
| Add a vector column | follow pattern above; ivfflat index; RLS |
| Add a materialized view | new migration; `pg_cron` refresh schedule; document refresh cost |
| Backfill historical data | one-shot migration that runs in batches (`LIMIT 10000` loops) under `lock_timeout` |
| Audit who changed what | `feature_flag_audit` for flags; for tables, write `audit.<table>_log` (manual today; Stage B `audit_log` global) |

---

## Watch list

When you change schema, also check:

- [`backend/app/services/cost_attribution.py`](../backend/app/services/cost_attribution.py)
  if you change `ai_invocations` or `org_cost_hourly`.
- [`backend/app/core/events/`](../backend/app/core/events/) if you change
  `events_outbox` shape.
- [`backend/tests/security/test_tenancy_isolation.py`](../backend/tests/security/test_tenancy_isolation.py)
  every time you add a new multi-tenant table — extend the test.
- [`docs/runbooks/outbox-partitions.md`](../docs/runbooks/outbox-partitions.md)
  if partitioning policy changes.
- [`docs/runbooks/staging-schema-sync.md`](../docs/runbooks/staging-schema-sync.md)
  if migrations apply order changes.
