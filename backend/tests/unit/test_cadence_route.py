from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api.routes import cadence as cadence_route


_FAKE_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "u@example.com",
    "full_name": "Ada Lovelace",
}


class _FakeDB:
    async def query(self, table, filters=None, order_by=None, order_direction="DESCENDING", limit=None, offset=None):
        if table == "applications":
            return [
                {
                    "id": "app-1",
                    "user_id": _FAKE_USER["id"],
                    "status": "submitted",
                    "submitted_at": "2026-05-06T12:00:00+00:00",
                    "company_name": "Acme",
                    "job_title": "Engineer",
                }
            ]
        if table == "application_followups":
            return []
        return []


def _build_client(db: _FakeDB) -> TestClient:
    app = FastAPI()
    app.state.limiter = cadence_route.limiter
    app.include_router(cadence_route.router, prefix="/api/cadence")
    app.dependency_overrides[api_deps.get_current_user] = lambda: _FAKE_USER
    app.dependency_overrides[cadence_route.get_db_dep] = lambda: db
    try:
        cadence_route.limiter.reset()
    except Exception:
        pass
    return TestClient(app)


def test_cadence_today_returns_bucketed_payload() -> None:
    client = _build_client(_FakeDB())

    resp = client.get("/api/cadence/today")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body["buckets"].keys()) == {"urgent", "overdue", "waiting", "cold"}
    assert body["metadata"]["total_tracked"] == 1
    assert body["buckets"]["waiting"][0]["company"] == "Acme"