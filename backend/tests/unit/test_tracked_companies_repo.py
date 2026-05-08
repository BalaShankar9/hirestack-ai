"""Tests for tracked_companies_repo (DB persistence boundary).

Validates load_enabled_for_user + mark_scanned with a small in-memory
fake that mimics the SupabaseDB surface used by the repo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Mapping

import pytest

from app.core.database import TABLES
from app.services.portal_scanner import JobPosting, PROVIDERS, TrackedCompany
from app.services.tracked_companies_repo import (
    WatchlistEntry,
    load_enabled_for_user,
    load_watchlist_for_user,
    mark_scanned,
    persist_scan_postings,
)


# ── In-memory DB fake ────────────────────────────────────────────────


class _FakeDB:
    """Mimics the slice of SupabaseDB that tracked_companies_repo uses.

    Stores tracked companies and scan-history rows separately so the
    repo helpers can exercise both tables without a real Supabase.
    """

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
        self.fail_update_for_id: str | None = None
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
            else:
                raise AssertionError(f"unhandled op {op!r}")
        # Repo sorts in Python, so DB-side order doesn't matter.
        return out

    async def update(self, table: str, doc_id: str, data: dict[str, Any]) -> bool:
        self.update_calls.append((table, doc_id, dict(data)))
        if doc_id == self.fail_update_for_id:
            raise RuntimeError("simulated update failure")
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


def _posting(
    *,
    external_id: str = "job-1",
    title: str = "Senior Engineer",
    company_slug: str = "acme",
    url: str = "https://boards.greenhouse.io/acme/jobs/1",
) -> JobPosting:
    return JobPosting(
        provider="greenhouse",
        company_slug=company_slug,
        external_id=external_id,
        title=title,
        location="Remote",
        url=url,
        url_canonical=url,
        posted_at=None,
        department=None,
    )


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
    display_name: str = "Acme",
) -> dict[str, Any]:
    return {
        "id": id,
        "user_id": user_id,
        "provider": provider,
        "company_slug": company_slug,
        "workday_tenant": workday_tenant,
        "enabled": enabled,
        "last_scanned_at": last_scanned_at,
        "display_name": display_name,
    }


# ── load_enabled_for_user ────────────────────────────────────────────


class TestLoadEnabled:
    @pytest.mark.asyncio
    async def test_empty_user_returns_empty_list(self):
        db = _FakeDB([])
        result = await load_enabled_for_user("u1", db)
        assert result == []

    @pytest.mark.asyncio
    async def test_other_user_rows_excluded(self):
        db = _FakeDB([
            _row(id="r1", user_id="u1", company_slug="acme"),
            _row(id="r2", user_id="u2", company_slug="globex"),
        ])
        result = await load_enabled_for_user("u1", db)
        assert len(result) == 1
        assert result[0].company_slug == "acme"

    @pytest.mark.asyncio
    async def test_disabled_rows_excluded(self):
        db = _FakeDB([
            _row(id="r1", company_slug="acme", enabled=True),
            _row(id="r2", company_slug="globex", enabled=False),
        ])
        result = await load_enabled_for_user("u1", db)
        assert [c.company_slug for c in result] == ["acme"]

    @pytest.mark.asyncio
    async def test_returns_tracked_company_dataclass_instances(self):
        db = _FakeDB([_row(id="r1")])
        result = await load_enabled_for_user("u1", db)
        assert isinstance(result[0], TrackedCompany)

    @pytest.mark.asyncio
    async def test_workday_tenant_propagated(self):
        db = _FakeDB([
            _row(
                id="r1",
                provider="workday",
                company_slug="acme",
                workday_tenant="acme.wd5",
            ),
        ])
        result = await load_enabled_for_user("u1", db)
        assert result[0].provider == "workday"
        assert result[0].workday_tenant == "acme.wd5"

    @pytest.mark.asyncio
    async def test_non_workday_tenant_is_none(self):
        db = _FakeDB([_row(id="r1", provider="greenhouse")])
        result = await load_enabled_for_user("u1", db)
        assert result[0].workday_tenant is None

    @pytest.mark.asyncio
    async def test_unknown_provider_dropped_not_raised(self):
        # Future-proofing: row with provider not in PROVIDERS gets
        # silently dropped, scheduler still scans the rest.
        db = _FakeDB([
            _row(id="r1", provider="greenhouse", company_slug="acme"),
            _row(id="r2", provider="future_ats", company_slug="x"),
        ])
        result = await load_enabled_for_user("u1", db)
        assert [c.company_slug for c in result] == ["acme"]

    @pytest.mark.asyncio
    async def test_provides_runs_match_PROVIDERS_constant(self):
        # All 6 providers can be loaded.
        rows = [
            _row(
                id=f"r{i}",
                provider=p,
                company_slug=f"co{i}",
                workday_tenant="acme.wd5" if p == "workday" else None,
            )
            for i, p in enumerate(PROVIDERS)
        ]
        db = _FakeDB(rows)
        result = await load_enabled_for_user("u1", db)
        assert {c.provider for c in result} == set(PROVIDERS)


class TestStalestFirstOrdering:
    @pytest.mark.asyncio
    async def test_never_scanned_rows_come_first(self):
        db = _FakeDB([
            _row(id="r1", company_slug="scanned", last_scanned_at="2026-04-01T00:00:00+00:00"),
            _row(id="r2", company_slug="never", last_scanned_at=None),
        ])
        result = await load_enabled_for_user("u1", db)
        assert [c.company_slug for c in result] == ["never", "scanned"]

    @pytest.mark.asyncio
    async def test_oldest_scanned_before_newest_scanned(self):
        db = _FakeDB([
            _row(id="r1", company_slug="newer", last_scanned_at="2026-04-30T12:00:00+00:00"),
            _row(id="r2", company_slug="older", last_scanned_at="2026-04-01T12:00:00+00:00"),
        ])
        result = await load_enabled_for_user("u1", db)
        assert [c.company_slug for c in result] == ["older", "newer"]

    @pytest.mark.asyncio
    async def test_multiple_never_scanned_then_oldest_scanned(self):
        db = _FakeDB([
            _row(id="r1", company_slug="b_scanned_old", last_scanned_at="2026-04-01T00:00:00+00:00"),
            _row(id="r2", company_slug="a_never", last_scanned_at=None),
            _row(id="r3", company_slug="d_scanned_new", last_scanned_at="2026-04-30T00:00:00+00:00"),
            _row(id="r4", company_slug="c_never_too", last_scanned_at=None),
        ])
        result = await load_enabled_for_user("u1", db)
        slugs = [c.company_slug for c in result]
        # Both never-scanned come first (relative order between them
        # is implementation-defined but both must precede any scanned).
        assert set(slugs[:2]) == {"a_never", "c_never_too"}
        assert slugs[2:] == ["b_scanned_old", "d_scanned_new"]


# ── load_watchlist_for_user (sister fn returning ids + companies) ────


class TestLoadWatchlist:
    @pytest.mark.asyncio
    async def test_returns_watchlist_entries_with_ids(self):
        db = _FakeDB([_row(id="r1", company_slug="acme")])
        result = await load_watchlist_for_user("u1", db)
        assert len(result) == 1
        assert isinstance(result[0], WatchlistEntry)
        assert result[0].id == "r1"
        assert isinstance(result[0].company, TrackedCompany)
        assert result[0].company.company_slug == "acme"

    @pytest.mark.asyncio
    async def test_empty_user_returns_empty(self):
        db = _FakeDB([])
        result = await load_watchlist_for_user("u1", db)
        assert result == []

    @pytest.mark.asyncio
    async def test_disabled_excluded(self):
        db = _FakeDB([
            _row(id="r1", company_slug="on", enabled=True),
            _row(id="r2", company_slug="off", enabled=False),
        ])
        result = await load_watchlist_for_user("u1", db)
        assert [(e.id, e.company.company_slug) for e in result] == [("r1", "on")]

    @pytest.mark.asyncio
    async def test_stalest_first_ordering_preserved(self):
        db = _FakeDB([
            _row(id="r1", company_slug="scanned", last_scanned_at="2026-04-01T00:00:00+00:00"),
            _row(id="r2", company_slug="never", last_scanned_at=None),
        ])
        result = await load_watchlist_for_user("u1", db)
        assert [e.id for e in result] == ["r2", "r1"]

    @pytest.mark.asyncio
    async def test_unknown_provider_dropped(self):
        db = _FakeDB([
            _row(id="r1", provider="future_ats", company_slug="x"),
            _row(id="r2", provider="lever", company_slug="ok"),
        ])
        result = await load_watchlist_for_user("u1", db)
        assert [e.id for e in result] == ["r2"]


class TestPersistScanPostings:
    @pytest.mark.asyncio
    async def test_inserts_new_rows_and_returns_inserted_count(self):
        db = _FakeDB()
        inserted = await persist_scan_postings(
            db,
            [_posting()],
            scanned_at=datetime(2026, 5, 3, 9, 0, 0, tzinfo=timezone.utc),
        )

        assert inserted == 1
        assert len(db.create_calls) == 1
        row = next(iter(db.scan_history_rows.values()))
        assert row["company_slug"] == "acme"
        assert row["role_title"] == "Senior Engineer"
        assert row["times_seen"] == 1

    @pytest.mark.asyncio
    async def test_existing_rows_increment_last_seen_and_times_seen(self):
        db = _FakeDB(
            scan_history_rows=[_history_row(times_seen=2)],
        )
        inserted = await persist_scan_postings(
            db,
            [_posting()],
            scanned_at=datetime(2026, 5, 3, 9, 0, 0, tzinfo=timezone.utc),
        )

        assert inserted == 0
        row = db.scan_history_rows["history-1"]
        assert row["times_seen"] == 3
        assert row["last_seen"] == "2026-05-03T09:00:00+00:00"

    @pytest.mark.asyncio
    async def test_duplicate_canonicals_only_persist_once(self):
        db = _FakeDB()
        inserted = await persist_scan_postings(
            db,
            [_posting(), _posting(external_id="job-2")],
            scanned_at=datetime(2026, 5, 3, 9, 0, 0, tzinfo=timezone.utc),
        )

        assert inserted == 1
        assert len(db.scan_history_rows) == 1

    @pytest.mark.asyncio
    async def test_cross_user_isolation(self):
        db = _FakeDB([
            _row(id="r1", user_id="u1"),
            _row(id="r2", user_id="u2"),
        ])
        result = await load_watchlist_for_user("u1", db)
        assert [e.id for e in result] == ["r1"]


# ── mark_scanned ─────────────────────────────────────────────────────


_NOW = datetime(2026, 5, 3, 12, 30, 0, tzinfo=timezone.utc)


class TestMarkScanned:
    @pytest.mark.asyncio
    async def test_updates_single_row(self):
        db = _FakeDB([_row(id="r1", last_scanned_at=None)])
        n = await mark_scanned(db, ["r1"], scanned_at=_NOW)
        assert n == 1
        assert db.rows["r1"]["last_scanned_at"] == _NOW.isoformat()

    @pytest.mark.asyncio
    async def test_updates_multiple_rows_with_same_timestamp(self):
        db = _FakeDB([
            _row(id="r1"),
            _row(id="r2"),
            _row(id="r3"),
        ])
        n = await mark_scanned(db, ["r1", "r2", "r3"], scanned_at=_NOW)
        assert n == 3
        # Every row gets the SAME timestamp — operator-friendly.
        assert {db.rows[i]["last_scanned_at"] for i in ["r1", "r2", "r3"]} == {
            _NOW.isoformat()
        }

    @pytest.mark.asyncio
    async def test_empty_ids_is_noop(self):
        db = _FakeDB([_row(id="r1")])
        n = await mark_scanned(db, [], scanned_at=_NOW)
        assert n == 0
        assert db.update_calls == []
        # Untouched.
        assert db.rows["r1"]["last_scanned_at"] is None

    @pytest.mark.asyncio
    async def test_missing_id_silently_contributes_zero(self):
        # Row got deleted between load and mark — repo doesn't raise.
        db = _FakeDB([_row(id="r1")])
        n = await mark_scanned(db, ["r1", "r_gone"], scanned_at=_NOW)
        assert n == 1
        # Both attempted.
        assert len(db.update_calls) == 2
        # Existing row was actually updated.
        assert db.rows["r1"]["last_scanned_at"] == _NOW.isoformat()

    @pytest.mark.asyncio
    async def test_db_failure_propagates(self):
        # A real DB exception (not a missing row) should propagate so
        # the scheduler can log + retry — silent swallow would mask
        # connectivity issues.
        db = _FakeDB([_row(id="r1"), _row(id="r2")])
        db.fail_update_for_id = "r2"
        with pytest.raises(RuntimeError, match="simulated update failure"):
            await mark_scanned(db, ["r1", "r2", "r3"], scanned_at=_NOW)
        # Sequential semantics: r1 was marked before r2 raised.
        assert db.rows["r1"]["last_scanned_at"] == _NOW.isoformat()

    @pytest.mark.asyncio
    async def test_iterable_input_accepted(self):
        # Generator, not just list — repo signature is Iterable[str].
        db = _FakeDB([_row(id=f"r{i}") for i in range(3)])
        n = await mark_scanned(
            db,
            (f"r{i}" for i in range(3)),
            scanned_at=_NOW,
        )
        assert n == 3

    @pytest.mark.asyncio
    async def test_naive_datetime_serialized_without_tz(self):
        # Caller passing a naive datetime: we don't crash, we
        # serialize as-is.  Tests document the contract.
        naive = datetime(2026, 5, 3, 12, 30, 0)
        db = _FakeDB([_row(id="r1")])
        n = await mark_scanned(db, ["r1"], scanned_at=naive)
        assert n == 1
        assert db.rows["r1"]["last_scanned_at"] == "2026-05-03T12:30:00"

    @pytest.mark.asyncio
    async def test_only_last_scanned_at_is_updated(self):
        # Make sure we don't accidentally clobber other columns.
        db = _FakeDB([
            _row(
                id="r1",
                display_name="Acme Inc",
                enabled=True,
                last_scanned_at=None,
            ),
        ])
        await mark_scanned(db, ["r1"], scanned_at=_NOW)
        # display_name + enabled untouched.
        assert db.rows["r1"]["display_name"] == "Acme Inc"
        assert db.rows["r1"]["enabled"] is True
        # update payload was scoped to one field.
        assert db.update_calls[0][2] == {"last_scanned_at": _NOW.isoformat()}
