# Runbook: `events_outbox` partition rotation

Applies to the automated rotation introduced in
`supabase/migrations/20260508120000_outbox_partition_rotation.sql`
(ADR-0037, M7-A / m7-pr27a). Closes P0-1.

## Symptom matrix

| Alert / observation | Likely cause | Section |
|---|---|---|
| `partition_rotation_audit` last `ran_at` > 36h old | `pg_cron` job stopped or failed | §3 |
| Outbox `INSERT` failing: `no partition of relation "events_outbox" found for row` | Function never ran on a fresh database OR clock skew put `now()` past last partition | §4 |
| `events_outbox_YYYY_MM` partition exists but is empty for many days | Domain events not flowing — **separate incident**, not a partition problem | n/a |

## 1. Architecture (5-line summary)

- `events_outbox` is `RANGE`-partitioned monthly on `occurred_at`.
- Function `public.ensure_events_outbox_partitions(p_months_ahead int)`
  creates missing partitions, idempotently, up to `p_months_ahead` ahead.
- `pg_cron` job `events-outbox-rotation` runs daily at 00:01 UTC with
  `p_months_ahead := 4`.
- Each invocation appends a row to `public.partition_rotation_audit`.
- A migration-time bootstrap call ensures 4 months exist immediately on deploy.

## 2. Inspect current state

```sql
-- All current partitions of events_outbox
SELECT
    inhrelid::regclass AS partition,
    pg_get_expr(c.relpartbound, c.oid) AS bounds
FROM pg_inherits i
JOIN pg_class   c ON c.oid = i.inhrelid
WHERE inhparent = 'public.events_outbox'::regclass
ORDER BY partition::text;

-- Cron job status
SELECT jobid, jobname, schedule, command, active
FROM cron.job
WHERE jobname = 'events-outbox-rotation';

-- Recent rotation audit
SELECT * FROM public.partition_rotation_audit
WHERE table_name = 'events_outbox'
ORDER BY ran_at DESC
LIMIT 10;
```

## 3. `pg_cron` job stopped / silent

1. Check whether the job is `active = true`.
2. Look at `cron.job_run_details` (last 50 rows):
   ```sql
   SELECT jobid, runid, status, return_message, start_time, end_time
   FROM cron.job_run_details
   ORDER BY runid DESC LIMIT 50;
   ```
3. Common failure modes:
   - **`permission denied for function ...`** — the migration ran but
     the cron job is owned by a role lacking `EXECUTE` on the function.
     Fix: re-grant `GRANT EXECUTE ON FUNCTION
     public.ensure_events_outbox_partitions(integer) TO postgres;`
     (or to whichever role owns the cron job).
   - **`extension pg_cron does not exist`** — the migration didn't run
     on this database. Apply
     `supabase/migrations/20260508120000_outbox_partition_rotation.sql`.
   - **`duplicate jobname`** — the `DO $$ ... unschedule ... $$` block
     was skipped. Manually:
     ```sql
     SELECT cron.unschedule(jobid)
     FROM cron.job WHERE jobname = 'events-outbox-rotation';
     -- then re-schedule by re-running the migration.
     ```

## 4. Manual rotation (break-glass)

If alerts fire and the cron job cannot be restored quickly:

```sql
-- One-shot. Idempotent. Safe to run repeatedly.
SELECT public.ensure_events_outbox_partitions(6);
-- 6 months ahead buys ~180 days of headroom while you fix the
-- underlying scheduling problem.
```

If the function itself is missing or broken:

```sql
-- Last-resort, manual single-month creation. Replace YYYY_MM and the
-- bounds for the month you need.
CREATE TABLE IF NOT EXISTS public.events_outbox_2026_09
    PARTITION OF public.events_outbox
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
```

After break-glass, file a Sev2 postmortem per
`docs/architecture/OPERATIONAL_PROCESSES.md` §4.

## 5. Retention (out of scope for M7-A)

This rotation only creates *new* partitions. It does not drop old ones.
Retention policy and partition pruning is tracked under M11-pr40 (Stage-A
trailing). Until then, old partitions accumulate; at current event
volume that is sustainable for years.

## 6. Validation after change

```bash
# From any node with psql access:
psql "$DATABASE_URL" -c "SELECT public.ensure_events_outbox_partitions(4);"
# Expected: returns an integer ≥ 0, no error.

# CI integration test:
pytest backend/tests/integration/test_outbox_partitions.py -v
# Skips if INTEGRATION_DB_URL not set; runs in staging CI.
```

## References
- ADR-0037 (`docs/adrs/0037-partition-rotation-strategy.md`)
- Blueprint §17 (P0-1)
- Migration: `supabase/migrations/20260508120000_outbox_partition_rotation.sql`
- Original outbox: `supabase/migrations/20260521010000_events_outbox.sql`
