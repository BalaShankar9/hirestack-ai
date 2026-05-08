"""Tests for backend/app/api/routes/ghost_check.py."""

from __future__ import annotations

from typing import Tuple

import pytest
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.testclient import TestClient

from app.api.routes import ghost_check as gc
from app.core.security import limiter


# ── Helper-function tests (no HTTP) ──────────────────────────────────────


class TestExtractApplyControls:
    def test_finds_anchor_apply(self) -> None:
        html = '<html><body><a href="/apply">Apply for this job</a></body></html>'
        assert "Apply for this job" in gc.extract_apply_controls(html)

    def test_finds_button_apply(self) -> None:
        html = "<button>Apply Now</button>"
        assert "Apply Now" in gc.extract_apply_controls(html)

    def test_finds_input_submit(self) -> None:
        html = '<input type="submit" value="Submit Application">'
        assert "Submit Application" in gc.extract_apply_controls(html)

    def test_dedupes_case_insensitively(self) -> None:
        html = "<button>Apply</button><a>apply</a><button>APPLY</button>"
        out = gc.extract_apply_controls(html)
        assert len(out) == 1

    def test_caps_at_50(self) -> None:
        html = "".join(f"<a>Item {i}</a>" for i in range(200))
        assert len(gc.extract_apply_controls(html)) == 50

    def test_empty_returns_empty(self) -> None:
        assert gc.extract_apply_controls("") == []


class TestExtractVisibleText:
    def test_strips_tags(self) -> None:
        html = "<p>Hello <b>world</b></p>"
        assert gc.extract_visible_text(html) == "Hello world"

    def test_collapses_whitespace(self) -> None:
        html = "<p>a\n\n\n  b\t\tc</p>"
        assert gc.extract_visible_text(html) == "a b c"

    def test_caps_at_max_chars(self) -> None:
        html = "a" * 20000
        assert len(gc.extract_visible_text(html, max_chars=100)) == 100


class TestRequestValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/job",
            "javascript:alert(1)",
            "  ",
            "not-a-url",
            "http://",
        ],
    )
    def test_invalid_url_rejected(self, url: str) -> None:
        with pytest.raises(Exception):
            gc.GhostCheckRequest(url=url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://boards.greenhouse.io/acme/jobs/1234567",
            "http://example.com/careers/role",
        ],
    )
    def test_valid_url_accepted(self, url: str) -> None:
        req = gc.GhostCheckRequest(url=url)
        assert req.url == url


# ── Cache tests ──────────────────────────────────────────────────────────


class TestCache:
    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        gc._cache.clear()
        gc._hash_index.clear()
        yield
        gc._cache.clear()
        gc._hash_index.clear()

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self) -> None:
        assert await gc._cache_get("missing") is None

    @pytest.mark.asyncio
    async def test_put_then_get(self) -> None:
        await gc._cache_put("k", {"x": 1})
        assert (await gc._cache_get("k")) == {"x": 1}

    @pytest.mark.asyncio
    async def test_expired_entry_evicted(self, monkeypatch) -> None:
        await gc._cache_put("k", {"x": 1})
        # Force expiry.
        gc._cache["k"] = (gc._cache["k"][0], 0.0)
        assert await gc._cache_get("k") is None
        assert "k" not in gc._cache


# ── Route integration test (isolated app) ────────────────────────────────


def _build_app() -> FastAPI:
    """Build a minimal FastAPI app mounting only the ghost_check router.

    Avoids booting Supabase / AI engine / etc.
    """
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(gc.router, prefix="/api")
    return app


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    gc._cache.clear()
    gc._hash_index.clear()

    async def fake_fetch(url: str) -> Tuple[int, str, str]:
        # Simulate a live Greenhouse posting.
        return (
            200,
            url,
            "<html><body>"
            + ("Engineer role description. " * 30)
            + "<a href='/apply'>Apply for this job</a>"
            + "</body></html>",
        )

    monkeypatch.setattr(gc, "fetch_posting", fake_fetch)
    return TestClient(_build_app())


class TestRoute:
    def test_legitimate_verdict(self, client: TestClient) -> None:
        resp = client.post(
            "/api/ghost-check",
            json={"url": "https://boards.greenhouse.io/acme/jobs/1234567"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "legitimate"
        assert data["ats_provider"] == "greenhouse"
        assert data["cached"] is False
        assert "url_hash" in data
        assert len(data["url_hash"]) == 16

    def test_second_call_is_cached(self, client: TestClient) -> None:
        url = "https://boards.greenhouse.io/acme/jobs/9999999"
        first = client.post("/api/ghost-check", json={"url": url})
        second = client.post("/api/ghost-check", json={"url": url})
        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        # Same hash for same canonical URL.
        assert first.json()["url_hash"] == second.json()["url_hash"]

    def test_invalid_url_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/ghost-check", json={"url": "ftp://x/y"})
        assert resp.status_code == 422

    def test_missing_body_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/ghost-check", json={})
        assert resp.status_code == 422

    def test_response_shape(self, client: TestClient) -> None:
        resp = client.post(
            "/api/ghost-check",
            json={"url": "https://boards.greenhouse.io/acme/jobs/1"},
        )
        data = resp.json()
        # Verdict fields from PostingLegitimacy.to_dict()
        for key in (
            "tier",
            "confidence",
            "url_canonical",
            "ats_provider",
            "ats_company",
            "ats_job_id",
            "liveness",
            "signals",
            "reasoning",
            "evaluated_at",
        ):
            assert key in data, f"missing {key}"
        # Plus our wrapper additions:
        assert "cached" in data
        assert "url_hash" in data


class TestPermalink:
    def test_get_after_post_returns_verdict(self, client: TestClient) -> None:
        url = "https://boards.greenhouse.io/acme/jobs/77"
        post = client.post("/api/ghost-check", json={"url": url})
        assert post.status_code == 200
        url_hash = post.json()["url_hash"]

        get = client.get(f"/api/ghost-check/{url_hash}")
        assert get.status_code == 200
        assert get.json()["tier"] == "legitimate"
        assert get.json()["cached"] is True
        assert get.json()["url_hash"] == url_hash

    def test_unknown_hash_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/ghost-check/0123456789abcdef")
        assert resp.status_code == 404

    @pytest.mark.parametrize(
        "bad_hash",
        ["too-short", "NOT_HEX_CHARACTERS!", "abc", "x" * 16],
    )
    def test_invalid_hash_returns_400_or_404(
        self, client: TestClient, bad_hash: str
    ) -> None:
        resp = client.get(f"/api/ghost-check/{bad_hash}")
        # 16-char-non-hex → 400; shorter/longer → 400 (our validator).
        assert resp.status_code == 400


class TestFetchOnTimeout:
    @pytest.mark.asyncio
    async def test_fetch_returns_zero_on_error(self, monkeypatch) -> None:
        import httpx

        async def _boom(*_a, **_kw):
            raise httpx.ConnectTimeout("boom")

        # ghost_check now routes through safe_follow_get; patch there.
        monkeypatch.setattr(gc, "safe_follow_get", _boom)
        status, final_url, body = await gc.fetch_posting("https://example.com")
        assert status == 0
        assert body == ""
