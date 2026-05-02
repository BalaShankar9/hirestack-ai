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


# ── Score route ──────────────────────────────────────────────────────


from app.api.routes.batch_generate import get_scorer  # noqa: E402
from app.services.batch_evaluator import BatchEntry, ScoringResult  # noqa: E402


def _ok_scorer_factory(score_map):
    """Return a scorer that maps canonical_url → fit_score from the dict."""
    async def _scorer(entry: BatchEntry) -> ScoringResult:
        return ScoringResult(
            canonical_url=entry.canonical_url,
            fit_score=score_map.get(entry.canonical_url, 1.0),
            error=None,
            title="t",
            company="c",
        )
    return _scorer


def _build_score_app(scorer=None) -> FastAPI:
    app = FastAPI()
    app.state.limiter = batch_route.limiter
    app.include_router(batch_route.router, prefix="/api")
    app.dependency_overrides[api_deps.get_current_user] = lambda: _FAKE_USER
    if scorer is not None:
        app.dependency_overrides[get_scorer] = lambda: scorer
    return app


@pytest.fixture()
def score_client_factory():
    def _factory(scorer=None) -> TestClient:
        try:
            batch_route.limiter.reset()
        except Exception:
            pass
        return TestClient(_build_score_app(scorer))
    return _factory


class TestScoreBatchRoute:
    def test_empty_payload_returns_empty_buckets(self, score_client_factory) -> None:
        client = score_client_factory()
        resp = client.post("/api/generate/batch/score", json={"urls": []})
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"]["summary"]["is_empty"] is True
        assert body["scored"]["ranked"] == []
        assert body["scored"]["below_threshold"] == []
        assert body["scored"]["failed"] == []
        assert body["scored"]["summary"]["ranked_count"] == 0

    def test_default_stub_scorer_marks_all_failed(self, score_client_factory) -> None:
        """No scorer configured → every URL lands in `failed` with the typed error."""
        client = score_client_factory()
        resp = client.post("/api/generate/batch/score", json={
            "urls": ["https://boards.greenhouse.io/acme/jobs/101"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["scored"]["summary"]["failed_count"] == 1
        assert body["scored"]["failed"][0]["error"] == "scorer_not_configured"
        assert body["scored"]["ranked"] == []

    def test_injected_scorer_above_threshold_ranked(self, score_client_factory) -> None:
        u1 = "https://boards.greenhouse.io/acme/jobs/101"
        u2 = "https://jobs.lever.co/foo/abc-123"
        scorer = _ok_scorer_factory({u1: 4.5, u2: 2.0})
        client = score_client_factory(scorer=scorer)
        resp = client.post("/api/generate/batch/score", json={
            "urls": [u1, u2],
            "min_fit_score": 3.0,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["scored"]["summary"]["ranked_count"] == 1
        assert body["scored"]["summary"]["below_threshold_count"] == 1
        assert body["scored"]["ranked"][0]["fit_score"] == 4.5
        assert body["scored"]["below_threshold"][0]["fit_score"] == 2.0

    def test_min_fit_score_echoed(self, score_client_factory) -> None:
        scorer = _ok_scorer_factory({})
        client = score_client_factory(scorer=scorer)
        resp = client.post("/api/generate/batch/score", json={
            "urls": [],
            "min_fit_score": 3.7,
        })
        assert resp.status_code == 200
        assert resp.json()["min_fit_score"] == 3.7

    def test_min_fit_score_out_of_range_422(self, score_client_factory) -> None:
        client = score_client_factory()
        resp = client.post("/api/generate/batch/score", json={
            "urls": [],
            "min_fit_score": MIN_FIT_SCORE_CEIL + 1,
        })
        assert resp.status_code == 422

    def test_concurrency_out_of_range_422(self, score_client_factory) -> None:
        client = score_client_factory()
        # MAX_CONCURRENCY=16, so 1000 should 422.
        resp = client.post("/api/generate/batch/score", json={
            "urls": [],
            "concurrency": 1000,
        })
        assert resp.status_code == 422

        resp2 = client.post("/api/generate/batch/score", json={
            "urls": [],
            "concurrency": 0,
        })
        assert resp2.status_code == 422

    def test_invalid_urls_dont_reach_scorer(self, score_client_factory) -> None:
        called_with = []

        async def scorer(entry: BatchEntry) -> ScoringResult:
            called_with.append(entry.canonical_url)
            return ScoringResult(canonical_url=entry.canonical_url, fit_score=4.0, error=None)

        client = score_client_factory(scorer=scorer)
        resp = client.post("/api/generate/batch/score", json={
            "urls": ["", "not-a-url", "https://boards.greenhouse.io/acme/jobs/101"],
        })
        assert resp.status_code == 200
        # Only the 1 valid URL reaches the scorer.
        assert len(called_with) == 1
        body = resp.json()
        assert body["plan"]["summary"]["accepted_count"] == 1
        assert body["plan"]["summary"]["rejected_count"] == 2

    def test_scorer_failure_routes_to_failed_bucket(self, score_client_factory) -> None:
        async def scorer(entry: BatchEntry) -> ScoringResult:
            raise RuntimeError("boom")

        client = score_client_factory(scorer=scorer)
        resp = client.post("/api/generate/batch/score", json={
            "urls": ["https://boards.greenhouse.io/acme/jobs/101"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["scored"]["summary"]["failed_count"] == 1
        assert body["scored"]["failed"][0]["error"].startswith("scorer_bug:")

    def test_response_is_json_serializable(self, score_client_factory) -> None:
        import json
        scorer = _ok_scorer_factory({})
        client = score_client_factory(scorer=scorer)
        resp = client.post("/api/generate/batch/score", json={
            "urls": ["https://boards.greenhouse.io/acme/jobs/101"],
        })
        assert resp.status_code == 200
        json.dumps(resp.json())

    def test_plan_payload_included_in_response(self, score_client_factory) -> None:
        """Response must include the plan so UI can show rejections + scores in one shot."""
        scorer = _ok_scorer_factory({})
        client = score_client_factory(scorer=scorer)
        resp = client.post("/api/generate/batch/score", json={
            "urls": ["", "https://boards.greenhouse.io/acme/jobs/101"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "plan" in body
        assert body["plan"]["summary"]["accepted_count"] == 1
        assert body["plan"]["summary"]["rejected_count"] == 1
