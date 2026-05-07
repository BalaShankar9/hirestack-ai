"""PR m6-pr19c — backfill_aim_source_embeddings unit tests.

Exercises the pure pieces (`fetch_pending_batch`, `run_backfill`,
`_parse_args`) without standing up Supabase or OpenAI.
"""
from __future__ import annotations

from typing import Any

import pytest

from scripts.backfill_aim_source_embeddings import (
    _parse_args,
    fetch_pending_batch,
    run_backfill,
)


# ── Fakes ────────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]], log: list[dict[str, Any]],
                 filters: dict[str, Any]):
        self._rows = rows
        self._log = log
        self._filters = dict(filters)
        self._limit = None

    def select(self, *a, **kw): return self
    def order(self, *a, **kw): return self

    def is_(self, col, val):
        self._filters[f"is_{col}"] = val
        return self

    def gt(self, col, val):
        self._filters[f"gt_{col}"] = val
        return self

    def eq(self, col, val):
        self._filters[f"eq_{col}"] = val
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        self._log.append({"filters": self._filters, "limit": self._limit})
        # Apply gt(id) cursor + eq(organization_id) so pagination works.
        rows = list(self._rows)
        cursor = self._filters.get("gt_id")
        if cursor is not None:
            rows = [r for r in rows if r["id"] > cursor]
        org = self._filters.get("eq_organization_id")
        if org is not None:
            rows = [r for r in rows if r.get("organization_id") == org]
        return _Resp(rows[: (self._limit or len(rows))])


class _FakeSupabase:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self.queries: list[dict[str, Any]] = []

    def table(self, name):
        assert name == "aim_sources"
        return _FakeQuery(self._rows, self.queries, {})


class _FakeService:
    def __init__(self, *, fail_ids: set[str] | None = None,
                 empty_ids: set[str] | None = None):
        self.fail_ids = fail_ids or set()
        self.empty_ids = empty_ids or set()
        self.calls: list[str] = []

    async def embed_source(self, *, source_id, title, extracted_summary):
        self.calls.append(source_id)
        if source_id in self.fail_ids:
            raise RuntimeError("boom")
        if source_id in self.empty_ids:
            return None
        return object()


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_pending_batch_filters_and_paginates():
    rows = [
        {"id": "a", "title": "t", "extracted_summary": "s", "organization_id": "o1"},
        {"id": "b", "title": "t", "extracted_summary": "s", "organization_id": "o2"},
        {"id": "c", "title": "t", "extracted_summary": "s", "organization_id": "o1"},
    ]
    sb = _FakeSupabase(rows)
    page = await fetch_pending_batch(
        supabase=sb, batch_size=10, after_id="a", org_id="o1"
    )
    assert [r["id"] for r in page] == ["c"]
    # Verify the query was assembled with the right filters.
    assert sb.queries[-1]["filters"]["gt_id"] == "a"
    assert sb.queries[-1]["filters"]["eq_organization_id"] == "o1"
    assert sb.queries[-1]["filters"]["is_embedding"] is None
    assert sb.queries[-1]["limit"] == 10


@pytest.mark.asyncio
async def test_run_backfill_dry_run_does_not_call_embedder():
    rows = [{"id": f"{i}", "title": "t", "extracted_summary": "s",
             "organization_id": "o"} for i in range(3)]
    svc = _FakeService()
    counts = await run_backfill(
        service=svc, supabase=_FakeSupabase(rows),
        batch_size=10, limit=None, org_id=None, dry_run=True,
    )
    assert counts == {"scanned": 3, "embedded": 0, "skipped": 3, "failed": 0}
    assert svc.calls == []


@pytest.mark.asyncio
async def test_run_backfill_counts_success_skip_failure():
    rows = [{"id": "1", "title": "t", "extracted_summary": "s",
             "organization_id": "o"},
            {"id": "2", "title": "t", "extracted_summary": "s",
             "organization_id": "o"},
            {"id": "3", "title": "t", "extracted_summary": "s",
             "organization_id": "o"}]
    svc = _FakeService(fail_ids={"2"}, empty_ids={"3"})
    counts = await run_backfill(
        service=svc, supabase=_FakeSupabase(rows),
        batch_size=10, limit=None, org_id=None, dry_run=False,
    )
    assert counts == {"scanned": 3, "embedded": 1, "skipped": 1, "failed": 1}
    assert svc.calls == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_run_backfill_paginates_across_batches():
    rows = [{"id": f"{i:02d}", "title": "t", "extracted_summary": "s",
             "organization_id": "o"} for i in range(5)]
    svc = _FakeService()
    sb = _FakeSupabase(rows)
    counts = await run_backfill(
        service=svc, supabase=sb, batch_size=2, limit=None,
        org_id=None, dry_run=False,
    )
    assert counts["scanned"] == 5 and counts["embedded"] == 5
    # 4 fetches: 2 + 2 + 1 + final empty page that terminates the loop.
    assert len(sb.queries) == 4


@pytest.mark.asyncio
async def test_run_backfill_respects_limit():
    rows = [{"id": f"{i:02d}", "title": "t", "extracted_summary": "s",
             "organization_id": "o"} for i in range(10)]
    svc = _FakeService()
    counts = await run_backfill(
        service=svc, supabase=_FakeSupabase(rows),
        batch_size=4, limit=3, org_id=None, dry_run=False,
    )
    assert counts["scanned"] == 3
    assert svc.calls == ["00", "01", "02"]


def test_parse_args_defaults_and_overrides():
    a = _parse_args([])
    assert a.batch_size == 50 and a.limit is None
    assert a.org_id is None and a.dry_run is False

    b = _parse_args(["--batch-size", "10", "--limit", "100",
                     "--org-id", "o1", "--dry-run"])
    assert b.batch_size == 10 and b.limit == 100
    assert b.org_id == "o1" and b.dry_run is True
