# S2 Data & Migrations — sign-off (2026-04-28)

Squad: Data & Migrations
Status: **GREEN**
Audit: `docs/audits/S2-data-migrations.md`
ADR: `docs/adrs/0004-single-migration-source-of-truth.md`

## Production-readiness bar

| # | Check                                                                            | Status |
|---|----------------------------------------------------------------------------------|--------|
| 1 | One declared source of truth for production schema                               | ✅ ADR-0004; `supabase/migrations/` only |
| 2 | No orphan migrations (file in `database/migrations/` with no supabase/ mirror)   | ✅ Stripe orphan fixed; regression test pins it |
| 3 | RLS enabled on every public table                                                | ✅ 70/70 tables; regression test enforces |
| 4 | Hot read paths covered by indexes                                                | ✅ Audit + 2 missing indexes added; regression pin |
| 5 | Dangerous bundle scripts called out as recovery-only                             | ✅ `database/README.md` |
| 6 | Operator runbook for the schema-cache reload (`NOTIFY pgrst`)                    | ✅ included in every new migration |
| 7 | Backend unit suite green and <15s                                                | ✅ 1226 passed in 6.08s |

## Fixes shipped

| ID  | Title                                                                                | Commit  |
|-----|--------------------------------------------------------------------------------------|---------|
| F1  | Mirror Stripe webhook idempotency to `supabase/migrations/` (with deny-by-default RLS) | (pending push) |
| F2  | `test_supabase_migrations_mirror` — block future orphans at CI                        | bundled with F1 |
| F3  | Enable RLS on `ai_platform_spend_daily` + RLS coverage regression test               | (pending push) |
| F4  | Add `audit_logs.user_id` and `api_usage.user_id` indexes + hot-path pin              | (pending push) |
| F5  | `database/README.md` warning on bundle SQL                                           | f03481f |
| F6  | ADR-0004 + this sign-off                                                             | (this commit) |

(Per blueprint: commits stay local until the P4-S10 staging-deploy gate.)

## Operator action queue

After P4-S10 push to staging, run these against production:

```sh
supabase db push   # applies the three new supabase/migrations/ files
```

The migrations are all idempotent (`IF NOT EXISTS` / RLS enable is a no-op if already on), so re-running on top of an already-migrated database is safe.

## Deferred (NOT staging blockers)

- Migrate `backend/tests/unit/test_schema_invariants.py` and `scripts/run_migrations.py` to read from `supabase/migrations/` directly so the bundle SQL files at `database/` root can be deleted.
- TABLES dict alignment audit — verify every key in `app/core/database.TABLES` corresponds to a real table in `supabase/migrations/`.
- ON DELETE CASCADE verification for the org-delete and job-lifecycle paths (some FK columns use `ON DELETE SET NULL` which may be intentional or accidental).
- Deny-write policies on the `ai_platform_spend_daily` and `processed_webhook_events` tables (currently relying on no-policies-means-deny — explicit policies would be clearer to readers).

These are picked up by S3 (Pipeline Runtime) and a future S11 hardening pass.

## Next squad

S3 Pipeline Runtime starts now in parallel.
