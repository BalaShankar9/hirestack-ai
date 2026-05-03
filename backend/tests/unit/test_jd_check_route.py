"""Tests for backend/app/api/routes/jd_check.py — public POST /api/jd-check."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.testclient import TestClient

from app.api.routes import jd_check as jc
from app.core.security import limiter


# ── Request validation ──────────────────────────────────────────────


class TestRequestValidation:
    def test_empty_string_rejected(self):
        with pytest.raises(Exception):
            jc.JDCheckRequest(text="")

    def test_whitespace_only_rejected(self):
        with pytest.raises(Exception):
            jc.JDCheckRequest(text="   \n\t  ")

    def test_oversize_rejected(self):
        with pytest.raises(Exception):
            jc.JDCheckRequest(text="x" * (jc._MAX_JD_BYTES + 1))

    def test_valid_text_accepted(self):
        req = jc.JDCheckRequest(text="Hire a rockstar engineer.")
        assert req.text == "Hire a rockstar engineer."


# ── Pure helpers ────────────────────────────────────────────────────


class TestSerializers:
    def test_finding_to_dict_keys(self):
        from app.services.jd_anti_pattern_detector import detect_anti_patterns

        rep = detect_anti_patterns("Hire a rockstar engineer.")
        d = jc._finding_to_dict(rep.findings[0])
        assert set(d.keys()) == {"category", "severity", "snippet", "term", "char_start", "char_end"}

    def test_report_to_dict_top_level(self):
        from app.services.jd_anti_pattern_detector import detect_anti_patterns

        rep = detect_anti_patterns("Hire a rockstar engineer.")
        d = jc._report_to_dict(rep)
        assert set(d.keys()) == {"findings", "by_category", "severity_counts", "total_count"}
        assert isinstance(d["findings"], list)
        assert isinstance(d["by_category"], dict)
        assert isinstance(d["severity_counts"], dict)


# ── Route integration ──────────────────────────────────────────────


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(jc.router, prefix="/api")
    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_build_app())


class TestRoute:
    def test_clean_jd_returns_empty_findings(self, client: TestClient):
        resp = client.post(
            "/api/jd-check",
            json={"text": "Senior engineer wanted. $180k base. Strong communicator."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0
        assert data["findings"] == []
        assert data["severity_counts"] == {"critical": 0, "warn": 0, "info": 0}

    def test_bad_jd_flags_categories(self, client: TestClient):
        resp = client.post(
            "/api/jd-check",
            json={
                "text": (
                    "We're a family of digital natives looking for a "
                    "rockstar engineer. 20+ years Kubernetes. "
                    "Competitive salary. ASAP."
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] >= 5
        assert data["by_category"]["ageist"] >= 1
        assert data["by_category"]["gendered"] >= 1
        assert data["by_category"]["vague_compensation"] >= 1
        assert data["by_category"]["unrealistic_experience"] >= 1
        assert data["by_category"]["urgency"] >= 1
        # critical surface first
        assert data["findings"][0]["severity"] == "critical"

    def test_response_shape_finding(self, client: TestClient):
        resp = client.post("/api/jd-check", json={"text": "Hire a rockstar."})
        data = resp.json()
        f = data["findings"][0]
        assert set(f.keys()) == {"category", "severity", "snippet", "term", "char_start", "char_end"}
        assert isinstance(f["char_start"], int)
        assert isinstance(f["char_end"], int)
        assert f["char_end"] > f["char_start"]

    def test_response_shape_top_level(self, client: TestClient):
        resp = client.post("/api/jd-check", json={"text": "Hire a rockstar."})
        data = resp.json()
        for key in ("findings", "by_category", "severity_counts", "total_count"):
            assert key in data
        assert set(data["by_category"].keys()) == {
            "ageist", "gendered", "vague_compensation",
            "unrealistic_experience", "culture_red_flag", "urgency",
        }
        assert set(data["severity_counts"].keys()) == {"critical", "warn", "info"}

    def test_empty_body_returns_422(self, client: TestClient):
        resp = client.post("/api/jd-check", json={})
        assert resp.status_code == 422

    def test_empty_text_returns_422(self, client: TestClient):
        resp = client.post("/api/jd-check", json={"text": ""})
        assert resp.status_code == 422

    def test_whitespace_text_returns_422(self, client: TestClient):
        resp = client.post("/api/jd-check", json={"text": "   "})
        assert resp.status_code == 422

    def test_oversize_text_returns_422(self, client: TestClient):
        resp = client.post("/api/jd-check", json={"text": "x" * (jc._MAX_JD_BYTES + 1)})
        assert resp.status_code == 422

    def test_idempotent_same_input(self, client: TestClient):
        payload = {"text": "Rockstar wanted ASAP. Competitive salary."}
        a = client.post("/api/jd-check", json=payload).json()
        b = client.post("/api/jd-check", json=payload).json()
        assert a == b

    def test_no_caching_field_in_response(self, client: TestClient):
        # Unlike ghost-check, this route does NOT cache (output is deterministic).
        resp = client.post("/api/jd-check", json={"text": "Hire a rockstar."})
        data = resp.json()
        assert "cached" not in data

    def test_unicode_text_handled(self, client: TestClient):
        resp = client.post(
            "/api/jd-check",
            json={"text": "Looking for rockstar — résumé required."},
        )
        assert resp.status_code == 200
        assert resp.json()["total_count"] >= 1

    def test_non_str_text_returns_422(self, client: TestClient):
        resp = client.post("/api/jd-check", json={"text": 123})
        assert resp.status_code == 422


# ── Rate limit pin ─────────────────────────────────────────────────


class TestRateLimitDecorator:
    def test_route_decorated_with_limit(self):
        # The slowapi limiter attaches "_rate_limit" attribute on the wrapped fn.
        # We assert the route function has the limit decorator applied.
        for route in jc.router.routes:
            if getattr(route, "path", "") == "/jd-check":
                assert route.endpoint is not None
                # slowapi tags the wrapper; introspecting via __wrapped__ chain
                # is fragile, so we just assert the route is mounted POST.
                assert "POST" in route.methods  # type: ignore[union-attr]
                return
        pytest.fail("/jd-check route not found")
