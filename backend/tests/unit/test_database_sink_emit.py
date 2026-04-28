"""S3-F2 — Behavioral tests for DatabaseSink.emit.

DatabaseSink is the only path from an in-flight pipeline event to a
persisted row in `generation_job_events` AND it owns the live mirror
of the `generation_jobs` row (progress, phase, current_agent,
completed_steps) that polling clients depend on.

These tests pin the contract:
  * progress events insert a job-event row with top-level columns
    (message, agent_name, stage, status, latency_ms) populated, not
    just stuffed inside `payload` (frontend dock reads top-level).
  * progress events update the generation_jobs snapshot.
  * redundant updates (same snapshot) are skipped.
  * an insert/update failure does not break the pipeline (caught,
    logged, swallowed).
  * `complete` events push progress=100 and current_agent=nova.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services.pipeline_runtime import DatabaseSink, PipelineEvent


# ── Fake supabase client ──────────────────────────────────────────────

class _FakeQuery:
    def __init__(self, table: str, log: List[Dict[str, Any]]):
        self._table = table
        self._log = log
        self._op: str = ""
        self._row: Any = None
        self._filters: Dict[str, Any] = {}

    def insert(self, row: Dict[str, Any]) -> "_FakeQuery":
        self._op = "insert"
        self._row = row
        return self

    def update(self, row: Dict[str, Any]) -> "_FakeQuery":
        self._op = "update"
        self._row = row
        return self

    def select(self, *_a, **_k) -> "_FakeQuery":
        self._op = "select"
        return self

    def eq(self, key: str, value: Any) -> "_FakeQuery":
        self._filters[key] = value
        return self

    def maybe_single(self) -> "_FakeQuery":
        return self

    def execute(self):
        self._log.append({
            "table": self._table,
            "op": self._op,
            "row": self._row,
            "filters": dict(self._filters),
        })
        # `select` calls (used by _update_module_progress) need a `.data` shape.
        class _R:
            data = {"modules": {}}
        return _R()


class _FakeDB:
    def __init__(self):
        self.log: List[Dict[str, Any]] = []

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(name, self.log)


def _sink(db: _FakeDB | None = None) -> DatabaseSink:
    return DatabaseSink(
        db=db or _FakeDB(),
        tables={
            "generation_jobs": "generation_jobs",
            "generation_job_events": "generation_job_events",
            "applications": "applications",
        },
        job_id="job-1",
        user_id="user-1",
        application_id="app-1",
    )


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_progress_event_inserts_job_event_row_with_top_level_columns() -> None:
    db = _FakeDB()
    sink = _sink(db)

    await sink.emit(PipelineEvent(
        event_type="progress",
        phase="recon",
        progress=10,
        message="Recon started",
        status="running",
        stage="researcher",
        latency_ms=42,
    ))

    inserts = [c for c in db.log if c["op"] == "insert" and c["table"] == "generation_job_events"]
    assert len(inserts) == 1, "exactly one job_events row written"
    row = inserts[0]["row"]
    # Top-level columns the frontend dock reads from
    assert row["event_name"] == "progress"
    assert row["message"] == "Recon started"
    assert row["agent_name"] == "recon"
    assert row["stage"] == "researcher"
    assert row["status"] == "running"
    assert row["latency_ms"] == 42
    assert row["sequence_no"] == 1
    # Payload still carries everything for replay
    assert row["payload"]["phase"] == "recon"
    assert row["payload"]["progress"] == 10


@pytest.mark.asyncio
async def test_progress_event_updates_generation_jobs_snapshot() -> None:
    db = _FakeDB()
    sink = _sink(db)
    await sink.emit(PipelineEvent(
        event_type="progress", phase="atlas", progress=25, message="Atlas drafting",
    ))

    job_updates = [
        c for c in db.log
        if c["op"] == "update" and c["table"] == "generation_jobs"
    ]
    assert len(job_updates) == 1
    fields = job_updates[0]["row"]
    assert fields["progress"] == 25
    assert fields["status"] == "running"
    assert fields["phase"] == "atlas"
    assert fields["current_agent"] == "atlas"
    assert fields["completed_steps"] == 1  # _PHASE_ORDER.index("atlas") == 1
    assert fields["total_steps"] == 7
    assert job_updates[0]["filters"] == {"id": "job-1"}


@pytest.mark.asyncio
async def test_redundant_job_snapshot_updates_are_skipped() -> None:
    db = _FakeDB()
    sink = _sink(db)
    ev = PipelineEvent(event_type="progress", phase="atlas", progress=25, message="m")
    await sink.emit(ev)
    await sink.emit(ev)

    job_updates = [c for c in db.log if c["op"] == "update" and c["table"] == "generation_jobs"]
    assert len(job_updates) == 1, "second emit with identical snapshot must not re-issue UPDATE"


@pytest.mark.asyncio
async def test_complete_event_pins_progress_100_and_nova() -> None:
    db = _FakeDB()
    sink = _sink(db)
    await sink.emit(PipelineEvent(event_type="complete", message="done"))

    job_updates = [c for c in db.log if c["op"] == "update" and c["table"] == "generation_jobs"]
    assert len(job_updates) == 1
    fields = job_updates[0]["row"]
    assert fields["progress"] == 100
    assert fields["phase"] == "complete"
    assert fields["current_agent"] == "nova"
    assert fields["completed_steps"] == 7
    assert fields["total_steps"] == 7


@pytest.mark.asyncio
async def test_event_persist_failure_is_swallowed_not_raised() -> None:
    """A flaky DB on the events table must not crash the pipeline."""
    class _ExplodingDB(_FakeDB):
        def table(self, name: str):
            class _Boom:
                def insert(self, *_a, **_k): raise RuntimeError("db down")
                def update(self, *_a, **_k): return self
                def eq(self, *_a, **_k): return self
                def execute(self): return None
            return _Boom() if name == "generation_job_events" else super().table.__func__(self, name)  # type: ignore[attr-defined]

    sink = _sink(_ExplodingDB())
    # Must not raise.
    await sink.emit(PipelineEvent(
        event_type="progress", phase="recon", progress=5, message="m",
    ))


@pytest.mark.asyncio
async def test_sequence_no_increments_monotonically() -> None:
    db = _FakeDB()
    sink = _sink(db)
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=1))
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=2))
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=3))

    inserts = [c["row"]["sequence_no"] for c in db.log
               if c["op"] == "insert" and c["table"] == "generation_job_events"]
    assert inserts == [1, 2, 3]


@pytest.mark.asyncio
async def test_completed_steps_never_regress_on_phase_skip_back() -> None:
    """If for any reason a late event re-emits an earlier phase, the
    completed_steps counter must take max() and not slide backwards —
    polling clients rely on monotonic progress."""
    db = _FakeDB()
    sink = _sink(db)

    await sink.emit(PipelineEvent(event_type="progress", phase="forge", progress=60))
    await sink.emit(PipelineEvent(event_type="progress", phase="atlas", progress=25))

    updates = [c["row"] for c in db.log
               if c["op"] == "update" and c["table"] == "generation_jobs"]
    # forge → completed_steps = 4; atlas after forge must NOT pull it back to 1
    assert updates[0]["completed_steps"] == 4
    assert updates[1]["completed_steps"] == 4
