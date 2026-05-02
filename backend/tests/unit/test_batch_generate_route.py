"""Tests for backend/app/api/routes/batch_generate.py (B0.api)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api.routes import batch_generate as batch_route
from app.api.routes.batch_generate import _serialize_plan
from app.services.batch_evaluator import (
    MAX_URLS,
    MIN_FIT_SCORE_CEIL,
    MIN_FIT_SCORE_FLOOR,
    plan_batch,
)


# ── _serialize_plan ──────────────────────────────────────────────────


class TestSerializePlan:
    def test_empty_plan_serializes(self) -> None:
        plan = plan_batch([])
        out = _serialize_plan(plan)
        assert out["accepted"] == []
        assert out["rejected"] == []
        assert out["summary"]["accepted_count"] == 0
        assert out["summary"]["rejected_count"] == 0
        assert out["summary"]["max_urls"] == MAX_URLS
        assert out["summary"]["is_empty"] is True

    def test_accepted_entry_shape(self) -> None:
        plan = plan_batch(["https://boards.greenhouse.io/acme/jobs/101"])
        out = _serialize_plan(plan)
        assert out["summary"]["accepted_count"] == 1
        entry = out["accepted"][0]
        assert "raw_url" in entry
        assert "canonical_url" in entry
        assert "ats_key" in entry
        # ats_key is either None or a 3-list (asdict turns the tuple into a list).
        assert entry["ats_key"] is None or len(entry["ats_key"]) == 3

    def test_rejected_entry_shape(self) -> None:
        plan = plan_batch(["", "not-a-url", "https://example.com/x"])
        out = _serialize_plan(plan)
        reasons = {r["reason"] for r in out["rejected"]}
        # "" → empty, "not-a-url" → invalid_url
        assert "empty" in reasons
        assert "invalid_url" in reasons

    def test_duplicate_marked(self) -> None:
        u = "https://boards.greenhouse.io/acme/jobs/101"
        plan = plan_batch([u, u])
        out = _serialize_plan(plan)
        assert out["summary"]["accepted_count"] == 1
        assert out["summary"]["rejected_count"] == 1
        assert out["rejected"][0]["reason"] == "duplicate"

    def test_over_cap_marked(self) -> None:
        urls = [f"https://example.com/job/{i}" for i in range(MAX_URLS + 3)]
        plan = plan_batch(urls)
        out = _serialize_plan(plan)
        # First MAX_URLS accepted, last 3 rejected as over_cap.
        assert out["summary"]["accepted_count"] == MAX_URLS
        over = [r for r in out["rejected"] if r["reason"] == "over_cap"]
        assert len(over) == 3


# ── Route integration ────────────────────────────────────────────────


_FAKE_USER = {"id": "user-1", "email": "u@example.com"}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = batch_route.limiter
    app.include_router(batch_route.router, prefix="/api")
    app.dependency_overrides[api_deps.get_current_user] = lambda: _FAKE_USER
    return app


@pytest.fixture()
def client() -> TestClient:
    try:
        batch_route.limiter.reset()
    except Exception:
        pass
    return TestClient(_build_app())


class TestPlanBatchRoute:
    def test_empty_payload_returns_empty_plan(self, client: TestClient) -> None:
        resp = client.post("/api/generate/batch/plan", json={"urls": []})
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"]["is_empty"] is True
        assert body["accepted"] == []
        assert body["rejected"] == []
        assert body["min_fit_score"] == MIN_FIT_SCORE_FLOOR

    def test_accepts_valid_urls(self, client: TestClient) -> None:
        resp = client.post("/api/generate/batch/plan", json={
            "urls": [
                "https://boards.greenhouse.io/acme/jobs/101",
                "https://jobs.lever.co/foo/abc-123",
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"]["accepted_count"] == 2
        assert body["summary"]["rejected_count"] == 0

    def test_mixed_valid_invalid(self, client: TestClient) -> None:
        resp = client.post("/api/generate/batch/plan", json={
            "urls": [
                "https://boards.greenhouse.io/acme/jobs/101",
                "",
                "ftp://nope",
                "https://boards.greenhouse.io/acme/jobs/101",  # dup
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"]["accepted_count"] == 1
        assert body["summary"]["rejected_count"] == 3
        reasons = sorted(r["reason"] for r in body["rejected"])
        assert reasons == ["duplicate", "empty", "invalid_url"]

    def test_min_fit_score_echoed(self, client: TestClient) -> None:
        resp = client.post("/api/generate/batch/plan", json={
            "urls": ["https://boards.greenhouse.io/acme/jobs/101"],
            "min_fit_score": 3.5,
        })
        assert resp.status_code == 200
        assert resp.json()["min_fit_score"] == 3.5

    def test_min_fit_score_out_of_range_rejected(self, client: TestClient) -> None:
        # Pydantic ge/le validation kicks in.
        resp = client.post("/api/generate/batch/plan", json={
            "urls": [],
            "min_fit_score": MIN_FIT_SCORE_CEIL + 1,
        })
        assert resp.status_code == 422

        resp2 = client.post("/api/generate/batch/plan", json={
            "urls": [],
            "min_fit_score": MIN_FIT_SCORE_FLOOR - 1,
        })
        assert resp2.status_code == 422

    def test_over_cap_returned_in_rejected(self, client: TestClient) -> None:
        urls = [f"https://example.com/job/{i}" for i in range(MAX_URLS + 2)]
        resp = client.post("/api/generate/batch/plan", json={"urls": urls})
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"]["accepted_count"] == MAX_URLS
        over = [r for r in body["rejected"] if r["reason"] == "over_cap"]
        assert len(over) == 2

    def test_response_is_json_serializable(self, client: TestClient) -> None:
        # Round-trip JSON to catch any tuple/dataclass leakage.
        import json
        resp = client.post("/api/generate/batch/plan", json={
            "urls": ["https://boards.greenhouse.io/acme/jobs/101"],
        })
        assert resp.status_code == 200
        # Already JSON via httpx, but re-encode to be sure.
        json.dumps(resp.json())

    def test_idempotent_same_input_same_output(self, client: TestClient) -> None:
        payload = {"urls": [
            "https://boards.greenhouse.io/acme/jobs/101",
            "https://jobs.lever.co/foo/abc-123",
        ]}
        a = client.post("/api/generate/batch/plan", json=payload).json()
        b = client.post("/api/generate/batch/plan", json=payload).json()
        assert a == b
