# S2 Data & Migrations — audit (2026-04-21)

Squad: Data & Migrations
Owner: this autonomous run
Pivot doc: `/memories/repo/schema-drift-2026-04-21.md`

## Setup

- Source of truth for production: **`supabase/migrations/`** (deployed
  by `supabase db push`).
- `database/migrations/` is a **legacy mirror** that nothing reads
  for prod. Migrations placed only here are orphans.
- Root-level files (`apply_all_migrations.sql`,
  `apply_all_pending.sql`, `apply_production_wave23.sql`,
  `combined_migration.sql`, `hirestack_full_migration.sql`) are
  bundle scripts. Dangerous if mis-run; keep as recovery aids only.

## Inventory

| Folder                        | Files | Notes |
|-------------------------------|-------|-------|
| `supabase/migrations/`        | 34    | Source of truth.  |
| `database/migrations/`        | 9     | Legacy mirror — must match supabase/. |
| `database/*.sql` (root)       | 5     | Bundle / recovery scripts. |

### Drift between the two folders

| `database/migrations/` file                                 | `supabase/migrations/` counterpart                        | Status |
|-------------------------------------------------------------|-----------------------------------------------------------|--------|
| `001_initial_schema.sql`                                    | superseded by `20260206000000_full_schema.sql`            | OK (legacy)         |
| `002_frontend_tables.sql`                                   | superseded by full_schema                                 | OK (legacy)         |
| `003_add_ps_portfolio_columns.sql`                          | superseded                                                | OK (legacy)         |
| `20250610_atomic_module_status.sql`                         | superseded                                                | OK (legacy)         |
| `20250611_add_recovery_attempts.sql`                        | superseded                                                | OK (legacy)         |
| `20260417_knowledge_library_and_global_skills.sql`          | `20260417000000_knowledge_library_and_global_skills.sql`  | OK (identical)      |
| `20260418_add_resume_html_column.sql`                       | `20260421000000_add_resume_html_column.sql`               | OK (equivalent SQL) |
| **`20260420_stripe_webhook_idempotency.sql`**               | **NONE**                                                  | **🔥 ORPHAN — prod missing this table** |
| `20260422_widen_generation_jobs_status.sql`                 | `20260422000000_widen_generation_jobs_status.sql`         | OK                  |

### Risk: `processed_webhook_events`

- Table is referenced by `app/services/billing.py` (lines 195, 209, 217)
  for Stripe webhook idempotency.
- `TABLES["processed_webhook_events"]` is registered in
  `app/core/database.py:241`.
- `test_prod_readiness_audit::test_webhook_handler_skips_duplicate_event`
  exists and passes against mocks.
- **Production likely does not have this table.** First Stripe
  webhook redelivery would attempt `db.get(TABLES["processed_webhook_events"], …)`
  and fail with PGRST204, then attempt the create and double-grant
  the subscription side-effect.

## Fix queue

| ID  | Title                                                          | Risk |
|-----|----------------------------------------------------------------|------|
| F1  | Mirror Stripe webhook idempotency to `supabase/migrations/`     | HIGH — duplicate subscriptions on retry |
| F2  | Add `test_supabase_migrations_mirror_database` regression pin   | MED  |
| F3  | RLS audit pass — every user-scoped table has `enable row level security` | MED |
| F4  | Index audit — top 5 hot read paths covered                      | MED  |
| F5  | Document `apply_*.sql` bundle scripts as recovery-only           | LOW  |
| F6  | S2 sign-off + ADR on the dual-folder migration setup            | LOW  |

Each fix lands as a separate ≤500 LOC commit per squad rule. F1 + F2 ship together because they are inseparable (the test would fail without the file).
