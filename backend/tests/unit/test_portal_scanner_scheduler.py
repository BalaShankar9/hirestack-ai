"""Tests for portal_scanner_scheduler.run_user_scan_tick.

End-to-end orchestration: in-memory DB + canned fetcher exercise the
load → run_scan → mark_scanned pipeline without any HTTP or
real Supabase.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Mapping

import pytest

from app.core.database import TABLES
from app.services.portal_scanner_scheduler import (
    TickResult,
    run_user_scan_tick,
)
from app.services.portal_scanner_worker import FetchResult


# ── In-memory DB fake (slim copy of the repo test fake) ──────────────


class _FakeDB:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        scan_history_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        for r in rows or []:
            self.rows[r["id"]] = dict(r)
        self.scan_history_rows: dict[str, dict[str, Any]] = {}
        for r in scan_history_rows or []:
            self.scan_history_rows[r["id"]] = dict(r)
        self.update_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self._history_counter = len(self.scan_history_rows)

    async def create(self, table: str, data: dict[str, Any], doc_id=None) -> str:
        assert table == TABLES["job_scan_history"]
        self._history_counter += 1
        new_id = doc_id or f"history-{self._history_counter}"
        payload = {**data, "id": new_id}
        self.scan_history_rows[new_id] = payload
        self.create_calls.append((table, payload))
        return new_id

    async def query(
        self,
        table: str,
        filters: list[tuple] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
        offset: int | None = None,
    ) -> List[Mapping[str, Any]]:
        if table == TABLES["tracked_companies"]:
            out = list(self.rows.values())
        elif table == TABLES["job_scan_history"]:
            out = list(self.scan_history_rows.values())
        else:  # pragma: no cover - unsupported table in these tests
            raise AssertionError(f"unexpected table {table!r}")
        for field, op, value in filters or []:
            if op == "==":
                out = [r for r in out if r.get(field) == value]
            elif op == "in":
                out = [r for r in out if r.get(field) in value]
        return out

    async def update(self, table: str, doc_id: str, data: dict[str, Any]) -> bool:
        self.update_calls.append((table, doc_id, dict(data)))
        if table == TABLES["tracked_companies"]:
            if doc_id not in self.rows:
                return False
            self.rows[doc_id].update(data)
            return True
        if table == TABLES["job_scan_history"]:
            if doc_id not in self.scan_history_rows:
                return False
            self.scan_history_rows[doc_id].update(data)
            return True
        raise AssertionError(f"unexpected table {table!r}")


def _history_row(
    *,
    id: str = "history-1",
    url_canonical: str = "https://boards.greenhouse.io/acme/jobs/1",
    company_slug: str = "acme",
    role_title: str = "Senior Engineer",
    first_seen: str = "2026-05-01T00:00:00+00:00",
    last_seen: str = "2026-05-01T00:00:00+00:00",
    times_seen: int = 1,
) -> dict[str, Any]:
    return {
        "id": id,
        "url_canonical": url_canonical,
        "company_slug": company_slug,
        "role_title": role_title,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "times_seen": times_seen,
    }


def _row(
    *,
    id: str,
    user_id: str = "u1",
    provider: str = "greenhouse",
    company_slug: str = "acme",
    workday_tenant: str | None = None,
    enabled: bool = True,
    last_scanned_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "user_id": user_id,
        "provider": provider,
        "company_slug": company_slug,
        "workday_tenant": workday_tenant,
        "enabled": enabled,
        "last_scanned_at": last_scanned_at,
    }


# ── Canned fetcher helpers ───────────────────────────────────────────


def _gh_payload(*titles: str) -> dict:
    """Greenhouse listing JSON: ``{"jobs": [...]}``.

    Match the shape parse_greenhouse expects so worker.run_scan
    actually emits JobPosting rows.
    """
    return {
        "jobs": [
            {
                "id": abs(hash(t)) % 10_000_000,
                "title": t,
                "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{abs(hash(t)) % 10_000_000}",
                "location": {"name": "Remote"},
                "updated_at": "2026-04-30T10:00:00Z",
            }
            for i, t in enumerate(titles)
        ]
    }


def _make_fetcher(*, payload_by_url: dict[str, dict] | None = None,
                  status_by_url: dict[str, int] | None = None):
    """Build an async fetcher returning canned results per URL."""
    payload_by_url = payload_by_url or {}
    status_by_url = status_by_url or {}

    async def _fetch(url: str) -> FetchResult:
        if url in status_by_url and status_by_url[url] != 200:
            s = status_by_url[url]
            return FetchResult(status=s, payload=None, error=f"http_{s}")
        return FetchResult(status=200, payload=payload_by_url.get(url, {"jobs": []}))

    return _fetch


_TICK_NOW = datetime(2026, 5, 3, 9, 0, 0, tzinfo=timezone.utc)


# ── Scheduler tick tests ─────────────────────────────────────────────


class TestEmptyWatchlist:
    @pytest.mark.asyncio
    async def test_no_companies_short_circuits(self):
        db = _FakeDB([])
        called: list[str] = []

        async def _fetch(url: str) -> FetchResult:  # pragma: no cover
            called.append(url)
            return FetchResult(status=200, payload={"jobs": []})

        result = await run_user_scan_tick(
            "u1", db=db, fetcher=_fetch, now=_TICK_NOW
        )
        assert result == TickResult(0, 0, 0, 0, 0)
        # Worker never invoked, no DB writes.
        assert called == []
        assert db.update_calls == []

    @pytest.mark.asyncio
    async def test_only_disabled_rows_short_circuits(self):
        db = _FakeDB([
            _row(id="r1", enabled=False),
            _row(id="r2", enabled=False),
        ])
        result = await run_user_scan_tick(
            "u1", db=db, fetcher=_make_fetcher(), now=_TICK_NOW
        )
        assert result.scanned_count == 0
        assert db.update_calls == []


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_single_company_with_one_posting(self):
        db = _FakeDB([_row(id="r1", company_slug="acme")])
        # The greenhouse plan URL for slug 'acme'.
        url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
        fetcher = _make_fetcher(payload_by_url={url: _gh_payload("Senior Engineer")})

        result = await run_user_scan_tick(
            "u1", db=db, fetcher=fetcher, now=_TICK_NOW
        )

        assert result.scanned_count == 1
        assert result.plans_attempted == 1
        assert result.new_postings_count == 1
        assert result.failure_count == 0
        assert result.marked_scanned_count == 1
        # mark_scanned bumped the row's last_scanned_at.
        assert db.rows["r1"]["last_scanned_at"] == _TICK_NOW.isoformat()
        assert len(db.scan_history_rows) == 1
        history = next(iter(db.scan_history_rows.values()))
        assert history["role_title"] == "Senior Engineer"
        assert history["times_seen"] == 1

    @pytest.mark.asyncio
    async def test_multiple_companies_all_marked(self):
        db = _FakeDB([
            _row(id="r1", company_slug="acme"),
            _row(id="r2", company_slug="globex"),
        ])
        url_acme = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
        url_globex = "https://boards-api.greenhouse.io/v1/boards/globex/jobs?content=true"
        fetcher = _make_fetcher(payload_by_url={
            url_acme: _gh_payload("Eng A"),
            url_globex: _gh_payload("Eng B", "Eng C"),
        })

        result = await run_user_scan_tick(
            "u1", db=db, fetcher=fetcher, now=_TICK_NOW
        )

        assert result.scanned_count == 2
        assert result.new_postings_count == 3
        assert result.failure_count == 0
        # Both rows marked with the SAME tick timestamp.
        ts = _TICK_NOW.isoformat()
        assert db.rows["r1"]["last_scanned_at"] == ts
        assert db.rows["r2"]["last_scanned_at"] == ts


class TestFailureMarksScannedToo:
    @pytest.mark.asyncio
    async def test_permanent_4xx_still_marks_scanned(self):
        # Mark-on-attempt: a 404 company still gets last_scanned_at
        # bumped so it doesn't crowd the front of "stalest first" forever.
        db = _FakeDB([_row(id="r1", company_slug="ghost")])
        url = "https://boards-api.greenhouse.io/v1/boards/ghost/jobs?content=true"
        fetcher = _make_fetcher(status_by_url={url: 404})

        result = await run_user_scan_tick(
            "u1", db=db, fetcher=fetcher, now=_TICK_NOW
        )

        assert result.scanned_count == 1
        assert result.new_postings_count == 0
        assert result.failure_count == 1
        # mark_scanned still ran for the failed row.
        assert result.marked_scanned_count == 1
        assert db.rows["r1"]["last_scanned_at"] == _TICK_NOW.isoformat()

    @pytest.mark.asyncio
    async def test_partial_failure_marks_all(self):
        db = _FakeDB([
            _row(id="r1", company_slug="alive"),
            _row(id="r2", company_slug="dead"),
        ])
        url_alive = "https://boards-api.greenhouse.io/v1/boards/alive/jobs?content=true"
        url_dead = "https://boards-api.greenhouse.io/v1/boards/dead/jobs?content=true"
        fetcher = _make_fetcher(
            payload_by_url={url_alive: _gh_payload("Eng")},
            status_by_url={url_dead: 404},
        )

        result = await run_user_scan_tick(
            "u1", db=db, fetcher=fetcher, now=_TICK_NOW
        )

        assert result.scanned_count == 2
        assert result.new_postings_count == 1
        assert result.failure_count == 1
        assert result.marked_scanned_count == 2


class TestExistingHistory:
    @pytest.mark.asyncio
    async def test_repeat_posting_increments_history_without_counting_new(self):
        payload = _gh_payload("Senior Engineer")
        posting_url = payload["jobs"][0]["absolute_url"]
        db = _FakeDB(
            [_row(id="r1", company_slug="acme")],
            scan_history_rows=[_history_row(times_seen=2, url_canonical=posting_url)],
        )
        url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
        fetcher = _make_fetcher(payload_by_url={url: payload})

        result = await run_user_scan_tick(
            "u1", db=db, fetcher=fetcher, now=_TICK_NOW
        )

        assert result.scanned_count == 1
        assert result.new_postings_count == 0
        history = db.scan_history_rows["history-1"]
        assert history["times_seen"] == 3
        assert history["last_seen"] == _TICK_NOW.isoformat()


class TestOrdering:
    @pytest.mark.asyncio
    async def test_stalest_company_scanned(self):
        # Sanity-check the wiring: the load step orders stalest first,
        # so a never-scanned row precedes a recently-scanned one in
        # the URL the fetcher sees.
        db = _FakeDB([
            _row(id="r1", company_slug="recent",
                 last_scanned_at="2026-05-02T00:00:00+00:00"),
            _row(id="r2", company_slug="never", last_scanned_at=None),
        ])
        seen_urls: list[str] = []

        async def _fetch(url: str) -> FetchResult:
            seen_urls.append(url)
            return FetchResult(status=200, payload={"jobs": []})

        await run_user_scan_tick("u1", db=db, fetcher=_fetch, now=_TICK_NOW)

        # Both URLs hit, but 'never' comes first in the plan list so
        # without concurrency reordering it'd appear first.  We only
        # assert both reached the fetcher (concurrency may interleave).
        assert any("never" in u for u in seen_urls)
        assert any("recent" in u for u in seen_urls)


class TestNowDefault:
    @pytest.mark.asyncio
    async def test_now_defaults_to_utc(self, monkeypatch):
        # Pin ``datetime.now`` so the test isn't time-flaky.
        fixed = datetime(2026, 5, 3, 11, 22, 33, tzinfo=timezone.utc)

        class _FrozenDT(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

        import app.services.portal_scanner_scheduler as mod
        monkeypatch.setattr(mod, "datetime", _FrozenDT)

        db = _FakeDB([_row(id="r1", company_slug="acme")])
        fetcher = _make_fetcher(payload_by_url={
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true": {"jobs": []}
        })

        # No `now=` kwarg.
        await run_user_scan_tick("u1", db=db, fetcher=fetcher)

        assert db.rows["r1"]["last_scanned_at"] == fixed.isoformat()


class TestCrossUserIsolation:
    @pytest.mark.asyncio
    async def test_other_users_rows_untouched(self):
        db = _FakeDB([
            _row(id="r1", user_id="u1", company_slug="mine"),
            _row(id="r2", user_id="u2", company_slug="theirs"),
        ])
        fetcher = _make_fetcher(payload_by_url={
            "https://boards-api.greenhouse.io/v1/boards/mine/jobs?content=true": {"jobs": []}
        })

        result = await run_user_scan_tick(
            "u1", db=db, fetcher=fetcher, now=_TICK_NOW
        )
        assert result.scanned_count == 1
        # Only u1's row was touched.
        assert db.rows["r1"]["last_scanned_at"] == _TICK_NOW.isoformat()
        assert db.rows["r2"]["last_scanned_at"] is None
