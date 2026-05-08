"""B3 \u2014 unit tests for the AIM database event sink.

Verifies that ``AIMDatabaseSink``:
  * persists every event with monotonic sequence,
  * preserves event_type / agent / status / data fields,
  * never raises on transient db failures (best-effort durability),
  * never persists token-delta events.
"""
from __future__ import annotations

from typing import Any

import pytest

from backend.tests.aim.test_aim_services import FakeDB

from app.services.aim.event_sink import AIMDatabaseSink
from app.services.pipeline_runtime import PipelineEvent


@pytest.mark.asyncio
async def test_database_sink_persists_event_with_sequence_and_fields():
    db = FakeDB()
    sink = AIMDatabaseSink(section_id="sec-1", user_id="u1", db=db)

    await sink.emit(PipelineEvent(
        event_type="agent_status", stage="writer", status="running",
        message="drafting", progress=10, latency_ms=0,
        pipeline_name="aim", data={"attempt": 1},
    ))
    await sink.emit(PipelineEvent(
        event_type="agent_status", stage="writer", status="completed",
        message="done", progress=20, latency_ms=42,
        pipeline_name="aim", data={"attempt": 1, "word_count": 200},
    ))

    rows = db._store.get("aim_section_events", [])  # type: ignore[attr-defined]
    assert len(rows) == 2
    assert [r["sequence"] for r in rows] == [1, 2]
    assert rows[0]["agent"] == "writer"
    assert rows[0]["status"] == "running"
    assert rows[0]["section_id"] == "sec-1"
    assert rows[0]["user_id"] == "u1"
    assert rows[0]["data"] == {"attempt": 1}
    assert rows[1]["latency_ms"] == 42
    assert rows[1]["data"]["word_count"] == 200
    # Each row gets a unique event_id for client-side dedup
    assert rows[0]["event_id"] != rows[1]["event_id"]


@pytest.mark.asyncio
async def test_database_sink_honours_preassigned_sequence_and_event_id():
    db = FakeDB()
    sink = AIMDatabaseSink(section_id="sec-1", user_id="u1", db=db)

    await sink.emit(PipelineEvent(
        event_type="attempt",
        stage="reviewer",
        data={"sequence": 8, "event_id": "evt-fixed", "weighted_score": 92},
    ))

    rows = db._store.get("aim_section_events", [])  # type: ignore[attr-defined]
    assert rows[0]["sequence"] == 8
    assert rows[0]["event_id"] == "evt-fixed"


@pytest.mark.asyncio
async def test_database_sink_swallows_db_errors():
    class ExplodingDB:
        async def create(self, *_a: Any, **_kw: Any) -> str:
            raise RuntimeError("supabase down")

    sink = AIMDatabaseSink(section_id="s", user_id="u", db=ExplodingDB())
    # Must NOT raise — the live SSE stream cannot be poisoned by a DB outage.
    await sink.emit(PipelineEvent(event_type="complete", pipeline_name="aim"))


@pytest.mark.asyncio
async def test_database_sink_drops_token_deltas():
    db = FakeDB()
    sink = AIMDatabaseSink(section_id="s", user_id="u", db=db)
    await sink.emit_token_delta(
        stage="writer", document_kind="section", delta="hello", sequence=0,
    )
    assert db._store.get("aim_section_events", []) == []  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_database_sink_prefers_stage_over_phase_for_agent_field():
    db = FakeDB()
    sink = AIMDatabaseSink(section_id="s", user_id="u", db=db)
    await sink.emit(PipelineEvent(
        event_type="agent_status", phase="ignored", stage="reviewer",
        status="completed",
    ))
    rows = db._store.get("aim_section_events", [])  # type: ignore[attr-defined]
    assert rows[0]["agent"] == "reviewer"


@pytest.mark.asyncio
async def test_database_sink_truncates_huge_messages():
    db = FakeDB()
    sink = AIMDatabaseSink(section_id="s", user_id="u", db=db)
    await sink.emit(PipelineEvent(
        event_type="error", message="x" * 10_000, status="failed",
    ))
    rows = db._store.get("aim_section_events", [])  # type: ignore[attr-defined]
    assert len(rows[0]["message"]) == 5000


@pytest.mark.asyncio
async def test_database_sink_handles_non_serialisable_data_gracefully():
    db = FakeDB()
    sink = AIMDatabaseSink(section_id="s", user_id="u", db=db)
    # Non-JSON-serialisable types (e.g. a set) are stripped, not raised.
    await sink.emit(PipelineEvent(
        event_type="agent_status", stage="writer", status="running",
        data={"tags": {"a", "b"}},  # set is not JSON
    ))
    rows = db._store.get("aim_section_events", [])  # type: ignore[attr-defined]
    assert len(rows) == 1
    # Round-trip via str repr is acceptable; must not be the original set
    assert isinstance(rows[0]["data"], dict)
