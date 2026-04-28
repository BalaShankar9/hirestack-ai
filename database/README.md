# `database/` — read me before touching anything

**Production deploys do NOT come from this folder.** They come from
`supabase/migrations/`, applied by `supabase db push`. See the S2
audit at `docs/audits/S2-data-migrations.md` and the schema-drift
pivot note for the full story.

## What lives here, and what it's actually for

### `database/migrations/` — legacy mirror

Pre-supabase-CLI migrations plus a few that were authored after
the CLI was adopted but never made it into `supabase/migrations/`
(the orphan trap). The S2 regression test
`backend/tests/unit/test_supabase_migrations_mirror.py` now blocks
new orphans at CI.

You should not need to touch this folder. New schema changes belong
in `supabase/migrations/` only.

### Bundle scripts at this level (DANGEROUS)

| File                              | What it is                                                     | Safe to run? |
|-----------------------------------|----------------------------------------------------------------|--------------|
| `apply_all_migrations.sql`        | Concatenated dump of `database/migrations/*.sql`               | ❌ No — superseded |
| `apply_all_pending.sql`           | Snapshot of "everything that wasn't yet in prod" as of Apr-13  | ❌ No — out of date |
| `apply_production_wave23.sql`     | Snapshot for the wave-23 incident recovery                     | ❌ No — historical |
| `combined_migration.sql`          | Same idea as `apply_all_migrations.sql`, different timestamp   | ❌ No — duplicate |
| `hirestack_full_migration.sql`    | Identical bytes to `apply_all_migrations.sql`                  | ❌ No — duplicate |

These files exist for two narrow reasons:

1. **Schema-invariant testing.** `backend/tests/unit/test_schema_invariants.py`
   parses `combined_migration.sql` + `apply_production_wave23.sql` to
   assert structural invariants (column types, FK CASCADE rules,
   unique constraints) without spinning up a real Postgres. This is
   read-only consumption — the tests never execute the SQL.
2. **Disaster recovery on a fresh database.** If somebody is
   bootstrapping a new Postgres from scratch and cannot use the
   Supabase CLI for some reason, `hirestack_full_migration.sql` is a
   one-shot equivalent. Use as a last resort and follow up with
   `supabase db push` to bring the migration history table in sync.

### Never run these against production directly

If you `psql $DATABASE_URL < apply_all_pending.sql` against an
already-migrated database you will get duplicate-table errors at
best and silent data corruption at worst (some statements are
`ALTER TABLE … ADD COLUMN` without `IF NOT EXISTS`).

### How to ship a schema change

1. Add a new file to `supabase/migrations/` with a timestamp prefix
   that sorts after every existing one.
2. Run `supabase db push --dry-run` locally to preview.
3. Run the backend unit suite — `test_supabase_migrations_mirror`,
   `test_rls_coverage`, and `test_hotpath_indexes` will catch the
   common regression classes.
4. After merge, an operator runs `supabase db push` against
   production.

### Cleanup deferred

The bundle scripts could in principle be regenerated on demand from
`supabase/migrations/` and deleted from the repo. That is tracked as
a follow-up; deleting them now would break
`test_schema_invariants.py` and `scripts/run_migrations.py`. If you
pick up that work, both consumers need to migrate to read from
`supabase/migrations/` directly first.
