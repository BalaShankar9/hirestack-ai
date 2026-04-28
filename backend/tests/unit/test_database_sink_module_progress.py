"""S3-F4 — Behavioral tests for DatabaseSink._update_module_progress.

The module-progress writer pushes the current pipeline progress into
`applications.modules` so module cards on the frontend animate in
real-time. Two invariants matter:

  * **5%-step throttle** — calls within 5% of the previous push must
    NOT issue a UPDATE (saves DB write amplification on chatty
    pipelines).
  * **state filter** — only modules currently in `generating` or
    `queued` state get their progress overwritten; modules already
    `completed` or `failed` must be left alone.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services.pipeline_runtime import DatabaseSink, PipelineEvent


# ── Fake DB that returns a configurable modules snapshot ──────────────


class _AppsDB:
    def __init__(self, modules: Dict[str, Any]):
        self._modules = modules
        self.updates: List[Dict[str, Any]] = []
        self.events_inserts: List[Dict[str, Any]] = []
        self.jobs_updates: List[Dict[str, Any]] = []

    def table(self, name: str):
        outer = self

        class _Q:
            def __init__(self):
                self._table = name
                self._op = ""
                self._row: Any = None

            def insert(self, row):
                self._op = "insert"
                self._row = row
                return self

            def update(self, row):
                self._op = "update"
                self._row = row
                return self

            def select(self, *_a, **_k):
                self._op = "select"
                return self

            def eq(self, *_a, **_k):
                return self

            def maybe_single(self):
                return self

            def execute(self):
                if self._table == "applications" and self._op == "select":
                    class _R: pass
                    r = _R()
                    r.data = {"modules": outer._modules}
                    return r
                if self._table == "applications" and self._op == "update":
                    outer.updates.append(self._row)
                    # Keep modules dict in sync so subsequent selects see it
                    outer._modules = self._row.get("modules", outer._modules)
                if self._table == "generation_job_events" and self._op == "insert":
                    outer.events_inserts.append(self._row)
                if self._table == "generation_jobs" and self._op == "update":
                    outer.jobs_updates.append(self._row)
                class _R: pass
                r = _R()
                r.data = None
                return r

        return _Q()


def _sink(db: _AppsDB, modules: list[str] | None = None) -> DatabaseSink:
    return DatabaseSink(
        db=db,
        tables={
            "generation_jobs": "generation_jobs",
            "generation_job_events": "generation_job_events",
            "applications": "applications",
        },
        job_id="job-1",
        user_id="user-1",
        application_id="app-1",
        requested_modules=["cv", "cover_letter"] if modules is None else modules,
    )


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_progress_emit_writes_module_progress() -> None:
    db = _AppsDB(modules={
        "cv": {"state": "generating", "progress": 0},
        "cover_letter": {"state": "queued", "progress": 0},
    })
    sink = _sink(db)
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=20))

    # First emit always writes (last_module_progress starts at -1)
    assert len(db.updates) == 1
    written = db.updates[0]["modules"]
    assert written["cv"]["progress"] == 20
    assert written["cover_letter"]["progress"] == 20
    assert "updatedAt" in written["cv"]


@pytest.mark.asyncio
async def test_throttle_skips_updates_within_5_percent() -> None:
    db = _AppsDB(modules={"cv": {"state": "generating", "progress": 0}})
    sink = _sink(db, modules=["cv"])

    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=20))
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=22))  # +2: throttled
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=24))  # +4: throttled

    assert len(db.updates) == 1, "Δ < 5% must not re-issue an UPDATE"


@pytest.mark.asyncio
async def test_throttle_releases_at_5_percent_step() -> None:
    db = _AppsDB(modules={"cv": {"state": "generating", "progress": 0}})
    sink = _sink(db, modules=["cv"])

    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=10))
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=15))  # +5: write
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=20))  # +5: write

    assert len(db.updates) == 3


@pytest.mark.asyncio
async def test_state_filter_skips_completed_and_failed_modules() -> None:
    db = _AppsDB(modules={
        "cv": {"state": "generating", "progress": 10},
        "cover_letter": {"state": "completed", "progress": 100},
        "portfolio": {"state": "failed", "progress": 50},
    })
    sink = _sink(db, modules=["cv", "cover_letter", "portfolio"])
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=42))

    written = db.updates[0]["modules"]
    assert written["cv"]["progress"] == 42, "generating → updated"
    # completed/failed left alone
    assert written["cover_letter"]["progress"] == 100
    assert written["cover_letter"]["state"] == "completed"
    assert written["portfolio"]["progress"] == 50
    assert written["portfolio"]["state"] == "failed"


@pytest.mark.asyncio
async def test_no_requested_modules_means_no_module_writes() -> None:
    db = _AppsDB(modules={"cv": {"state": "generating", "progress": 0}})
    sink = _sink(db, modules=[])  # empty
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=42))
    assert db.updates == []


@pytest.mark.asyncio
async def test_module_progress_failure_is_swallowed() -> None:
    """A flaky DB on the applications table must not crash the pipeline."""
    class _Boom(_AppsDB):
        def table(self, name):
            if name == "applications":
                class _Q:
                    def select(self, *a, **k): return self
                    def eq(self, *a, **k): return self
                    def maybe_single(self): return self
                    def update(self, *a, **k): return self
                    def execute(self): raise RuntimeError("apps table down")
                return _Q()
            return super().table(name)

    db = _Boom(modules={})
    sink = _sink(db, modules=["cv"])
    # Must not raise.
    await sink.emit(PipelineEvent(event_type="progress", phase="recon", progress=20))
