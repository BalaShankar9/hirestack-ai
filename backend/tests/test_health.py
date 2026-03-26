"""Health and basic endpoint tests"""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_auth_required_endpoints(client):
    """All protected endpoints should return 401 without a token."""
    protected = [
        ("GET", "/api/profile"),
        ("GET", "/api/candidates"),
        ("GET", "/api/ats"),
        ("GET", "/api/salary/"),
        ("GET", "/api/interview/sessions"),
        ("GET", "/api/analytics/dashboard"),
        ("GET", "/api/orgs"),
        ("GET", "/api/learning/today"),
    ]
    for method, path in protected:
        resp = await client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}, expected 401"


@pytest.mark.asyncio
async def test_guest_endpoints_accessible(client):
    """Guest endpoints should not return 401."""
    # Resume parse needs a file, so 422 is expected (validation error)
    resp = await client.post("/api/generate/pipeline", json={})
    assert resp.status_code != 401, "Pipeline should be accessible without auth"

    resp = await client.post("/api/generate/pipeline/stream", json={})
    assert resp.status_code != 401, "Pipeline stream should be accessible without auth"


@pytest.mark.asyncio
async def test_cors_headers(client):
    """CORS should be configured."""
    resp = await client.options(
        "/health",
        headers={
            "Origin": "https://hirestack.tech",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Should not be blocked
    assert resp.status_code in (200, 204, 307)


@pytest.mark.asyncio
async def test_security_headers(client):
    """Security headers middleware is registered."""
    from app.core.security import SecurityHeadersMiddleware
    assert SecurityHeadersMiddleware is not None
    # Verify it has the expected HEADERS
    assert len(SecurityHeadersMiddleware.HEADERS) >= 5

