# ADR-0004: `supabase/migrations/` is the only source of truth for schema

Date: 2026-04-28
Status: Accepted
Supersedes: implicit dual-folder convention used through April 2026

## Context

The repository carries two migration folders:

- `supabase/migrations/` — what `supabase db push` deploys to production.
- `database/migrations/` — a legacy folder predating the Supabase CLI, kept around because pre-CLI migrations and a handful of post-CLI ones still live there.

This duality has produced silent production gaps at least twice:

1. **`resume_html` column.** Authored in `database/migrations/20260418_add_resume_html_column.sql`, never mirrored to `supabase/`. The generation-job runner failed PGRST204 on every persistence attempt until `supabase/migrations/20260421000000_add_resume_html_column.sql` shipped.
2. **`processed_webhook_events` table.** Authored in `database/migrations/20260420_stripe_webhook_idempotency.sql`, never mirrored. Stripe webhook retries would have double-granted subscriptions; caught by the S2 audit before any retry actually fired (April 2026).

The pattern is the same: someone sees a `database/migrations/` folder, follows the local convention, and ships a migration that production never receives.

## Decision

`supabase/migrations/` is the **single source of truth** for production schema. New schema changes go there and only there.

`database/migrations/` is **frozen**. The pre-CLI files stay (they document history and are referenced by `test_schema_invariants.py`), but nothing new should be added.

Two regression tests enforce the rule:

- `backend/tests/unit/test_supabase_migrations_mirror.py` — every 2026+ file in `database/migrations/` must have a slug-equivalent counterpart in `supabase/migrations/`.
- `backend/tests/unit/test_rls_coverage.py` — every public table created in `supabase/migrations/` must have RLS enabled.
- `backend/tests/unit/test_hotpath_indexes.py` — pinned hot-path indexes cannot silently disappear.

The bundle SQL files at the `database/` root (`apply_*.sql`, `combined_migration.sql`, `hirestack_full_migration.sql`) are flagged as recovery-only by `database/README.md`.

## Consequences

- Future schema work has one well-marked place to land.
- The mirror test fails fast at CI when somebody forgets the rule again.
- Operators only need to know one command: `supabase db push`.
- Cleaning up the bundle SQL files (and migrating `test_schema_invariants.py` to read from `supabase/migrations/` directly) remains as deferred follow-up work; the README documents this.
