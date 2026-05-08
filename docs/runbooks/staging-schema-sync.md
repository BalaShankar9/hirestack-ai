# Runbook: staging schema sync (m11-pr45)

Keeps the staging Postgres database **shape-identical** to prod
without copying any rows. Runs weekly via GitHub Actions; can be
triggered manually after a hotfix migration so staging tests catch
the new schema before the next release lands.

## What it does

* Dumps the prod schema with `pg_dump --schema-only --clean
  --if-exists --no-owner --no-privileges --no-tablespaces`.
* Applies the dump to staging inside a single transaction with
  `psql --single-transaction --variable=ON_ERROR_STOP=1`.
* On any failure, staging is rolled back to its pre-sync state.

It does **not** copy:
* Table rows (intentional — staging holds its own seed data).
* Roles, grants, tablespaces (staging RBAC is independent).
* Extensions that aren't already installed on staging — `pg_dump`
  emits `CREATE EXTENSION IF NOT EXISTS` only for extensions
  already present in the dumped schemas.

## When to run it manually

* You just shipped a hotfix migration to prod that didn't go
  through the normal release pipeline. Trigger
  `Staging schema sync` from the Actions tab so staging tests on
  the next PR see the same schema.
* QA reports "test environment is missing the new column from
  ticket X" — likely a missed weekly run. Re-trigger.

## How to run locally

For dev work, use the local mirror compose file rather than
pointing at the real staging DB:

```bash
docker compose -f infra/staging-mirror.compose.yml up -d
export STAGING_DATABASE_URL="postgres://hirestack:devpw@localhost:55432/hirestack_staging"
export PROD_DATABASE_URL="$YOUR_PROD_RO_URL"   # READ-ONLY url required
./scripts/ops/sync_staging_schema.sh
```

Cleanup:

```bash
docker compose -f infra/staging-mirror.compose.yml down -v
```

## How to trigger the workflow manually

1. Repo → Actions → **Staging schema sync** → **Run workflow**.
2. Pick branch `main`.
3. (Optional) set `Dry run only = true` to dump without applying;
   the dump is uploaded as a workflow artifact for inspection.

## What can go wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `pg_dump: error: connection failed` | `PROD_DATABASE_URL_RO` secret expired/rotated | Rotate the secret; re-run. |
| `psql: error: ON_ERROR_STOP at line N` | Staging has objects that conflict with `DROP IF EXISTS` (e.g. external dependent views) | Drop the conflicting object on staging by hand; re-run. |
| Workflow times out | Schema is unusually large or prod is under read load | Increase `timeout-minutes` in the workflow file (default 15). |
| Apply succeeded but app on staging crashes on boot | A migration was applied to prod that the staging app code doesn't yet support | Roll forward staging app build, or revert the prod migration. |

## Rollback

This action is non-destructive of *application data* (only schema
DDL is touched). Staging row data survives untouched. If a sync
applies a schema you didn't want:

1. Revert the offending prod migration (so the next sync drops the
   change).
2. Re-run `Staging schema sync` to bring staging back in line.
3. If you can't wait for the next weekly run, trigger the
   workflow manually.

## Related

* `scripts/ops/sync_staging_schema.sh` — the script itself.
* `.github/workflows/staging-schema-sync.yml` — workflow definition.
* `infra/staging-mirror.compose.yml` — local "staging-like" Postgres.
* P1-15 (PERFECTION_ROADMAP) — the gap this closes.
