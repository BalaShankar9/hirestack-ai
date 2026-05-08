"""Route tests for ``backend/app/api/routes/job_sync.py``.

Pins the thin HTTP contract around alert CRUD so frontend helpers stay
aligned with the backend route surface.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api.routes import job_sync as js_route


_FAKE_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "u@example.com",
}


class _FakeService:
    def __init__(self) -> None:
        self.create_alert = AsyncMock(return_value={"id": "alert-1"})
        self.get_alerts = AsyncMock(return_value=[])
        self.delete_alert = AsyncMock(return_value=True)
        self.get_matches = AsyncMock(return_value=[])
        self.update_match_status = AsyncMock(return_value=True)


def _build_client(service: _FakeService) -> TestClient:
    app = FastAPI()
    app.state.limiter = js_route.limiter
    app.include_router(js_route.router, prefix="/api/job-sync")
    app.dependency_overrides[api_deps.get_current_user] = lambda: _FAKE_USER
    js_route.get_job_sync_service = lambda: service
    try:
        js_route.limiter.reset()
    except Exception:
        pass
    return TestClient(app)


def test_create_alert_posts_to_alert_service_with_salary_min():
    service = _FakeService()
    client = _build_client(service)

    resp = client.post(
        "/api/job-sync/alerts",
        json={
            "keywords": ["react", "typescript"],
            "location": "Remote",
            "salary_min": 120000,
        },
    )

    assert resp.status_code == 200
    kwargs = service.create_alert.await_args.kwargs
    assert kwargs["user_id"] == _FAKE_USER["id"]
    assert kwargs["keywords"] == ["react", "typescript"]
    assert kwargs["location"] == "Remote"
    assert kwargs["salary_min"] == 120000


def test_delete_alert_calls_service_and_returns_deleted_payload():
    service = _FakeService()
    client = _build_client(service)
    alert_id = "00000000-0000-0000-0000-000000000222"

    resp = client.delete(f"/api/job-sync/alerts/{alert_id}")

    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "id": alert_id}
    kwargs = service.delete_alert.await_args.kwargs
    assert kwargs == {"alert_id": alert_id, "user_id": _FAKE_USER["id"]}


def test_delete_alert_returns_404_when_service_reports_missing():
    service = _FakeService()
    service.delete_alert = AsyncMock(return_value=False)
    client = _build_client(service)

    resp = client.delete(
        "/api/job-sync/alerts/00000000-0000-0000-0000-000000000333"
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Alert not found"


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123"])
def test_delete_alert_validates_uuid(bad_id: str):
    service = _FakeService()
    client = _build_client(service)

    resp = client.delete(f"/api/job-sync/alerts/{bad_id}")

    assert resp.status_code == 422
    assert "Invalid alert_id" in resp.json()["detail"]