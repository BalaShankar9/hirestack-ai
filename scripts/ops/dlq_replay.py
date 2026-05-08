"""DLQ replay tool for the shared ``events:dlq`` Redis stream (PR m11-pr37).

The application has two writers that XADD into ``events:dlq``:

* ``app.core.queue`` (generation jobs queue, group ``hirestack-workers``)
  emits fields: ``consumer``, ``source_stream``, ``source_msg_id``,
  ``job_id``, ``user_id``, ``reason``.
* ``app.core.events.consumer.StreamConsumer`` (generic stream consumer)
  emits fields: ``consumer``, ``source_stream``, ``source_msg_id``,
  ``reason``, ``event`` (JSON-encoded original event payload).

This tool gives operators a safe way to inspect, filter, replay, and
purge those entries. **Dry-run is the default** for every mutating
action — pass ``--apply`` to actually XADD/XDEL.

Replay strategy:

* Generic-consumer entries (have ``event`` field) are re-XADDed to
  ``source_stream`` with the decoded event JSON as the payload. The
  generic consumer's dedup table (``consumed_events``) keyed by
  ``event_id`` prevents the handler from running twice if the
  original delivery actually succeeded but failed mid-ACK.
* Queue entries (no ``event`` field) are re-XADDed to ``source_stream``
  with ``{job_id, user_id}`` as the payload. The queue's
  ``processed_queue_events`` dedup keyed by ``msg_id`` does NOT cover
  this case (new ``msg_id`` after re-XADD), so the runbook documents
  the operator pre-flight: confirm the job is genuinely dead before
  replay (DB row in ``failed`` state, no recent progress).

After successful XADD, the original DLQ entry is XDELed by default
unless ``--keep`` is passed.

Usage:

    python scripts/ops/dlq_replay.py list                       # show last 20
    python scripts/ops/dlq_replay.py list --consumer hirestack-workers --limit 50
    python scripts/ops/dlq_replay.py inspect <dlq_msg_id>
    python scripts/ops/dlq_replay.py replay <dlq_msg_id>        # dry-run
    python scripts/ops/dlq_replay.py replay <dlq_msg_id> --apply
    python scripts/ops/dlq_replay.py replay-all --consumer foo --since 1h --apply
    python scripts/ops/dlq_replay.py purge <dlq_msg_id> --apply

Exit codes: 0 success / 1 not-found / 2 redis unavailable / 3 user error.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from typing import Any, Iterable

DLQ_STREAM = "events:dlq"

logger = logging.getLogger("dlq_replay")


# ─────────────────────────── Redis bootstrap ───────────────────────────


def _connect_redis() -> Any:
    """Connect to Redis using the same settings the app uses.

    Returns a synchronous ``redis.Redis`` client (not the asyncio one) —
    the tool runs as a one-shot script, so blocking I/O is fine and
    keeps the code straightforward.
    """
    try:
        from app.core.config import settings  # type: ignore
    except Exception as exc:  # pragma: no cover - import-time failure
        sys.stderr.write(f"FATAL: cannot import app.core.config: {exc}\n")
        sys.exit(2)

    url = getattr(settings, "redis_url", None)
    if not url:
        sys.stderr.write("FATAL: REDIS_URL not configured\n")
        sys.exit(2)

    try:
        import redis  # type: ignore
    except ImportError:
        sys.stderr.write("FATAL: redis-py not installed\n")
        sys.exit(2)

    client = redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        client.ping()
    except Exception as exc:
        sys.stderr.write(f"FATAL: Redis unreachable: {exc}\n")
        sys.exit(2)
    return client


# ─────────────────────────── parsing helpers ───────────────────────────


_DURATION_RE = re.compile(r"^(\d+)([smhd])$")


def _parse_since(since: str | None) -> str:
    """Parse ``--since`` value into an XRANGE start id (``ms-0`` or ``-``).

    Accepts: ``-`` (=earliest), bare ms epoch, or shorthand like ``15m``,
    ``2h``, ``1d``.
    """
    if not since or since == "-":
        return "-"
    if since.isdigit():
        return f"{since}-0"
    match = _DURATION_RE.match(since)
    if not match:
        sys.stderr.write(
            f"ERROR: --since must be '-', a ms epoch, or duration like 15m/2h/1d (got {since!r})\n"
        )
        sys.exit(3)
    n, unit = int(match.group(1)), match.group(2)
    secs = n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    cutoff_ms = int((time.time() - secs) * 1000)
    return f"{cutoff_ms}-0"


def _matches_filters(
    fields: dict[str, str], *, consumer: str | None, reason_substr: str | None
) -> bool:
    if consumer and fields.get("consumer") != consumer:
        return False
    if reason_substr and reason_substr.lower() not in (fields.get("reason") or "").lower():
        return False
    return True


def _xrange(
    client: Any,
    *,
    start: str = "-",
    end: str = "+",
    count: int | None = None,
) -> list[tuple[str, dict[str, str]]]:
    return client.xrange(DLQ_STREAM, min=start, max=end, count=count)


# ─────────────────────────── commands ───────────────────────────


def cmd_list(client: Any, args: argparse.Namespace) -> int:
    start = _parse_since(args.since)
    entries = _xrange(client, start=start, count=args.limit)
    matched = [
        (mid, f)
        for mid, f in entries
        if _matches_filters(f, consumer=args.consumer, reason_substr=args.reason)
    ]
    if not matched:
        print("(no DLQ entries match)")
        return 0
    print(f"{len(matched)} DLQ entries (newest last):")
    print(f"{'msg_id':<22} {'consumer':<24} {'source_stream':<24} reason")
    print("-" * 100)
    for mid, f in matched:
        reason = (f.get("reason") or "")[:50]
        print(
            f"{mid:<22} "
            f"{(f.get('consumer') or '?')[:24]:<24} "
            f"{(f.get('source_stream') or '?')[:24]:<24} "
            f"{reason}"
        )
    return 0


def cmd_inspect(client: Any, args: argparse.Namespace) -> int:
    entries = _xrange(client, start=args.msg_id, end=args.msg_id, count=1)
    if not entries:
        print(f"NOT FOUND: {args.msg_id}", file=sys.stderr)
        return 1
    mid, fields = entries[0]
    out = {"dlq_msg_id": mid, **fields}
    if "event" in out:
        try:
            out["event"] = json.loads(out["event"])
        except Exception:
            pass  # leave as raw string
    print(json.dumps(out, indent=2, default=str))
    return 0


def _build_replay_payload(fields: dict[str, str]) -> dict[str, str]:
    """Reconstruct the message body that goes back onto the source stream.

    Two shapes:

    * Generic-consumer entry: the ``event`` field holds the JSON-encoded
      original event. We decode it and re-encode each top-level key as a
      Redis-stream field (matching how the consumer reads it).
    * Queue entry: just ``job_id`` + ``user_id``.
    """
    if "event" in fields:
        try:
            event = json.loads(fields["event"])
        except Exception as exc:
            raise ValueError(f"could not decode 'event' JSON: {exc}") from exc
        # Redis-stream fields must be strings — match the producer's shape
        # by stringifying each top-level value.
        return {k: v if isinstance(v, str) else json.dumps(v, default=str) for k, v in event.items()}
    if "job_id" in fields and "user_id" in fields:
        return {"job_id": fields["job_id"], "user_id": fields["user_id"]}
    raise ValueError("DLQ entry has neither 'event' nor 'job_id'/'user_id' — cannot rebuild payload")


def _replay_one(
    client: Any, mid: str, fields: dict[str, str], *, apply: bool, keep: bool
) -> bool:
    source = fields.get("source_stream")
    if not source:
        print(f"  SKIP {mid}: missing source_stream", file=sys.stderr)
        return False
    try:
        payload = _build_replay_payload(fields)
    except ValueError as exc:
        print(f"  SKIP {mid}: {exc}", file=sys.stderr)
        return False
    prefix = "WOULD" if not apply else "DID"
    print(f"  {prefix} XADD {source} ({len(payload)} fields) [from DLQ {mid}]")
    if apply:
        new_id = client.xadd(source, payload)
        print(f"    -> new id {new_id}")
        if not keep:
            deleted = client.xdel(DLQ_STREAM, mid)
            print(f"    -> XDEL {DLQ_STREAM} {mid} (rows={deleted})")
    return True


def cmd_replay(client: Any, args: argparse.Namespace) -> int:
    entries = _xrange(client, start=args.msg_id, end=args.msg_id, count=1)
    if not entries:
        print(f"NOT FOUND: {args.msg_id}", file=sys.stderr)
        return 1
    if not args.apply:
        print("DRY RUN (pass --apply to mutate):")
    ok = _replay_one(client, entries[0][0], entries[0][1], apply=args.apply, keep=args.keep)
    return 0 if ok else 1


def cmd_replay_all(client: Any, args: argparse.Namespace) -> int:
    start = _parse_since(args.since)
    entries = _xrange(client, start=start, count=args.limit)
    matched = [
        (mid, f)
        for mid, f in entries
        if _matches_filters(f, consumer=args.consumer, reason_substr=args.reason)
    ]
    if not matched:
        print("(no DLQ entries match)")
        return 0
    if not args.apply:
        print(f"DRY RUN: would replay {len(matched)} entries (pass --apply to mutate):")
    else:
        print(f"REPLAYING {len(matched)} entries:")
    failures = 0
    for mid, fields in matched:
        if not _replay_one(client, mid, fields, apply=args.apply, keep=args.keep):
            failures += 1
    print(f"done: {len(matched) - failures} ok, {failures} skipped")
    return 0 if failures == 0 else 1


def cmd_purge(client: Any, args: argparse.Namespace) -> int:
    entries = _xrange(client, start=args.msg_id, end=args.msg_id, count=1)
    if not entries:
        print(f"NOT FOUND: {args.msg_id}", file=sys.stderr)
        return 1
    if not args.apply:
        print(f"DRY RUN: would XDEL {DLQ_STREAM} {args.msg_id} (pass --apply to delete)")
        return 0
    deleted = client.xdel(DLQ_STREAM, args.msg_id)
    print(f"XDEL {DLQ_STREAM} {args.msg_id} (rows={deleted})")
    return 0 if deleted else 1


# ─────────────────────────── CLI ───────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dlq_replay",
        description="Inspect / replay / purge events:dlq entries (m11-pr37).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    common_filters = argparse.ArgumentParser(add_help=False)
    common_filters.add_argument("--consumer", help="filter by consumer field")
    common_filters.add_argument(
        "--reason", help="filter by case-insensitive substring of reason field"
    )
    common_filters.add_argument(
        "--since",
        default="-",
        help="oldest entry to consider; '-' = all, ms epoch, or duration like 15m/2h/1d",
    )
    common_filters.add_argument("--limit", type=int, default=20)

    sp_list = sub.add_parser("list", parents=[common_filters], help="list DLQ entries")
    sp_list.set_defaults(func=cmd_list)

    sp_inspect = sub.add_parser("inspect", help="dump one DLQ entry as JSON")
    sp_inspect.add_argument("msg_id")
    sp_inspect.set_defaults(func=cmd_inspect)

    sp_replay = sub.add_parser("replay", help="replay one DLQ entry to its source stream")
    sp_replay.add_argument("msg_id")
    sp_replay.add_argument("--apply", action="store_true", help="actually mutate (default: dry-run)")
    sp_replay.add_argument("--keep", action="store_true", help="do not XDEL the DLQ entry after XADD")
    sp_replay.set_defaults(func=cmd_replay)

    sp_replay_all = sub.add_parser(
        "replay-all", parents=[common_filters], help="replay all matching DLQ entries"
    )
    sp_replay_all.add_argument("--apply", action="store_true")
    sp_replay_all.add_argument("--keep", action="store_true")
    sp_replay_all.set_defaults(func=cmd_replay_all)

    sp_purge = sub.add_parser("purge", help="XDEL a DLQ entry without replay")
    sp_purge.add_argument("msg_id")
    sp_purge.add_argument("--apply", action="store_true")
    sp_purge.set_defaults(func=cmd_purge)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    client = _connect_redis()
    return int(args.func(client, args))


if __name__ == "__main__":
    raise SystemExit(main())
