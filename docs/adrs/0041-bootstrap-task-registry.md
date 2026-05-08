# ADR-0041 — Managed task registry for generation-job bootstrap coroutines

| | |
|---|---|
| **Status** | Accepted 2026-05-08 |
| **Owners** | Platform Core / @BalaShankar9 |
| **Closes** | P0-4 (orphan task hygiene) |
| **Slice** | m7-pr27d |
| **Supersedes** | — |
| **Superseded by** | — |
| **Related** | ADR-0037 (partition rotation), ADR-0038 (in-process fallback gate), ADR-0040 (ACK-on-success queue) |

## Context

`backend/app/api/routes/generate/jobs.py::_start_generation_job` and
`_start_generation_job_legacy` use raw `asyncio.create_task(...)` for
three short-lived bootstrap coroutines that hand a job off from the
synchronous request path to the async dispatch substrate:

1. `_try_temporal()` — strangler dispatch to Temporal when the
   `ff_temporal_generation` flag is on.
2. `_try_enqueue()` — the Tier-2 Redis Streams enqueue path.
3. `_handle_redis_unavailable()` — the ADR-0038 fallback decisioning
   coroutine, also fired on enqueue-setup exception.

A fourth `asyncio.create_task` inside `_start_generation_job_inprocess`
(the saturation finaliser) is also a fire-and-forget bootstrap.

Python's [asyncio docs](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task)
explicitly warn that the runtime holds **only a weak reference** to
tasks created by `create_task` when the caller does not retain the
return value — meaning the garbage collector may eat the task mid-flight.
In practice we have not observed this on CPython, but the larger problem
is **shutdown semantics**:

- The lifespan handler drains `_ACTIVE_GENERATION_TASKS` (the long-lived
  pipeline coroutines) but knows nothing about the four bootstrap tasks.
- On SIGTERM, an in-flight `_try_enqueue()` racing against Redis
  unavailability can be cancelled mid-flight, leaving the job in a
  zombie `queued` state with no enqueue and no failure record.
- Exceptions in these tasks vanish silently — `asyncio` only logs them
  if the task is awaited or has a done-callback, neither of which is
  the case today.

This is P0 because it is a *durability* hole (the user's primary
production concern after silent event loss, which ADR-0040 addressed):
a job submitted just before deploy can disappear without trace.

## Decision

Introduce a single module-level managed task registry in
`backend/app/api/routes/generate/jobs.py`:

```python
_BOOTSTRAP_TASKS: set[asyncio.Task] = set()


def _track_bootstrap(coro, *, name: str) -> asyncio.Task:
    """Create + register a fire-and-forget bootstrap task.

    Holds a strong reference (prevents GC), logs unhandled exceptions
    in a done-callback, and removes the task from the registry on
    completion. Used for short-lived dispatch handoff coroutines that
    we cannot block on but whose loss would orphan a generation job.
    """
    task = asyncio.create_task(coro, name=name)
    _BOOTSTRAP_TASKS.add(task)

    def _done(t: asyncio.Task) -> None:
        _BOOTSTRAP_TASKS.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.warning(
                "generation_bootstrap_task_failed",
                task=name,
                error=str(exc)[:300],
            )

    task.add_done_callback(_done)
    return task
```

Replace every raw `asyncio.create_task(...)` inside the
`_start_generation_job*` family with `_track_bootstrap(..., name=...)`.

Extend the FastAPI lifespan handler in `backend/main.py` so that, after
draining `_ACTIVE_GENERATION_TASKS`, it also drains `_BOOTSTRAP_TASKS`
with a short bounded wait (`asyncio.wait_for(asyncio.gather(...), timeout=5)`)
so SIGTERM never abandons an in-flight enqueue.

## Considered alternatives

- **(A) Do nothing — rely on `asyncio` cleanup.** Rejected: the weak-
  reference GC risk is a well-known footgun, and the silent shutdown
  truncation is observable today.
- **(B) Convert bootstrap coroutines to `asyncio.shield`.** Rejected:
  `shield` only protects against external cancellation; it does not
  surface exceptions and does not give us a registry to drain.
- **(C) Switch the entire dispatch path to background-task workers
  (FastAPI `BackgroundTasks`).** Rejected: would require touching every
  call site of `_start_generation_job` and `BackgroundTasks` are bound
  to the request lifecycle (cancelled when the response body is written),
  which is the wrong semantic for a fire-and-forget dispatcher.
- **(D) Use the `_ACTIVE_GENERATION_TASKS` dict for everything.** Rejected:
  that dict is keyed by `job_id` and is tied to long-lived pipeline
  execution. Bootstrap tasks are short-lived and may race for the same
  `job_id` (e.g. duplicate request); collapsing them would require a
  composite key and would entangle two distinct lifecycles.

## Consequences

**Positive:**
- No tasks GC'd mid-flight (strong reference).
- Bootstrap exceptions surface as a single structured WARN log line
  instead of silent stderr.
- SIGTERM drains both registries → jobs are never orphaned at deploy.

**Negative:**
- A pathologically slow bootstrap coroutine (>5s — the lifespan budget)
  is still cancelled, but now it is logged. Acceptable.
- One additional set + one additional callback per dispatch. Cost is
  microseconds; not measurable in any pipeline budget.

**Operational notes:**
- The drain budget (5s) is the same order as the existing
  `await asyncio.sleep(2)` grace + the 2s expected enqueue path.
- No new feature flag — this is a pure-improvement change with no
  observable behavioural difference outside SIGTERM windows.

## Out of scope (deferred — written down so they don't get lost)

- A generic `app.core.task_registry` module that other parts of the
  backend (e.g. `_periodic_stale_job_cleanup`, `JobWatchdog`) could
  adopt — M11.
- Prometheus gauges `bootstrap_tasks_inflight`, `bootstrap_task_failures_total`
  — M11.
- `_try_temporal()` failure mode where it falls back to legacy mid-flight
  on cancellation — currently the legacy fallback only fires inside the
  outer try/except; cancellation paths drop the job. Tolerable until
  Temporal is at 100% rollout.

## Stage-B revisit triggers

- More than one production incident per quarter where a job is observed
  in `queued` state with no corresponding Redis stream entry → consider
  promoting the registry into a generic primitive and adding metrics.
- `_BOOTSTRAP_TASKS` size observed > 100 sustained → indicates dispatch
  is not draining fast enough; investigate Redis health.

## Verification

- Unit tests in `backend/tests/unit/test_bootstrap_task_registry.py` cover
  registration, completion, exception logging, and concurrent registration.
- Manual SIGTERM drill: submit 50 jobs in a tight loop, send SIGTERM
  during dispatch → all jobs end up either enqueued or failed (none in
  `queued` with no stream entry).
