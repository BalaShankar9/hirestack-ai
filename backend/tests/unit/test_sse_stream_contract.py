"""S4-F5 — Pin SSE envelope helpers + stream terminal-drain pattern.

The streaming endpoint at /jobs/{job_id}/stream tails persisted SSE
events. Two contracts protect the user from a frustrating "stuck at
99%" experience:

1. **Envelope shape** — `_sse`, `_agent_sse`, `_detail_sse` produce
   the exact wire format the frontend EventSource client parses.
   A drift in the line endings, the `event:` / `data:` prefix order,
   or the JSON serialisation breaks every running browser tab.

2. **Terminal drain** — when the endpoint observes the job has
   reached a terminal status (succeeded / failed / cancelled), it
   MUST do one final SELECT for events beyond `last_sequence` before
   breaking the loop. Otherwise the very last batch of events
   (including the `complete` event) is silently dropped and the
   frontend hangs waiting for them.

Test (1) directly via behavioural assertions on the helpers.
Test (2) as a code-shape regression sentinel: the streaming
endpoint MUST contain the terminal-drain pattern. A future
contributor "simplifying" the loop and dropping the second SELECT
will trip this test.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.api.routes.generate.helpers import (
    _agent_sse,
    _detail_sse,
    _sse,
)


# ── _sse envelope ─────────────────────────────────────────────────────


def test_sse_uses_event_then_data_then_blank_line() -> None:
    """Wire format the EventSource spec demands: lines must be
    `event: <name>\\n`, `data: <json>\\n`, terminated by a blank
    line. Reordering or dropping the blank line breaks the parser."""
    out = _sse("progress", {"step": 1})
    assert out == "event: progress\ndata: {\"step\": 1}\n\n"


def test_sse_data_is_compact_json() -> None:
    out = _sse("progress", {"a": 1, "b": "x"})
    # Extract the data line and round-trip
    match = re.search(r"^data: (.+)$", out, re.MULTILINE)
    assert match is not None
    parsed = json.loads(match.group(1))
    assert parsed == {"a": 1, "b": "x"}


def test_sse_handles_nested_payloads() -> None:
    out = _sse("complete", {"result": {"score": 0.9, "ok": True}})
    match = re.search(r"^data: (.+)$", out, re.MULTILINE)
    assert match is not None
    assert json.loads(match.group(1)) == {"result": {"score": 0.9, "ok": True}}


def test_sse_terminates_with_double_newline() -> None:
    """The blank line is what tells the EventSource the message is
    complete. Missing terminator means the browser holds the event
    in buffer until the next message arrives."""
    out = _sse("x", {})
    assert out.endswith("\n\n")


# ── _agent_sse envelope ───────────────────────────────────────────────


def test_agent_sse_event_name_is_agent_status() -> None:
    out = _agent_sse("recon", "running", "in_progress")
    assert out.startswith("event: agent_status\n")


def test_agent_sse_carries_required_fields() -> None:
    out = _agent_sse("recon", "scanning", "in_progress", latency_ms=42, message="hi")
    match = re.search(r"^data: (.+)$", out, re.MULTILINE)
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["pipeline_name"] == "recon"
    assert payload["stage"] == "scanning"
    assert payload["status"] == "in_progress"
    assert payload["latency_ms"] == 42
    assert payload["message"] == "hi"
    assert "timestamp" in payload


def test_agent_sse_omits_quality_scores_when_none() -> None:
    out = _agent_sse("recon", "scan", "ok")
    payload = json.loads(re.search(r"^data: (.+)$", out, re.MULTILINE).group(1))
    assert "quality_scores" not in payload


def test_agent_sse_includes_quality_scores_when_provided() -> None:
    out = _agent_sse("recon", "scan", "ok", quality_scores={"clarity": 0.9})
    payload = json.loads(re.search(r"^data: (.+)$", out, re.MULTILINE).group(1))
    assert payload["quality_scores"] == {"clarity": 0.9}


# ── _detail_sse envelope ──────────────────────────────────────────────


def test_detail_sse_event_name_is_detail() -> None:
    out = _detail_sse("nova", "step done")
    assert out.startswith("event: detail\n")


def test_detail_sse_default_status_is_info() -> None:
    out = _detail_sse("nova", "hi")
    payload = json.loads(re.search(r"^data: (.+)$", out, re.MULTILINE).group(1))
    assert payload["status"] == "info"


def test_detail_sse_omits_optional_fields_when_none() -> None:
    out = _detail_sse("nova", "hi")
    payload = json.loads(re.search(r"^data: (.+)$", out, re.MULTILINE).group(1))
    for optional in ("source", "url", "metadata"):
        assert optional not in payload


def test_detail_sse_includes_optional_fields_when_provided() -> None:
    out = _detail_sse(
        "nova",
        "scanned",
        status="ok",
        source="linkedin",
        url="https://x.test/y",
        metadata={"hits": 3},
    )
    payload = json.loads(re.search(r"^data: (.+)$", out, re.MULTILINE).group(1))
    assert payload["source"] == "linkedin"
    assert payload["url"] == "https://x.test/y"
    assert payload["metadata"] == {"hits": 3}


# ── Stream terminal-drain pattern (regression sentinel) ───────────────

_JOBS_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "routes"
    / "generate"
    / "jobs.py"
)


def test_stream_endpoint_drains_events_after_terminal_status() -> None:
    """The /jobs/{job_id}/stream loop must do ONE final SELECT for
    events beyond last_sequence after observing a terminal status,
    before breaking the loop. Without this, the last batch of events
    (including the `complete` event) is dropped and the frontend
    hangs at 99%.

    Sentinel: after the terminal-status check the source must call
    final_events = ... .gt('sequence_no', last_sequence) ...
    """
    src = _JOBS_PATH.read_text()
    # Find the streaming function body
    match = re.search(
        r"async def stream_generation_job\(.*?\n    return StreamingResponse",
        src,
        re.DOTALL,
    )
    assert match is not None, "stream_generation_job endpoint not found"
    body = match.group(0)

    # Must check for terminal status set
    assert re.search(
        r"\{[^}]*\"succeeded\"[^}]*\"failed\"[^}]*\"cancelled\"[^}]*\}",
        body,
    ), "terminal status set must include succeeded / failed / cancelled"

    # Must do a final drain SELECT keyed off last_sequence
    final_drain = re.search(
        r"final_events\s*=.*?\.gt\(\"sequence_no\",\s*last_sequence\)",
        body,
        re.DOTALL,
    )
    assert final_drain is not None, (
        "stream endpoint dropped the terminal drain SELECT — "
        "frontend will hang on the last batch of events"
    )


def test_stream_endpoint_uses_monotonic_sequence_cursor() -> None:
    """Both the polling SELECT and the terminal-drain SELECT must
    advance via `gt('sequence_no', last_sequence)`. A future
    contributor switching to `gte` would replay the last event each
    poll cycle and create a livelock."""
    src = _JOBS_PATH.read_text()
    match = re.search(
        r"async def stream_generation_job\(.*?\n    return StreamingResponse",
        src,
        re.DOTALL,
    )
    assert match is not None
    body = match.group(0)

    gt_count = len(re.findall(r"\.gt\(\"sequence_no\",\s*last_sequence\)", body))
    gte_count = len(re.findall(r"\.gte\(\"sequence_no\",\s*last_sequence\)", body))

    # Two GT calls: one in the polling loop, one in the terminal drain
    assert gt_count >= 2, f"expected ≥2 gt(sequence_no, last_sequence) calls, found {gt_count}"
    assert gte_count == 0, "gte(sequence_no, ...) replays events and creates livelocks"


def test_stream_endpoint_advances_last_sequence_after_each_event() -> None:
    """`last_sequence` MUST be updated to the highest sequence_no of
    the batch before yielding the SSE line — otherwise the next poll
    re-fetches the same row and the client sees duplicate events."""
    src = _JOBS_PATH.read_text()
    match = re.search(
        r"async def stream_generation_job\(.*?\n    return StreamingResponse",
        src,
        re.DOTALL,
    )
    assert match is not None
    body = match.group(0)

    # Pattern: last_sequence = max(last_sequence, int(row.get("sequence_no") or 0))
    advance = re.search(
        r"last_sequence\s*=\s*max\(last_sequence,\s*int\(row\.get\(\"sequence_no\"\)",
        body,
    )
    assert advance is not None, (
        "stream endpoint dropped last_sequence advancement — "
        "clients will receive duplicate events"
    )
