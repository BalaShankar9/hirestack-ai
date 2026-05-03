"""Tests for tracked_companies_repo (DB persistence boundary).

Validates load_enabled_for_user + mark_scanned with a small in-memory
fake that mimics the SupabaseDB surface used by the repo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Mapping

import pytest

from app.core.database import TABLES
from app.services.portal_scanner import PROVIDERS, TrackedCompany
from app.services.tracked_companies_repo import (
    load_enabled_for_user,
    mark_scanned,
)


# ── In-memory DB fake ────────────────────────────────────────────────


class _FakeDB:
    """Mimics the slice of SupabaseDB that tracked_companies_repo uses.

    Only ``query()`` (with ``filters`` ==/in support) and ``update()``
    are needed.  Rows are stored in a dict keyed by id so update can
    do an in-place merge.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        for r in rows or []:
            self.rows[r["id"]] = dict(r)
        self.update_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_update_for_id: str | None = None

    async def query(
        self,
        table: str,
        filters: list[tuple] | None = None,
        order_by: str | None = None,
        order_direction: str = "DESCENDING",
        limit: int | None = None,
        offset: int | None = None,
    ) -> List[Mapping[str, Any]]:
        assert table == TABLES["tracked_companies"]
        out = list(self.rows.values())
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
        assert table == TABLES["tracked_companies"]
        self.update_calls.append((table, doc_id, dict(data)))
        if doc_id == self.fail_update_for_id:
            raise RuntimeError("simulated update failure")
        if doc_id not in self.rows:
            return False
        self.rows[doc_id].update(data)
        return True


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
