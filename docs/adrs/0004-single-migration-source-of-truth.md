# ADR-0004: `supabase/migrations/` is the only source of truth for schema

Date: 2026-04-28
Status: Accepted
Updated: 2026-05-21 (m9-pr33 — `database/migrations/` directory removed)
Supersedes: implicit dual-folder convention used through April 2026

## Context

Until m9-pr33 (M10), the repository carried two migration folders:

- `supabase/migrations/` — what `supabase db push` deploys to production.
- `database/migrations/` — a legacy folder predating the Supabase CLI, kept around because pre-CLI migrations and a handful of post-CLI ones still lived there.

This duality produced silent production gaps at least twice:

1. **`resume_html` column.** Authored in `database/migrations/20260418_add_resume_html_column.sql`, never mirrored to `supabase/`. The generation-job runner failed PGRST204 on every persistence attempt until `supabase/migrations/20260421000000_add_resume_html_column.sql` shipped.
2. **`processed_webhook_events` table.** Authored in `database/migrations/20260420_stripe_webhook_idempotency.sql`, never mirrored. Stripe webhook retries would have double-granted subscriptions; caught by the S2 audit before any retry actually fired (April 2026).

The pattern is the same: someone sees a `database/migrations/` folder, follows the local convention, and ships a migration that production never receives.

## Decision

`supabase/migrations/` is the **single and only** source of truth for production schema. New schema changes go there and only there.

As of m9-pr33 (M10), the `database/` directory has been **deleted entirely**. The 3 remaining orphaned migrations (`processed_queue_events`, `idempotency_keys`, `consumed_events`) were mirrored into `supabase/migrations/` first; the rest were either already mirrored or were pre-CLI baselines folded into `20260206000000_full_schema.sql`.

Three regression tests enforce the single-root rule:

- `backend/tests/unit/test_supabase_migrations_mirror.py::test_legacy_database_migrations_dir_does_not_exist` — re-creating `database/migrations/` is a build-time failure.
- `backend/tests/unit/test_supabase_migrations_mirror.py::test_every_public_table_has_rls_enabled` — every public table created in `supabase/migrations/` must have RLS enabled.
- `backend/tests/unit/test_migration_placement_invariants.py` — the `generation_jobs.status` column width invariant (the canary that detected the original drift) is pinned against `supabase/migrations/` only.

## Consequences

- Future schema work has one well-marked place to land.
- The legacy directory can no longer be recreated without a regression-test failure.
- Operators only need to know one command: `supabase db push`.
- The bundle SQL files (`apply_*.sql`, `combined_migration.sql`, `hirestack_full_migration.sql`) and the `database/README.md` warning sign were removed alongside the directory; recovery now flows through `supabase db push` exclusively.

