# ADR-0006: Generation-job SSE protocol contract

**Status**: accepted
**Date**: 2026-04-29
**Squad**: S4 — Generation API & SSE
**Supersedes**: none

## Context

The frontend tails generation jobs through `/api/generate/jobs/{job_id}/stream`,
a Server-Sent Events endpoint. Lost events here look to a user like a
generation that "got stuck at 99 percent": all the work succeeded server-side,
but the client never received the final batch and the spinner never resolves.

Three classes of bug have lived in this surface in the past:

1. **Envelope drift** — a contributor changed `_sse` to use `\r\n` or to
   put `data:` before `event:`, and the EventSource parser silently
   dropped every event. Bug surfaced as "spinner forever" in the browser.
2. **Terminal-drain miss** — the polling loop noticed status was
   `succeeded` and broke out of the loop without doing one last SELECT
   for events that arrived between the last poll and the status check.
   The `complete` event lived only in the DB; the client never saw it.
3. **Sequence-cursor regression** — a refactor switched `.gt(sequence_no,
   last_sequence)` to `.gte(...)` "for safety," which made every poll
   re-emit the last event and the client looped forever consuming
   duplicates.

S4-F5 pins the contract so any of these regressions fail loudly in CI.

## Decision

### Wire format (every event MUST conform)

```
event: <event_name>\n
data: <single_line_compact_json>\n
\n
```

Constraints:
- Line endings are `\n`, not `\r\n` and not `\r`.
- `event:` line precedes `data:` line.
- The blank line is the terminator; it MUST be present.
- `data:` is exactly one line of compact JSON (no pretty-printing).

Producers: `_sse`, `_agent_sse`, `_detail_sse` in
`backend/app/api/routes/generate/helpers.py`.

### Event taxonomy

| Event name        | Producer       | Payload shape                                                                   |
|-------------------|----------------|---------------------------------------------------------------------------------|
| `progress`        | `_sse`         | Free-form dict; default for any persisted row whose `event_name` is unset.      |
| `agent_status`    | `_agent_sse`   | `{pipeline_name, stage, status, latency_ms, message, timestamp, [quality_scores]}` |
| `detail`          | `_detail_sse`  | `{agent, message, status, timestamp, [source], [url], [metadata]}`              |
| `complete`        | runtime sink   | Final terminal event; payload carries the result envelope.                      |
| (free-form)       | persisted row  | If `generation_job_events.event_name` is anything else, it passes through with `_sse`. |

Optional fields (e.g. `quality_scores`, `source`, `url`, `metadata`) MUST
be omitted from the JSON payload when their value is `None` / empty;
the frontend treats their presence as truthy.

### Stream loop invariants (`/jobs/{job_id}/stream`)

1. **Monotonic cursor.** Both the polling SELECT and the terminal-drain
   SELECT use `.gt("sequence_no", last_sequence)`, never `.gte`. Each
   yielded row advances `last_sequence` via
   `last_sequence = max(last_sequence, int(row.get("sequence_no") or 0))`
   *before* the SSE line is emitted.
2. **Terminal drain.** When the latest job row reports a terminal
   status (`succeeded`, `succeeded_with_warnings`, `failed`, `cancelled`),
   the loop MUST do one final SELECT for any rows past `last_sequence`
   and emit them before breaking out.
3. **Idle keepalive.** After two consecutive idle poll cycles the loop
   yields `: keepalive\n\n` (the SSE comment-line keepalive) so
   intermediaries don't time the connection out at 30s.
4. **Lazy job spin-up.** If the requested job is in `queued` or
   `running` and not in `_ACTIVE_GENERATION_TASKS`, the endpoint kicks
   off the in-process runner before opening the stream so a re-attached
   client doesn't observe a dead job.

### Test contract

Pinned in `backend/tests/unit/test_sse_stream_contract.py` (S4-F5):
- 12 envelope behaviour tests across `_sse` / `_agent_sse` / `_detail_sse`.
- 3 source-shape regression sentinels for the loop:
  - terminal-drain SELECT must exist past the terminal-status check;
  - `.gte("sequence_no", ...)` is forbidden;
  - `last_sequence = max(last_sequence, ...)` advancement must remain.

## Consequences

**Good.** Three different "stuck at 99%" classes of bug now fail in CI
the moment a contributor introduces them, before any user is affected.

**Acceptable.** The terminal-drain regression sentinels are source-shape
checks, not behavioural — they assert the loop *contains* the right
calls rather than running it end-to-end. We accept this because:
- the loop is a closure inside a FastAPI endpoint, hard to drive with
  fakes without auth and rate-limit setup;
- the protocol invariants are stable (sequence-cursor, terminal drain)
  and unlikely to change shape; and
- the envelope helpers `_sse` / `_agent_sse` / `_detail_sse` carry the
  vast majority of behavioural risk and ARE pure-function tested.

**Future.** When S4 takes the structural-decomposition swing, extract
the inner stream loop into a module-level pure async generator that
takes a `StreamSink` protocol. At that point the source-shape sentinels
in F5 graduate into proper behavioural tests.

## References

- `backend/app/api/routes/generate/jobs.py` — `stream_generation_job` (L1588).
- `backend/app/api/routes/generate/helpers.py` — `_sse`, `_agent_sse`, `_detail_sse` (L688-732).
- `backend/tests/unit/test_sse_stream_contract.py` — pinned contract.
- `docs/audits/S4-generation-api-sse.md` — S4 risk inventory + fix queue.
