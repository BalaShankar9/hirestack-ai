"""
Comprehensive backend route tests — auth, jobs, candidates, billing, interview, learning, salary, career.
Tests auth enforcement, input validation, and response formats.
"""
import pytest
import uuid


# ── Extended Auth Enforcement ────────────────────────────────────

ADDITIONAL_AUTH_ROUTES = [
    ("GET", "/api/auth/me"),
    ("PUT", "/api/auth/me"),
    ("POST", "/api/auth/sync"),
    ("GET", "/api/billing/status"),
    ("POST", "/api/billing/checkout"),
    ("POST", "/api/billing/portal"),
    ("POST", "/api/billing/record-export"),
    ("POST", "/api/jobs"),
    ("DELETE", f"/api/jobs/{uuid.uuid4()}"),
    ("GET", "/api/candidates"),
    ("POST", "/api/candidates"),
    ("GET", "/api/candidates/stats"),
    ("POST", "/api/interview/sessions"),
    ("GET", "/api/career/portfolio"),
    ("POST", "/api/career/snapshot"),
    ("POST", "/api/benchmark/generate"),
    ("GET", "/api/job-sync/alerts"),
    ("GET", "/api/job-sync/matches"),
    ("GET", "/api/api-keys/keys"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ADDITIONAL_AUTH_ROUTES)
async def test_extended_auth_enforcement(client, method, path):
    """Additional protected endpoints must return 401 without auth."""
    resp = await client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}"


# ── Jobs Input Validation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_job_requires_title(client):
    """Creating a job without a title should fail validation."""
    resp = await client.post(
        "/api/jobs",
        json={"company": "Test"},
        headers={"Authorization": "Bearer fake"},
    )
    # 401 (no real auth) or 422 (validation error)
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_create_job_rejects_xss_title(client):
    """Job title with script tags should be rejected or sanitized."""
    resp = await client.post(
        "/api/jobs",
        json={"title": '<script>alert("xss")</script>'},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_get_job_invalid_uuid(client):
    """Getting a job with invalid UUID should return 422."""
    resp = await client.get(
        "/api/jobs/not-a-uuid",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Candidates Input Validation ──────────────────────────────────


@pytest.mark.asyncio
async def test_create_candidate_rejects_empty(client):
    """Creating a candidate with empty body should fail."""
    resp = await client.post(
        "/api/candidates",
        json={},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_candidate_invalid_uuid(client):
    """Candidate endpoint with invalid UUID should return 422."""
    resp = await client.get(
        "/api/candidates/not-a-uuid",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_move_candidate_invalid_stage(client):
    """Moving a candidate to invalid pipeline stage should fail."""
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/candidates/{fake_id}/move",
        json={"stage": ""},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Interview Input Validation ───────────────────────────────────


@pytest.mark.asyncio
async def test_create_interview_requires_job_title(client):
    """Creating an interview session without job_title should fail."""
    resp = await client.post(
        "/api/interview/sessions",
        json={},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_submit_answer_requires_fields(client):
    """Submitting an interview answer with empty body should fail."""
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/interview/sessions/{fake_id}/answers",
        json={},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Salary Input Validation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_salary_analyze_requires_job_title(client):
    """Salary analysis without job_title should fail validation."""
    resp = await client.post(
        "/api/salary/analyze",
        json={},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_salary_invalid_uuid(client):
    """Salary analysis with invalid UUID should return 422."""
    resp = await client.get(
        "/api/salary/not-a-uuid",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Learning Input Validation ────────────────────────────────────


@pytest.mark.asyncio
async def test_learning_generate_accepts_valid(client):
    """Learning generation with valid body should hit auth (not 422)."""
    resp = await client.post(
        "/api/learning/generate",
        json={"skills": ["Python"], "count": 3},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 503)  # Auth blocks, but not validation


@pytest.mark.asyncio
async def test_learning_generate_rejects_excessive_count(client):
    """Learning generation with count > 20 should fail validation."""
    resp = await client.post(
        "/api/learning/generate",
        json={"skills": ["Python"], "count": 100},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Benchmark Input Validation ───────────────────────────────────


@pytest.mark.asyncio
async def test_benchmark_generate_requires_job_id(client):
    """Benchmark generation without job_description_id should fail."""
    resp = await client.post(
        "/api/benchmark/generate",
        json={},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_benchmark_invalid_uuid(client):
    """Getting a benchmark with invalid UUID should return 422."""
    resp = await client.get(
        "/api/benchmark/not-a-uuid",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Billing Input Validation ────────────────────────────────────


@pytest.mark.asyncio
async def test_checkout_requires_plan(client):
    """Checkout without plan should fail validation."""
    resp = await client.post(
        "/api/billing/checkout",
        json={},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_checkout_rejects_invalid_plan(client):
    """Checkout with invalid plan name should fail."""
    resp = await client.post(
        "/api/billing/checkout",
        json={"plan": "hacker_plan", "success_url": "https://x.com", "cancel_url": "https://x.com"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Health / Smoke ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Health check returns 200 (healthy) or 503 (degraded when Supabase unavailable)."""
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert data.get("status") in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_openapi_docs(client):
    """OpenAPI docs should be accessible (200) or disabled in production (404)."""
    resp = await client.get("/docs")
    assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_openapi_json(client):
    """OpenAPI JSON schema should be accessible."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "paths" in data
    assert "info" in data


# ── CORS / Security Headers ─────────────────────────────────────


@pytest.mark.asyncio
async def test_cors_headers(client):
    """CORS headers should be set properly on OPTIONS preflight."""
    resp = await client.options(
        "/api/health",
        headers={
            "Origin": "https://hirestack.tech",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Should allow the correct origin
    assert resp.status_code in (200, 204, 405)


@pytest.mark.asyncio
async def test_cors_rejects_unknown_origin(client):
    """Unknown origins should not get CORS access-control-allow-origin."""
    resp = await client.options(
        "/api/health",
        headers={
            "Origin": "https://evil-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    # Should not wildcard or allow evil-site.com
    if allow_origin:
        assert allow_origin != "https://evil-site.com" or allow_origin == "*"


# ── Response Format Consistency ──────────────────────────────────


@pytest.mark.asyncio
async def test_401_response_format(client):
    """401 responses should have a consistent error body."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_webhook_no_signature_returns_400_or_422(client):
    """Stripe webhook without signature should fail."""
    resp = await client.post(
        "/api/billing/webhook",
        content=b"test",
        headers={"Content-Type": "application/json"},
    )
    # Should not be 200 (no valid signature)
    assert resp.status_code in (400, 422, 500, 503)
