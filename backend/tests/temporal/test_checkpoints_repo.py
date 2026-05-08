"""Tests for ``backend/app/temporal/checkpoints.py`` (ADR-0036, m8-pr32)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.temporal.checkpoints import (
    CHECKPOINT_SUMMARY_MAX_BYTES,
    Checkpoint,
    CheckpointStore,
    _truncate_summary,
)


# ── Fakes ─────────────────────────────────────────────────────────────────

class _FakeQuery:
    def __init__(self, fake_table: "_FakeTable") -> None:
        self._fake_table = fake_table
        self._eq_filters: list[tuple[str, Any]] = []
        self._maybe_single = False

    def select(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def eq(self, col: str, val: Any) -> "_FakeQuery":
        self._eq_filters.append((col, val))
        return self

    def maybe_single(self) -> "_FakeQuery":
        self._maybe_single = True
        return self

    def execute(self) -> Any:
        if self._fake_table.read_raises:
            raise self._fake_table.read_raises
        # Match by job_id + stage among rows
        rows = list(self._fake_table.rows)
        for col, val in self._eq_filters:
            rows = [r for r in rows if r.get(col) == val]
        resp = MagicMock()
        resp.data = rows[0] if rows else None
        return resp


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.upserts: list[dict[str, Any]] = []
        self.upsert_raises: Exception | None = None
        self.read_raises: Exception | None = None

    # Read API
    def select(self, *args: Any, **kwargs: Any) -> _FakeQuery:
        q = _FakeQuery(self)
        return q.select(*args, **kwargs)

    # Write API
    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> "_FakeTable":
        self._pending_upsert = payload
        return self

    def execute(self) -> Any:
        if self.upsert_raises:
            raise self.upsert_raises
        # Apply upsert: replace row matching (job_id, stage) or append
        payload = self._pending_upsert
        for i, existing in enumerate(self.rows):
            if (
                existing.get("job_id") == payload.get("job_id")
                and existing.get("stage") == payload.get("stage")
            ):
                merged = {**existing, **payload}
                self.rows[i] = merged
                self.upserts.append(payload)
                return MagicMock(data=[merged])
        self.rows.append(dict(payload))
        self.upserts.append(payload)
        return MagicMock(data=[payload])


class _FakeSupabase:
    def __init__(self) -> None:
        self._tables: dict[str, _FakeTable] = {}

    def table(self, name: str) -> _FakeTable:
        if name not in self._tables:
            self._tables[name] = _FakeTable()
        return self._tables[name]


@pytest.fixture
def supa() -> _FakeSupabase:
    return _FakeSupabase()


@pytest.fixture
def store(supa: _FakeSupabase) -> CheckpointStore:
    return CheckpointStore(supa)


# ── _truncate_summary ─────────────────────────────────────────────────────

def test_truncate_summary_returns_none_for_none():
    assert _truncate_summary(None) is None


def test_truncate_summary_returns_summary_when_under_cap():
    s = {"a": 1, "b": "hi"}
    assert _truncate_summary(s) is s


def test_truncate_summary_returns_marker_when_over_cap():
    big = {"x": "z" * (CHECKPOINT_SUMMARY_MAX_BYTES + 100)}
    out = _truncate_summary(big)
    assert out is not None
    assert out["__truncated__"] is True
    assert out["original_bytes"] > CHECKPOINT_SUMMARY_MAX_BYTES


def test_truncate_summary_handles_unencodable_value():
    class _Weird:
        def __repr__(self) -> str:
            raise RuntimeError("boom")
    # default=str handles most, but a __repr__ that raises will still fail
    # via dumps(default=str) -> str(_Weird()) -> calls __repr__ -> raises.
    out = _truncate_summary({"weird": _Weird()})
    assert out == {"__truncated__": True, "reason": "encode_failed"}


# ── read / is_complete ────────────────────────────────────────────────────

def test_read_returns_none_when_row_missing(store: CheckpointStore):
    assert store.read("job-1", "recon") is None


def test_read_returns_checkpoint_when_row_present(supa: _FakeSupabase, store: CheckpointStore):
    supa.table("pipeline_checkpoints").rows.append(
        {
            "job_id": "job-1",
            "stage": "recon",
            "status": "complete",
            "attempt_count": 2,
            "output_summary": {"k": "v"},
            "error_class": None,
            "completed_at": "2026-05-08T00:00:00Z",
        }
    )
    cp = store.read("job-1", "recon")
    assert isinstance(cp, Checkpoint)
    assert cp.status == "complete"
    assert cp.attempt_count == 2
    assert cp.output_summary == {"k": "v"}


def test_read_returns_none_on_db_exception(supa: _FakeSupabase, store: CheckpointStore):
    supa.table("pipeline_checkpoints").read_raises = RuntimeError("conn lost")
    assert store.read("job-1", "recon") is None


def test_is_complete_true_when_status_complete(supa: _FakeSupabase, store: CheckpointStore):
    supa.table("pipeline_checkpoints").rows.append(
        {"job_id": "j", "stage": "recon", "status": "complete", "attempt_count": 1}
    )
    assert store.is_complete("j", "recon") is True


def test_is_complete_false_when_status_running(supa: _FakeSupabase, store: CheckpointStore):
    supa.table("pipeline_checkpoints").rows.append(
        {"job_id": "j", "stage": "recon", "status": "running", "attempt_count": 1}
    )
    assert store.is_complete("j", "recon") is False


def test_is_complete_false_when_missing(store: CheckpointStore):
    assert store.is_complete("j", "recon") is False


# ── mark_running ──────────────────────────────────────────────────────────

def test_mark_running_inserts_with_attempt_one(supa: _FakeSupabase, store: CheckpointStore):
    store.mark_running("job-1", "recon")
    rows = supa.table("pipeline_checkpoints").rows
    assert len(rows) == 1
    assert rows[0]["status"] == "running"
    assert rows[0]["attempt_count"] == 1


def test_mark_running_increments_attempt_when_existing(
    supa: _FakeSupabase, store: CheckpointStore
):
    supa.table("pipeline_checkpoints").rows.append(
        {"job_id": "job-1", "stage": "recon", "status": "failed", "attempt_count": 2}
    )
    store.mark_running("job-1", "recon")
    rows = supa.table("pipeline_checkpoints").rows
    assert len(rows) == 1
    assert rows[0]["status"] == "running"
    assert rows[0]["attempt_count"] == 3


def test_mark_running_swallows_db_exception(supa: _FakeSupabase, store: CheckpointStore):
    supa.table("pipeline_checkpoints").upsert_raises = RuntimeError("boom")
    # Must not raise.
    store.mark_running("job-1", "recon")


# ── mark_complete ─────────────────────────────────────────────────────────

def test_mark_complete_sets_status_and_summary(supa: _FakeSupabase, store: CheckpointStore):
    store.mark_complete("job-1", "recon", summary={"a": 1})
    rows = supa.table("pipeline_checkpoints").rows
    assert rows[0]["status"] == "complete"
    assert rows[0]["output_summary"] == {"a": 1}
    assert rows[0]["completed_at"] is not None


def test_mark_complete_truncates_oversize_summary(
    supa: _FakeSupabase, store: CheckpointStore
):
    big = {"x": "y" * (CHECKPOINT_SUMMARY_MAX_BYTES + 50)}
    store.mark_complete("job-1", "recon", summary=big)
    out = supa.table("pipeline_checkpoints").rows[0]["output_summary"]
    assert out["__truncated__"] is True


def test_mark_complete_swallows_db_exception(supa: _FakeSupabase, store: CheckpointStore):
    supa.table("pipeline_checkpoints").upsert_raises = RuntimeError("boom")
    store.mark_complete("job-1", "recon", summary={"a": 1})  # must not raise


# ── mark_failed ───────────────────────────────────────────────────────────

def test_mark_failed_records_error_class(supa: _FakeSupabase, store: CheckpointStore):
    store.mark_failed("job-1", "quill", "TimeoutError")
    rows = supa.table("pipeline_checkpoints").rows
    assert rows[0]["status"] == "failed"
    assert rows[0]["error_class"] == "TimeoutError"


def test_mark_failed_truncates_long_error_class(supa: _FakeSupabase, store: CheckpointStore):
    long_name = "X" * 500
    store.mark_failed("job-1", "quill", long_name)
    rows = supa.table("pipeline_checkpoints").rows
    assert len(rows[0]["error_class"]) == 200


def test_mark_failed_swallows_db_exception(supa: _FakeSupabase, store: CheckpointStore):
    supa.table("pipeline_checkpoints").upsert_raises = RuntimeError("boom")
    store.mark_failed("job-1", "quill", "TimeoutError")  # must not raise
