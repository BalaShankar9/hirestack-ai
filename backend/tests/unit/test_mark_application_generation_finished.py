"""S4-F4 — Pin `_mark_application_generation_finished` race protection.

The most subtle correctness invariant in the runtime: when two
generation jobs race against the same application (e.g. user
clicked Retry on a single module while a parent job was still
running), a `ready` module produced by one job MUST NOT be
overwritten with `error` / `idle` by the other job's terminal
finaliser. The user waited for that content; losing it is the
worst-case data-loss bug.

Other behaviours pinned:

  * Status `cancelled` → module stays `ready` if its column has
    content, otherwise drops to `idle` (NOT `error`, because the
    cancellation was user-initiated, not a generation failure).
  * Status `failed` → module flips to `error` and carries the
    `error_message` (with a sane default if the caller forgot one).
  * Status `succeeded` (anything else) → module flips to `ready`.
  * `application_row=None` triggers a fresh DB read so we don't
    trample concurrent mutations from a stale snapshot.
  * Final write goes through `_persist_application_patch` carrying
    the merged 9-key surface (defended by F3).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.api.routes.generate.jobs import _mark_application_generation_finished


# ── Tiny fake supabase client ──────────────────────────────────────────


class _FakeResp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQuery:
    """Records UPDATEs and answers SELECTs from a single mutable row."""

    def __init__(self, table_name: str, store: "_FakeStore") -> None:
        self._table = table_name
        self._store = store
        self._mode: Optional[str] = None
        self._patch: Dict[str, Any] = {}
        self._select_cols: Optional[str] = None
        self._eq_id: Optional[str] = None

    # Builder methods
    def update(self, patch: Dict[str, Any]) -> "_FakeQuery":
        self._mode = "update"
        self._patch = dict(patch)
        return self

    def select(self, cols: str) -> "_FakeQuery":
        self._mode = "select"
        self._select_cols = cols
        return self

    def eq(self, _col: str, value: str) -> "_FakeQuery":
        self._eq_id = value
        return self

    def maybe_single(self) -> "_FakeQuery":
        return self

    def execute(self) -> _FakeResp:
        if self._mode == "update":
            self._store.updates.append((self._table, dict(self._patch)))
            self._store.row.update(self._patch)
            return _FakeResp(None)
        if self._mode == "select":
            return _FakeResp(dict(self._store.row))
        raise RuntimeError(f"unexpected query mode {self._mode}")


class _FakeStore:
    def __init__(self, row: Dict[str, Any]) -> None:
        self.row = row
        self.updates: List[tuple[str, Dict[str, Any]]] = []


class _FakeSb:
    def __init__(self, store: _FakeStore) -> None:
        self._store = store

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(name, self._store)


_TABLES = {"applications": "applications"}


def _last_modules(store: _FakeStore) -> Dict[str, Any]:
    """Return the most recent `modules` dict written to the DB."""
    for table, patch in reversed(store.updates):
        if "modules" in patch:
            return patch["modules"]
    raise AssertionError("no modules write recorded")


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_succeeded_marks_modules_ready() -> None:
    store = _FakeStore({"id": "app-1", "modules": {}})
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        {"id": "app-1", "modules": {"cv": {"state": "generating"}}},
        ["cv", "coverLetter"],
        status="succeeded",
    )
    modules = _last_modules(store)
    assert modules["cv"]["state"] == "ready"
    assert modules["coverLetter"]["state"] == "ready"
    # Untouched modules retain their default
    assert modules["resume"]["state"] == "idle"


@pytest.mark.asyncio
async def test_failed_marks_modules_error_with_message() -> None:
    store = _FakeStore({"id": "app-1", "modules": {}})
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        {"id": "app-1", "modules": {"cv": {"state": "generating"}}},
        ["cv"],
        status="failed",
        error_message="boom",
    )
    modules = _last_modules(store)
    assert modules["cv"]["state"] == "error"
    assert modules["cv"]["error"] == "boom"


@pytest.mark.asyncio
async def test_failed_uses_default_error_message_when_none_provided() -> None:
    store = _FakeStore({"id": "app-1", "modules": {}})
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        {"id": "app-1", "modules": {"cv": {"state": "generating"}}},
        ["cv"],
        status="failed",
    )
    modules = _last_modules(store)
    assert modules["cv"]["state"] == "error"
    assert modules["cv"]["error"]  # non-empty default


@pytest.mark.asyncio
async def test_failed_does_not_overwrite_ready_module() -> None:
    """The headline race-protection invariant: a concurrent successful
    job already set `cv` to `ready`, then this failed job must NOT
    flip it back to `error`."""
    store = _FakeStore({
        "id": "app-1",
        "modules": {"cv": {"state": "ready", "updatedAt": 100}},
        "cv_html": "<p>generated content</p>",
    })
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        # Pass the *same* fresh row so the helper sees `cv: ready`
        {
            "id": "app-1",
            "modules": {"cv": {"state": "ready", "updatedAt": 100}},
            "cv_html": "<p>generated content</p>",
        },
        ["cv"],
        status="failed",
        error_message="boom",
    )
    modules = _last_modules(store)
    assert modules["cv"]["state"] == "ready"
    assert modules["cv"].get("error") is None


@pytest.mark.asyncio
async def test_cancelled_does_not_overwrite_ready_module() -> None:
    """Same race-protection guarantee for status=cancelled."""
    store = _FakeStore({
        "id": "app-1",
        "modules": {"coverLetter": {"state": "ready", "updatedAt": 100}},
        "cover_letter_html": "<p>letter</p>",
    })
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        {
            "id": "app-1",
            "modules": {"coverLetter": {"state": "ready", "updatedAt": 100}},
            "cover_letter_html": "<p>letter</p>",
        },
        ["coverLetter"],
        status="cancelled",
    )
    modules = _last_modules(store)
    assert modules["coverLetter"]["state"] == "ready"


@pytest.mark.asyncio
async def test_cancelled_drops_to_ready_when_column_has_content() -> None:
    """If a cancelled job's module slot already has rendered content
    (e.g. cancellation hit during finalisation), surface `ready` so
    the user can see what was generated before the cancel."""
    store = _FakeStore({
        "id": "app-1",
        "modules": {"cv": {"state": "generating"}},
        "cv_html": "<p>partial</p>",
    })
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        {
            "id": "app-1",
            "modules": {"cv": {"state": "generating"}},
            "cv_html": "<p>partial</p>",
        },
        ["cv"],
        status="cancelled",
    )
    modules = _last_modules(store)
    assert modules["cv"]["state"] == "ready"


@pytest.mark.asyncio
async def test_cancelled_drops_to_idle_when_no_content() -> None:
    """Cancelled with no rendered content goes to idle (NOT error —
    cancellation is user-initiated, not a generation failure)."""
    store = _FakeStore({
        "id": "app-1",
        "modules": {"cv": {"state": "generating"}},
    })
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        {"id": "app-1", "modules": {"cv": {"state": "generating"}}},
        ["cv"],
        status="cancelled",
    )
    modules = _last_modules(store)
    assert modules["cv"]["state"] == "idle"
    assert modules["cv"].get("error") is None


@pytest.mark.asyncio
async def test_none_application_row_triggers_fresh_db_read() -> None:
    """Stale-snapshot defence: passing application_row=None forces a
    fresh SELECT so the helper sees concurrent mutations from other
    jobs (e.g. cv flipped to ready)."""
    store = _FakeStore({
        "id": "app-1",
        "modules": {"cv": {"state": "ready", "updatedAt": 100}},
        "cv_html": "<p>ok</p>",
    })
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        None,  # ← force re-read
        ["cv"],
        status="failed",
        error_message="boom",
    )
    modules = _last_modules(store)
    # The fresh read saw cv=ready, so the failed status is suppressed.
    assert modules["cv"]["state"] == "ready"


@pytest.mark.asyncio
async def test_writes_full_9_key_module_surface() -> None:
    """Whatever the input row carried, the persist must write the full
    canonical 9-key surface (defended by F3 _merge_module_states)."""
    store = _FakeStore({"id": "app-1", "modules": {}})
    await _mark_application_generation_finished(
        _FakeSb(store),
        _TABLES,
        "app-1",
        {"id": "app-1", "modules": {}},
        ["cv"],
        status="succeeded",
    )
    modules = _last_modules(store)
    expected_keys = {
        "benchmark", "gaps", "learningPlan", "cv", "resume",
        "coverLetter", "personalStatement", "portfolio", "scorecard",
    }
    assert expected_keys.issubset(modules.keys())
