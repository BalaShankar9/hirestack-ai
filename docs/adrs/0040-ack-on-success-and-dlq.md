# ADR-0040 — ACK-on-success queue semantics + DLQ for generation jobs

- **Status:** Accepted 2026-05-08
- **Owners:** Platform Core / @BalaShankar9
- **Closes:** P0-3 in the production risk register
- **Slice:** `m7-pr27c`
- **Related:** ADR-0038 (in-process fallback gate), `backend/app/core/events/consumer.py` (the same pattern, applied earlier to the events bus)

---

## Context

`backend/app/core/queue.py::_dispatch` is the consumer-side handler for the
`hirestack:generation_jobs` Redis Stream. The current contract is:

```python
async def _run() -> None:
    async with self._sem:
        try:
            await self.handler(job_id, user_id)
        except Exception as exc:
            logger.error("queue.job_handler_error", ...)
        finally:
            # Always ACK — the handler is responsible for marking the
            # DB job as failed on error; we don't want infinite retries
            # of a permanently failing job.
            await asyncio.to_thread(r.xack, STREAM_KEY, GROUP_NAME, msg_id)
```

This is **always-ACK-in-finally**. Three failure modes follow:

1. **Silent loss on transient handler failure.** A handler raising on a
   Supabase 503, a Gemini 429, or an asyncio cancel during pod shutdown
   produces an ACK regardless. The next pod never sees the message. We
   rely entirely on the handler's defensive write to `generation_jobs`
   to surface the failure — a single `await` that itself can fail.
2. **No retry surface.** Redis Streams' `XPENDING` + `XCLAIM` is the
   built-in at-least-once retry primitive. Always-ACK throws it away.
3. **No isolation for poison messages.** A repeatedly-failing job has no
   way to be quarantined; the only signal is log noise.

Meanwhile, the **events bus** — same Redis Streams substrate, same fleet
— uses the correct pattern (`backend/app/core/events/consumer.py`):
delivery-count gate → handler → on success record dedup row + ACK → on
failure leave pending until `max_deliveries`, then DLQ + ACK. It works.
The job queue is the outlier.

P0-3 makes the job queue match.

## Decision

Refactor `_dispatch` to ACK only after a successful handler return,
gated behind feature flag **`ff_queue_ack_on_success`** (default
`false`, sunset **2026-09-01**). When the flag is on the consumer
follows the events-bus pattern verbatim:

1. Read the message's delivery count via `XPENDING` for the specific
   `msg_id`. If `delivery_count > queue_max_deliveries` (default `5`),
   `XADD` the message to the **shared** DLQ stream `events:dlq` with
   tags `{consumer="gen_workers", source_stream, source_msg_id, reason}`,
   then `XACK` and return.
2. Run the handler.
3. **On success:** insert `(consumer, msg_id)` into a new
   `processed_queue_events` table. A unique-violation here means the
   message was already processed in a prior delivery whose ACK round-
   tripped late — treat as success (idempotent). Then `XACK`.
4. **On failure:** log, **do not ACK**, **do not insert**. The message
   stays in the consumer group's pending entries list (PEL); the
   `_reclaim_pending` path on this or any sibling pod will pick it up
   after `CLAIM_IDLE_MS` (5 minutes) and retry. After
   `queue_max_deliveries` total deliveries, step 1 routes it to DLQ.

When the flag is off the legacy always-ACK behaviour is preserved
verbatim — this is a pure expand-only change at runtime.

The dedup table:

```sql
CREATE TABLE IF NOT EXISTS public.processed_queue_events (
    consumer    text        NOT NULL,
    msg_id      text        NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, msg_id)
);
```

`msg_id` is `text` (Redis stream IDs are `<ms>-<seq>`, not UUIDs);
this is intentionally a separate table from `consumed_events` (which
keys on `event_id uuid` from the events-bus payload). Mixing the two
schemas would force a UUID coercion of every msg_id and lose the
direct one-to-one mapping back to the Redis PEL entry during incident
forensics.

The DLQ stream is `events:dlq` — the same stream the events bus already
writes to. Replaying from there is a single `XRANGE` + handler-replay
script (out of scope for this slice; tracked in M11). All DLQ entries
carry a `consumer` field so `gen_workers` entries can be filtered.

## Considered alternatives

**(A) Inline `try/except` around the existing `xack` and conditionally
skip ACK on handler exception.** Rejected — solves the silent-loss
problem but adds no DLQ, no idempotency, no delivery-count gate. A
poison message blocks the consumer group forever. The events-bus
already had to solve all four; building a second incompatible solution
is debt.

**(B) Per-message Postgres advisory lock keyed on `job_id` instead of a
dedup table.** Rejected — `job_id` is application-level state; using it
for transport-level dedup couples the queue protocol to job semantics.
The dedup table key (`consumer`, `msg_id`) is purely transport.
Advisory locks also disappear on session end, so a crashed handler that
released the lock before crashing would expose the same race we're
trying to close.

**(C) Move to Temporal entirely and skip queue work.** Rejected — Temporal
is being introduced via the strangler (`ff_temporal_generation`) but is
not yet the path-of-record. The Redis queue is the *current* hot path
and an outage of it during the strangler period would directly hit
production users. Reliability work on the live path must precede
rip-and-replace.

**(D) Always-flip — no flag.** Rejected — semantics change for every
existing in-flight message at the moment of deploy. A handler that
raised but where the in-flight job was nonetheless completed by the
defensive write would now retry, possibly producing a duplicate. The
flag lets us flip per-environment after smoke-checking the
`processed_queue_events` insert path.

## Consequences

**Positive**
- Handler exceptions stop being silent: the message is retried, then
  DLQ'd. The DB row's failure state is no longer the only source of
  truth.
- A poison message stalls **only its own message slot** (until DLQ),
  not the whole consumer group — `_reclaim_pending` only re-claims
  *that* msg_id when idle; other reads continue.
- The job queue matches the events bus. One reliability story, one
  runbook, one DLQ stream to monitor.
- Idempotency at the transport layer means an at-least-once retry
  caused by a network hiccup between handler-success and ACK doesn't
  re-execute generation.

**Negative**
- A pathologically slow handler (>5 min of true work) could be
  reclaimed by a sibling pod and run twice before completing once.
  The dedup table makes the second run a no-op (it sees the prior
  delivery's row), but only if the first run also completed
  successfully and inserted. If the first run is still mid-execution
  the dedup row doesn't exist yet → duplicate execution. This is a
  known property of at-least-once semantics; the handler
  (`_run_generation_job_via_runtime`) already guards against
  duplicate state writes via `generation_jobs.status` transitions
  (Pending → Running → Completed/Failed) so the worst case is wasted
  compute, not duplicated user-visible side-effects. Stage-B option:
  raise `CLAIM_IDLE_MS` to 30 min for jobs whose 99p runtime is known.
- Adds a Supabase write per successful job. Cost: one row, one PK
  insert. Negligible at 50K jobs/day; revisit at 5M/day.
- DLQ depth becomes a new monitoring surface. Acceptable — the events
  bus already exposes the same metric pattern.

**Neutral**
- Schema change is additive (new table, no FK, RLS service-role-only).
- No change to producer (`enqueue_generation_job`).
- No change to flag-off path — bit-for-bit identical to today.

## Out of scope (explicit, deferred)

- **DLQ replay tool / runbook.** Tracked in M11 (observability uplift).
  Today the DLQ is write-only; ops can `XRANGE events:dlq` to inspect.
- **Prometheus counters** `queue_ack_total{outcome,consumer}`,
  `queue_dlq_total{consumer}`, `queue_pending_redeliveries{consumer}`.
  Tracked in M11.
- **Pruning policy for `processed_queue_events`.** The events bus's
  `consumed_events` is also unbounded (as documented in its migration).
  Both will get the same retention sweeper in a single follow-up
  (planned M7-D / Stage-A trailing) — at ~50K rows/day this is months
  of runway.
- **Per-event-type DLQ routing.** ADR-text mentioned `events:dlq:<type>`;
  the actual implementation reuses the single `events:dlq` stream with a
  `consumer` discriminator field, matching the events-bus convention.
  Per-stream DLQs revisit only if a single consumer's DLQ traffic
  drowns the shared stream's signal.
- **Temporal-side equivalent.** When `ff_temporal_generation` becomes
  the dominant path, Temporal's own retry policies + workflow history
  replace this layer. This ADR's flag and table can then be retired in
  the same wave that removes the legacy dispatcher.

## Stage-B revisit triggers

Reopen the design when **any** of these are true:

1. DLQ depth for `gen_workers` exceeds `0` for >24h on three separate
   weeks within a quarter (signals a chronic poison-message class that
   needs handler-side fix or per-class retry policy).
2. `processed_queue_events` row count exceeds 50M (forces the pruning
   conversation).
3. P99 handler runtime exceeds `CLAIM_IDLE_MS / 2` (= 2.5 min) (forces
   the claim-idle conversation).
4. Temporal becomes the only path and `ff_temporal_generation` is at
   100% with no rollback plan (allows retiring this entire layer).

## Rollout plan

1. **PR merge** — code lands with `ff_queue_ack_on_success=false`. Zero
   runtime change.
2. **Migration** — `database/migrations/20260508_processed_queue_events.sql`
   ships in the same PR. Idempotent `CREATE TABLE IF NOT EXISTS`.
3. **Dev flip** — set `FF_QUEUE_ACK_ON_SUCCESS=true` in the dev env, run
   a synthetic poison-message drill (handler raises 5 times → DLQ
   appears).
4. **Staging flip** — same.
5. **Prod flip** — set in prod env, monitor `events:dlq` `XLEN` and
   `processed_queue_events` row count for 7 days.
6. **Sunset deadline** — 2026-09-01: `check_feature_flags.py` enforces
   removal of the flag entirely (legacy code path deleted, gated
   behaviour becomes the only behaviour).
