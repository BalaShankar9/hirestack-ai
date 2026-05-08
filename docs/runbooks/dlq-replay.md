# Runbook: DLQ replay

Applies to the shared ``events:dlq`` Redis stream populated by:

* `app.core.queue` — generation jobs queue (group `hirestack-workers`).
* `app.core.events.consumer.StreamConsumer` — generic stream consumer
  used by outbox-relay etc.

## Symptom

Alert fires for `queue.dead_lettering` log lines (>5 / 5 min) or the
`queue_dlq_total{consumer}` Prometheus counter (m11-pr38) jumps. Users
report: jobs stuck in `failed` state without retry; events never
reaching downstream consumers (e.g. analytics counters lagging).

## 1. Confirm scope

```bash
# From a pod with REDIS_URL configured (or against a tunneled prod redis):
python scripts/ops/dlq_replay.py list --limit 50
# Filter by consumer / time window:
python scripts/ops/dlq_replay.py list --consumer hirestack-workers --since 1h
python scripts/ops/dlq_replay.py list --reason "max_deliveries_exceeded"
```

What you should see: a table of DLQ msg-ids with `consumer`,
`source_stream`, and a truncated `reason` per entry.

If `(no DLQ entries match)` — the queue is healthy; the alert was
transient (TTL-based) or already drained by a previous replay.

## 2. Identify root cause **before** replaying

Replaying an entry without fixing the underlying defect just re-fills
the DLQ. Inspect a representative entry:

```bash
python scripts/ops/dlq_replay.py inspect <dlq_msg_id>
```

The output is a JSON dump including the decoded `event` payload (for
generic-consumer entries) or `job_id`/`user_id` (for queue entries).
Cross-reference:

* **Reason `handler raised: <ExceptionClass>`** → check Sentry for
  the matching event class. Common causes: upstream API down (Stripe,
  Supabase), credential rotation, schema drift, OOM.
* **Reason `max_deliveries_exceeded`** → handler attempted ≥
  `queue_max_deliveries` (default 5) without success. Inspect the job
  row: `select status, last_error, attempts from generation_jobs where
  id = '<job_id>'`. If `last_error` is a 4xx (validation), do NOT
  replay — fix the input or mark the job dead. If 5xx (transient),
  proceed to step 3.

## 3. Pre-flight before replay

Generic-consumer entries are dedup-safe: the consumer's
`consumed_events` table keyed by `event_id` will short-circuit the
handler if a previous delivery actually succeeded but failed mid-ACK.
**Replay is idempotent.**

Queue entries (no `event` field) are NOT covered by the
`processed_queue_events` dedup after a re-XADD because the new msg-id
differs. Operator must verify the job is genuinely dead:

```sql
-- Replace <job_id> from `inspect` output.
select id, status, attempts, last_error, updated_at
from generation_jobs
where id = '<job_id>';
```

* `status = 'failed'` and `updated_at` older than 10 minutes → safe
  to replay.
* `status` in (`processing`, `queued`) → **DO NOT replay**, the worker
  is still trying. Wait or kill the worker first.
* `status = 'completed'` → DO NOT replay. XDEL the DLQ entry instead
  (`purge` command).

## 4. Replay

Always start with a **dry run** (the default — you do nothing):

```bash
python scripts/ops/dlq_replay.py replay <dlq_msg_id>
```

Output should look like:

```
DRY RUN (pass --apply to mutate):
  WOULD XADD events:aim.source.created (4 fields) [from DLQ 1700000000000-1]
```

When you're ready:

```bash
python scripts/ops/dlq_replay.py replay <dlq_msg_id> --apply
```

This XADDs a new entry to the original `source_stream`, prints the new
msg-id, then XDELs the DLQ entry. Pass `--keep` to leave the DLQ entry
in place (useful if you're debugging and want to compare).

### Bulk replay

After fixing the root cause (deploy + smoke tested), drain the DLQ:

```bash
# Dry-run the full set first so you can scan it.
python scripts/ops/dlq_replay.py replay-all --consumer hirestack-workers --since 1h
# Then actually replay:
python scripts/ops/dlq_replay.py replay-all --consumer hirestack-workers --since 1h --apply
```

`replay-all` honours `--consumer`, `--reason`, `--since`, and
`--limit`. It defaults to dry-run.

## 5. Purge (last resort)

If an entry is permanently un-replayable (e.g. corrupt event JSON,
job already completed via a different code path), purge it:

```bash
python scripts/ops/dlq_replay.py purge <dlq_msg_id> --apply
```

Document each purge in the postmortem — purging hides a real failure
from the metrics.

## 6. Post-incident

* Record the count of replayed vs. purged entries.
* If you replayed > 50 entries in a single window, file a follow-up
  to add automatic replay-with-backoff to the consumer instead of a
  manual workflow.
* Verify `queue_dlq_total{consumer}` (m11-pr38) flatlines after the
  drain.
* If the same `reason` shows up across milestones, escalate to a
  bounded-context owner — the handler needs a structural fix, not
  more retries.

## Reference

* Implementation: [`scripts/ops/dlq_replay.py`](../../scripts/ops/dlq_replay.py)
* Tests (pinning replay/purge semantics):
  [`backend/tests/ops/test_dlq_replay.py`](../../backend/tests/ops/test_dlq_replay.py)
* Producers: [`backend/app/core/queue.py`](../../backend/app/core/queue.py)
  and
  [`backend/app/core/events/consumer.py`](../../backend/app/core/events/consumer.py).
* Milestone: M11 / `m11-pr37` in
  [docs/architecture/IMPLEMENTATION_MILESTONES.md](../architecture/IMPLEMENTATION_MILESTONES.md).
