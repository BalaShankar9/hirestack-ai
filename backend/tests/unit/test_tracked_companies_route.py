"""Tests for ``backend/app/api/routes/tracked_companies.py`` (B2.api).

Black-box tests through TestClient — exercises the full FastAPI stack
(auth dep override, body validation, 422 mapping, db-DI override). The
DB is a fake that mimics ``SupabaseDB`` for the surface we use.

What's NOT tested here:
    * The DB CHECK constraints themselves (those are enforced by
      Postgres; ``test_tracked_companies_migration.py`` pins the SQL).
    * The pure-fn validation rules (those are pinned in
      ``test_tracked_companies_core.py``); we only verify the route
      maps ValidationError to a clean 422.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api.routes import tracked_companies as tc_route
from app.api.routes.tracked_companies import get_db_dep


_FAKE_USER = {"id": "user-1", "email": "u@example.com"}
_OTHER_USER = {"id": "user-2", "email": "other@example.com"}


class _FakeDB:
    """Minimal in-memory fake of the SupabaseDB surface this route uses.

    Stores rows by id, supports user-scoped query, mimics duplicate-key
    error on UNIQUE (user_id, provider, company_slug).
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self._counter = 0
        self.simulate_unique_violation_on_create = False

    def _next_id(self) -> str:
        self._counter += 1
        return f"00000000-0000-0000-0000-{self._counter:012d}"

    async def create(self, table, data, doc_id=None):
        if self.simulate_unique_violation_on_create:
            raise Exception(
                "duplicate key value violates unique constraint "
                "tracked_companies_user_provider_slug_key (sqlstate 23505)"
            )
        # Soft-emulate UNIQUE (user_id, provider, company_slug).
        for row in self.rows.values():
            if (
                row["user_id"] == data["user_id"]
                and row["provider"] == data["provider"]
                and row["company_slug"] == data["company_slug"]
            ):
                raise Exception(
                    "duplicate key value violates unique constraint"
                )
        new_id = doc_id or self._next_id()
        stored = {**data, "id": new_id}
        # Mirror DB defaults the migration sets.
        stored.setdefault("enabled", True)
        stored.setdefault("created_at", "2026-05-07T00:00:00Z")
        stored.setdefault("updated_at", "2026-05-07T00:00:00Z")
        self.rows[new_id] = stored
        return new_id

    async def get(self, table, doc_id):
        return self.rows.get(doc_id)

    async def update(self, table, doc_id, data):
        if doc_id not in self.rows:
            return False
        self.rows[doc_id] = {**self.rows[doc_id], **data}
        return True

    async def delete(self, table, doc_id):
        return self.rows.pop(doc_id, None) is not None

    async def query(
        self,
        table,
        filters=None,
        order_by=None,
        order_direction="DESCENDING",
        limit=None,
        offset=None,
    ):
        out = list(self.rows.values())
        for col, op, val in filters or []:
            if op == "==":
                out = [r for r in out if r.get(col) == val]
        if order_by:
            out.sort(
                key=lambda r: r.get(order_by, ""),
                reverse=(order_direction == "DESCENDING"),
            )
        return out


def _build_app(db: _FakeDB, user: dict = _FAKE_USER) -> FastAPI:
    app = FastAPI()
    app.state.limiter = tc_route.limiter
    app.include_router(tc_route.router, prefix="/api")
    app.dependency_overrides[api_deps.get_current_user] = lambda: user
    app.dependency_overrides[get_db_dep] = lambda: db
    return app


@pytest.fixture()
def client_factory():
    def _factory(db: _FakeDB | None = None, user: dict = _FAKE_USER) -> TestClient:
        try:
            tc_route.limiter.reset()
        except Exception:
            pass
        return TestClient(_build_app(db or _FakeDB(), user))

    return _factory


# ── POST /tracked-companies ─────────────────────────────────────────


class TestCreateRoute:
    def test_create_greenhouse_happy_path(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "greenhouse",
                "company_slug": "stripe",
                "display_name": "Stripe",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["provider"] == "greenhouse"
        assert body["company_slug"] == "stripe"
        assert body["display_name"] == "Stripe"
        assert body["user_id"] == _FAKE_USER["id"]
        assert body["workday_tenant"] is None
        assert "id" in body

    def test_create_workday_with_tenant(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "workday",
                "company_slug": "acme",
                "display_name": "Acme",
                "workday_tenant": "acme.wd5",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["workday_tenant"] == "acme.wd5"

    def test_create_workday_without_tenant_422(self, client_factory) -> None:
        client = client_factory()
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "workday",
                "company_slug": "acme",
                "display_name": "Acme",
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["field"] == "workday_tenant"

    def test_create_unknown_provider_422(self, client_factory) -> None:
        client = client_factory()
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "bamboohr",
                "company_slug": "acme",
                "display_name": "Acme",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "provider"

    def test_create_invalid_slug_422(self, client_factory) -> None:
        client = client_factory()
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "greenhouse",
                "company_slug": "Bad_Slug!",
                "display_name": "X",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "company_slug"

    def test_create_duplicate_returns_409(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        payload = {
            "provider": "greenhouse",
            "company_slug": "stripe",
            "display_name": "Stripe",
        }
        first = client.post("/api/tracked-companies", json=payload)
        assert first.status_code == 201
        second = client.post("/api/tracked-companies", json=payload)
        assert second.status_code == 409
        assert second.json()["detail"]["field"] == "company_slug"

    def test_create_db_unique_violation_returns_409(
        self, client_factory
    ) -> None:
        # Race condition path: pre-check passes, INSERT trips the
        # DB-level UNIQUE index.
        db = _FakeDB()
        db.simulate_unique_violation_on_create = True
        client = client_factory(db)
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "lever",
                "company_slug": "github",
                "display_name": "GitHub",
            },
        )
        assert resp.status_code == 409

    def test_create_persists_org_id_when_present(self, client_factory) -> None:
        db = _FakeDB()
        org_user = {**_FAKE_USER, "org_id": "org-abc"}
        client = client_factory(db, user=org_user)
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "lever",
                "company_slug": "github",
                "display_name": "GitHub",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["org_id"] == "org-abc"

    def test_create_normalizes_inputs(self, client_factory) -> None:
        # Pure-fn layer normalizes — verify the route preserves the
        # normalized values in the persisted row.
        db = _FakeDB()
        client = client_factory(db)
        resp = client.post(
            "/api/tracked-companies",
            json={
                "provider": "GREENHOUSE",
                "company_slug": "  Stripe  ",
                "display_name": "  Stripe   Inc.  ",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["provider"] == "greenhouse"
        assert body["company_slug"] == "stripe"
        assert body["display_name"] == "Stripe Inc."


# ── GET /tracked-companies ──────────────────────────────────────────


class TestListRoute:
    def test_empty_list(self, client_factory) -> None:
        client = client_factory()
        resp = client.get("/api/tracked-companies")
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "count": 0}

    def test_lists_only_callers_rows(self, client_factory) -> None:
        db = _FakeDB()
        # Seed two rows: one for FAKE_USER, one for OTHER_USER.
        client_a = client_factory(db, user=_FAKE_USER)
        client_b = client_factory(db, user=_OTHER_USER)
        client_a.post(
            "/api/tracked-companies",
            json={
                "provider": "greenhouse",
                "company_slug": "stripe",
                "display_name": "Stripe",
            },
        )
        client_b.post(
            "/api/tracked-companies",
            json={
                "provider": "lever",
                "company_slug": "github",
                "display_name": "GitHub",
            },
        )
        resp = client_a.get("/api/tracked-companies")
        body = resp.json()
        assert body["count"] == 1
        assert body["items"][0]["company_slug"] == "stripe"


# ── PATCH /tracked-companies/{id} ───────────────────────────────────


class TestPatchRoute:
    def _seed(self, client_factory, **overrides):
        db = _FakeDB()
        client = client_factory(db)
        payload = {
            "provider": "greenhouse",
            "company_slug": "stripe",
            "display_name": "Stripe",
        }
        payload.update(overrides)
        resp = client.post("/api/tracked-companies", json=payload)
        return client, db, resp.json()["id"]

    def test_patch_display_name(self, client_factory) -> None:
        client, _db, row_id = self._seed(client_factory)
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"display_name": "Stripe Inc."},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Stripe Inc."

    def test_patch_normalizes_display_name(self, client_factory) -> None:
        client, _db, row_id = self._seed(client_factory)
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"display_name": "  Stripe   Inc.  "},
        )
        assert resp.json()["display_name"] == "Stripe Inc."

    def test_patch_blank_display_name_422(self, client_factory) -> None:
        client, _db, row_id = self._seed(client_factory)
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"display_name": "  "},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "display_name"

    def test_patch_enabled_toggle(self, client_factory) -> None:
        client, _db, row_id = self._seed(client_factory)
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"enabled": False},
        )
        assert resp.json()["enabled"] is False

    def test_patch_careers_url_blank_becomes_null(self, client_factory) -> None:
        client, _db, row_id = self._seed(
            client_factory, careers_url="https://stripe.com"
        )
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"careers_url": "   "},
        )
        assert resp.json()["careers_url"] is None

    def test_patch_careers_url_invalid_422(self, client_factory) -> None:
        client, _db, row_id = self._seed(client_factory)
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"careers_url": "stripe.com/careers"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "careers_url"

    def test_patch_workday_tenant_on_non_workday_422(
        self, client_factory
    ) -> None:
        client, _db, row_id = self._seed(client_factory)
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"workday_tenant": "stripe.wd5"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "workday_tenant"

    def test_patch_workday_tenant_on_workday(self, client_factory) -> None:
        client, _db, row_id = self._seed(
            client_factory,
            provider="workday",
            company_slug="acme",
            display_name="Acme",
            workday_tenant="acme.wd5",
        )
        resp = client.patch(
            f"/api/tracked-companies/{row_id}",
            json={"workday_tenant": "acme.wd6"},
        )
        assert resp.status_code == 200
        assert resp.json()["workday_tenant"] == "acme.wd6"

    def test_patch_empty_body_is_noop(self, client_factory) -> None:
        client, _db, row_id = self._seed(client_factory)
        resp = client.patch(f"/api/tracked-companies/{row_id}", json={})
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Stripe"  # unchanged

    def test_patch_other_users_row_404(self, client_factory) -> None:
        # Seed as USER A, then PATCH as USER B → expect 404 (don't leak
        # row existence).
        db = _FakeDB()
        a = client_factory(db, user=_FAKE_USER)
        b = client_factory(db, user=_OTHER_USER)
        seed = a.post(
            "/api/tracked-companies",
            json={
                "provider": "greenhouse",
                "company_slug": "stripe",
                "display_name": "Stripe",
            },
        )
        row_id = seed.json()["id"]
        resp = b.patch(
            f"/api/tracked-companies/{row_id}",
            json={"display_name": "Stripe Inc."},
        )
        assert resp.status_code == 404

    def test_patch_unknown_id_404(self, client_factory) -> None:
        client = client_factory()
        resp = client.patch(
            "/api/tracked-companies/00000000-0000-0000-0000-000000000999",
            json={"display_name": "X"},
        )
        assert resp.status_code == 404


# ── DELETE /tracked-companies/{id} ──────────────────────────────────


class TestDeleteRoute:
    def test_delete_owned_row(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        seed = client.post(
            "/api/tracked-companies",
            json={
                "provider": "greenhouse",
                "company_slug": "stripe",
                "display_name": "Stripe",
            },
        )
        row_id = seed.json()["id"]
        resp = client.delete(f"/api/tracked-companies/{row_id}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "id": row_id}
        # Subsequent get returns 404
        resp2 = client.delete(f"/api/tracked-companies/{row_id}")
        assert resp2.status_code == 404

    def test_delete_other_users_row_404(self, client_factory) -> None:
        db = _FakeDB()
        a = client_factory(db, user=_FAKE_USER)
        b = client_factory(db, user=_OTHER_USER)
        seed = a.post(
            "/api/tracked-companies",
            json={
                "provider": "greenhouse",
                "company_slug": "stripe",
                "display_name": "Stripe",
            },
        )
        resp = b.delete(f"/api/tracked-companies/{seed.json()['id']}")
        assert resp.status_code == 404
        # Row is still present when the rightful owner queries.
        listing = a.get("/api/tracked-companies")
        assert listing.json()["count"] == 1

    def test_delete_unknown_id_404(self, client_factory) -> None:
        client = client_factory()
        resp = client.delete(
            "/api/tracked-companies/00000000-0000-0000-0000-000000000999"
        )
        assert resp.status_code == 404
