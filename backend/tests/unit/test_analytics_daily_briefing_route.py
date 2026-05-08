from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api.routes import analytics as analytics_route


_FAKE_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "ada@example.com",
    "full_name": "Ada Lovelace",
}


def _build_client() -> TestClient:
    app = FastAPI()
    app.state.limiter = analytics_route.limiter
    app.include_router(analytics_route.router, prefix="/api/analytics")
    app.dependency_overrides[api_deps.get_current_user] = lambda: _FAKE_USER
    try:
        analytics_route.limiter.reset()
    except Exception:
        pass
    return TestClient(app)


def test_daily_briefing_prefers_morning_brief_preview(monkeypatch) -> None:
    async def _fake_preview(self, user_id: str, *, user_context=None, now=None):
        return {
            "source": "morning_brief",
            "is_empty": False,
            "subject": "2026-05-07: 1 follow-up",
            "insight": "Send the first follow-up before lunch.",
            "summary": "1 follow-up due",
            "body_text": "Morning, Ada.",
            "body_html": "<p>Morning, Ada.</p>",
            "section_counts": {"beats": 1, "jobs": 0, "stale": 0, "wins": 0},
            "nudge": "Send the first follow-up before lunch.",
            "action_label": "Review cadence",
            "action_href": "/dashboard",
        }

    monkeypatch.setattr(
        analytics_route.MorningBriefPreviewService,
        "build_preview",
        _fake_preview,
    )

    client = _build_client()
    resp = client.get("/api/analytics/daily-briefing")

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "morning_brief"
    assert body["action_label"] == "Review cadence"
    assert body["insight"] == "Send the first follow-up before lunch."