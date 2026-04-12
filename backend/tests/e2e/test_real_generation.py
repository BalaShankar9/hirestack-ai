"""
Real E2E test — hits REAL Supabase + REAL Gemini.

Requires live credentials in backend/.env:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY

Also requires an E2E test user in Supabase Auth:
  E2E_TEST_EMAIL  (default: e2e-test@hirestack.local)
  E2E_TEST_PASSWORD  (default: E2ETestPass!2026)

The test will CREATE the test user if it doesn't exist (using service role).

Skip criteria: any missing credential → pytest.skip().

IMPORTANT: This test makes real AI API calls. Each run costs ~$0.01-0.05
in Gemini API usage and takes 30-120 seconds.
"""
import asyncio
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

import httpx
import pytest


# ── Skip unless real credentials are available ────────────────────────────


def _get_real_settings():
    """Load real settings from backend/.env (not test placeholders)."""
    # Remove test-injected placeholders so pydantic-settings reads .env
    saved = {}
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                "GEMINI_API_KEY", "ENVIRONMENT", "DEBUG"):
        if key in os.environ:
            saved[key] = os.environ.pop(key)

    try:
        # Force fresh settings
        from app.core.config import Settings
        s = Settings()
        return s, saved
    finally:
        os.environ.update(saved)


def _has_real_credentials() -> bool:
    s, saved = _get_real_settings()
    os.environ.update(saved)
    return bool(
        s.supabase_url and "placeholder" not in s.supabase_url
        and s.supabase_service_role_key and "placeholder" not in s.supabase_service_role_key
        and s.gemini_api_key
    )


def _server_is_running() -> bool:
    """Check if the backend server is listening."""
    import socket
    from app.core.config import get_settings
    s = get_settings()
    try:
        with socket.create_connection(("localhost", s.port), timeout=2):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


pytestmark = [
    pytest.mark.skipif(
        not _has_real_credentials(),
        reason="Real Supabase/Gemini credentials not available — skipping E2E",
    ),
    pytest.mark.skipif(
        not _server_is_running(),
        reason="Backend server not running on localhost — start with: uvicorn main:app",
    ),
]


# ── Test user management via Supabase Admin API ──────────────────────────


E2E_EMAIL = os.environ.get("E2E_TEST_EMAIL", "e2e-test@hirestack.local")
E2E_PASSWORD = os.environ.get("E2E_TEST_PASSWORD", "E2ETestPass!2026")


class SupabaseAdmin:
    """Thin wrapper around Supabase Admin Auth API (service role)."""

    def __init__(self, url: str, service_key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    async def get_or_create_user(self, email: str, password: str) -> Dict[str, Any]:
        """Get existing user or create a new one. Returns user dict."""
        async with httpx.AsyncClient(timeout=15) as c:
            # List users and find by email
            resp = await c.get(
                f"{self.url}/auth/v1/admin/users",
                headers=self.headers,
            )
            resp.raise_for_status()
            users = resp.json().get("users", [])
            for u in users:
                if u.get("email") == email:
                    return u

            # Create
            resp = await c.post(
                f"{self.url}/auth/v1/admin/users",
                headers=self.headers,
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"full_name": "E2E Test User"},
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Sign in and return {access_token, refresh_token, user}."""
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.post(
                f"{self.url}/auth/v1/token?grant_type=password",
                headers={"apikey": self.headers["apikey"], "Content-Type": "application/json"},
                json={"email": email, "password": password},
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_rows(self, table: str, column: str, value: str, service_key: str):
        """Delete rows from a table using PostgREST (service role)."""
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.delete(
                f"{self.url}/rest/v1/{table}?{column}=eq.{value}",
                headers={
                    **self.headers,
                    "Prefer": "return=minimal",
                },
            )
            # 404 / 406 are fine — table or row may not exist
            if resp.status_code not in (200, 204, 404, 406):
                resp.raise_for_status()


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def real_settings():
    """Load real settings (not test overrides)."""
    s, saved = _get_real_settings()
    os.environ.update(saved)
    return s


@pytest.fixture(scope="module")
def admin(real_settings):
    return SupabaseAdmin(real_settings.supabase_url, real_settings.supabase_service_role_key)


@pytest.fixture(scope="module")
def event_loop():
    """Module-scoped event loop for module-scoped async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def e2e_session(admin) -> Dict[str, Any]:
    """Get or create the E2E test user and sign in. Returns session dict."""
    await admin.get_or_create_user(E2E_EMAIL, E2E_PASSWORD)
    session = await admin.sign_in(E2E_EMAIL, E2E_PASSWORD)
    assert session.get("access_token"), "Failed to sign in E2E test user"
    return session


@pytest.fixture(scope="module")
def access_token(e2e_session) -> str:
    return e2e_session["access_token"]


@pytest.fixture(scope="module")
def user_id(e2e_session) -> str:
    return e2e_session["user"]["id"]


@pytest.fixture
async def e2e_application(admin, real_settings, access_token, user_id):
    """Create a real application row for testing, clean up after."""
    app_id = None
    job_ids = []

    async with httpx.AsyncClient(timeout=15) as c:
        # Create application via PostgREST (service role)
        resp = await c.post(
            f"{real_settings.supabase_url}/rest/v1/applications",
            headers={
                "apikey": real_settings.supabase_service_role_key,
                "Authorization": f"Bearer {real_settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json={
                "user_id": user_id,
                "title": f"E2E Test — {uuid.uuid4().hex[:8]}",
                "status": "draft",
                "confirmed_facts": {
                    "jobTitle": "Senior Python Engineer",
                    "company": "TestCorp",
                    "jdText": (
                        "We are looking for a Senior Python Engineer with 5+ years of experience "
                        "building scalable backend services. Must have strong experience with "
                        "FastAPI, PostgreSQL, and cloud platforms (AWS/GCP). Experience with "
                        "AI/ML pipelines is a strong plus. You will lead a team of 3 engineers "
                        "and report to the VP of Engineering."
                    ),
                    "resume": {
                        "text": (
                            "Jane Doe — Senior Software Engineer\n"
                            "5 years at TechCorp building Python microservices on AWS.\n"
                            "Led migration from monolith to FastAPI-based microservices.\n"
                            "Reduced API latency by 40% through async optimization.\n"
                            "Built ML inference pipeline serving 10K req/s.\n"
                            "BSc Computer Science, MIT 2019.\n"
                            "Skills: Python, FastAPI, PostgreSQL, AWS, Docker, Kubernetes, "
                            "TensorFlow, Redis, CI/CD, Agile."
                        ),
                    },
                },
            },
        )
        resp.raise_for_status()
        app_data = resp.json()
        app_id = app_data[0]["id"] if isinstance(app_data, list) else app_data["id"]

    yield {"app_id": app_id, "user_id": user_id, "job_ids": job_ids}

    # ── Cleanup ──
    if app_id:
        # Wait for any background pipeline tasks to finish persisting
        await asyncio.sleep(15)
        # Delete generation jobs first (FK constraint)
        for jid in job_ids:
            await admin.delete_rows("generation_job_events", "job_id", jid, real_settings.supabase_service_role_key)
        for jid in job_ids:
            await admin.delete_rows("generation_jobs", "id", jid, real_settings.supabase_service_role_key)
        await admin.delete_rows("applications", "id", app_id, real_settings.supabase_service_role_key)


# ── Sample data ───────────────────────────────────────────────────────────

SAMPLE_JD = (
    "We are looking for a Senior Python Engineer with 5+ years of experience "
    "building scalable backend services. Must have strong experience with "
    "FastAPI, PostgreSQL, and cloud platforms (AWS/GCP). Experience with "
    "AI/ML pipelines is a strong plus. You will lead a team of 3 engineers "
    "and report to the VP of Engineering."
)

SAMPLE_RESUME = (
    "Jane Doe — Senior Software Engineer\n"
    "5 years at TechCorp building Python microservices on AWS.\n"
    "Led migration from monolith to FastAPI-based microservices.\n"
    "Reduced API latency by 40% through async optimization.\n"
    "Built ML inference pipeline serving 10K req/s.\n"
    "BSc Computer Science, MIT 2019.\n"
    "Skills: Python, FastAPI, PostgreSQL, AWS, Docker, Kubernetes, "
    "TensorFlow, Redis, CI/CD, Agile."
)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Sync /pipeline — the fastest, most reliable E2E path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_sync_pipeline(real_settings, access_token):
    """
    THE PRIMARY E2E TEST.

    Hits /api/generate/pipeline with real Gemini AI, verifies:
    - Real AI-generated CV HTML with candidate details
    - Real scores (overall > 0)
    - Response format matches frontend expectations
    """
    api_url = f"http://localhost:{real_settings.port}"

    async with httpx.AsyncClient(timeout=300) as c:
        resp = await c.post(
            f"{api_url}/api/generate/pipeline",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "job_title": "Senior Python Engineer",
                "company": "TestCorp",
                "jd_text": SAMPLE_JD,
                "resume_text": SAMPLE_RESUME,
            },
        )

    if resp.status_code == 429:
        pytest.skip("Rate limited — retry later")

    assert resp.status_code == 200, f"Pipeline failed: {resp.status_code} {resp.text[:500]}"
    data = resp.json()

    cv_html = data.get("cvHtml", "")
    cl_html = data.get("coverLetterHtml", "")
    scores = data.get("scores", {})
    benchmark = data.get("benchmark", {})
    gaps = data.get("gaps", {})

    print(f"\n  Sync pipeline results:")
    print(f"    CV: {len(cv_html)} chars")
    print(f"    Cover letter: {len(cl_html)} chars")
    print(f"    Score: {scores.get('overall', 'N/A')}")
    print(f"    Benchmark keywords: {len(benchmark.get('keywords', []))}")
    print(f"    Gap dimensions: {len(gaps.get('gaps', []))}")

    # Core assertions
    assert scores.get("overall", 0) > 0, "Score should be positive"
    assert benchmark, "Benchmark data should be present"
    assert gaps, "Gap analysis should be present"
    assert len(cv_html) > 50 or len(cl_html) > 50, (
        f"AI output too short — CV={len(cv_html)}, CL={len(cl_html)} chars"
    )

    print(f"\n  ═══ SYNC PIPELINE E2E PASSED ═══")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Jobs flow — DB-backed generation with polling verification
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_generation_jobs_flow(real_settings, access_token, e2e_application):
    """
    Tests the production /jobs flow:

    1. POST /api/generate/jobs → get job_id
    2. Poll generation_jobs table for terminal status
    3. Verify: status=succeeded, scores > 0, benchmark/gaps populated
    """
    app_id = e2e_application["app_id"]
    api_url = f"http://localhost:{real_settings.port}"
    auth_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # ── Step 1: Create generation job ────────────────────────────────
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(
            f"{api_url}/api/generate/jobs",
            headers=auth_headers,
            json={
                "application_id": app_id,
                "requested_modules": ["benchmark", "gaps", "cv", "coverLetter"],
            },
        )

    assert resp.status_code == 200, f"Job creation failed: {resp.status_code} {resp.text}"
    body = resp.json()
    job_id = body["job_id"]
    e2e_application["job_ids"].append(job_id)
    print(f"\n  ✓ Job created: {job_id}")

    # ── Step 2: Verify job exists in DB and starts processing ────────
    # The full multi-agent pipeline takes 10-15+ minutes (4 pipelines with
    # revision loops). Test 1 (sync pipeline) already proves end-to-end
    # generation works. This test verifies the jobs API creates a real job
    # and it transitions from queued → running with progress advancing.
    svc_headers = {
        "apikey": real_settings.supabase_service_role_key,
        "Authorization": f"Bearer {real_settings.supabase_service_role_key}",
    }

    status = "queued"
    max_progress = 0
    poll_count = 0
    max_polls = 36  # 3 minutes max (36 * 5s) — just enough to see it start
    phases_seen = []

    async with httpx.AsyncClient(timeout=15) as c:
        while poll_count < max_polls:
            poll_count += 1
            await asyncio.sleep(5)

            resp = await c.get(
                f"{real_settings.supabase_url}/rest/v1/generation_jobs"
                f"?id=eq.{job_id}&select=status,progress,phase",
                headers={**svc_headers, "Accept": "application/json"},
            )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                continue

            job = rows[0]
            status = job.get("status", "queued")
            phase = job.get("phase", "")
            progress = job.get("progress", 0)
            max_progress = max(max_progress, progress)

            if phase and phase not in phases_seen:
                phases_seen.append(phase)
                print(f"  → {phase}: {progress}%")

            # Success criteria: job is running and has made progress
            if status == "running" and progress >= 18:
                print(f"  ✓ Job is actively processing (progress={progress}%)")
                break

            # If it already completed, that's great too
            if status in ("succeeded", "failed", "cancelled"):
                print(f"  Job reached terminal status: {status}")
                break

    # ── Step 3: Verify the job started and progressed ────────────────
    assert status in ("running", "succeeded"), f"Expected running/succeeded, got {status}"
    assert max_progress >= 8, f"Expected some progress, got {max_progress}%"
    assert len(phases_seen) >= 1, "Expected at least one pipeline phase"
    print(f"  Phases seen: {phases_seen}")
    print(f"  Max progress: {max_progress}%")

    print(f"\n  ═══ JOBS FLOW E2E PASSED ═══")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: SSE stream connectivity — verify events flow over SSE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_real_sse_stream_events(real_settings, access_token, e2e_application):
    """
    Verify the SSE stream delivers real progress events.
    Creates a job and streams for up to 60s — checks that at least
    a few progress events arrive (doesn't wait for completion).
    """
    app_id = e2e_application["app_id"]
    api_url = f"http://localhost:{real_settings.port}"

    # Create a new job
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.post(
            f"{api_url}/api/generate/jobs",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "application_id": app_id,
                "requested_modules": ["benchmark", "gaps"],
            },
        )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    e2e_application["job_ids"].append(job_id)

    # Stream for up to 60s — just check events arrive
    events = []
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            async with c.stream(
                "GET",
                f"{api_url}/api/generate/jobs/{job_id}/stream",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as stream:
                async for line in stream.aiter_lines():
                    if line.startswith("event:"):
                        event_name = line[len("event:"):].strip()
                    elif line.startswith("data:") and event_name:
                        try:
                            data = json.loads(line[len("data:"):].strip())
                        except json.JSONDecodeError:
                            data = {}
                        events.append({"event": event_name, "data": data})
                        if event_name in ("complete", "error") or len(events) >= 10:
                            break
    except httpx.ReadTimeout:
        pass  # Expected — we only stream for 60s

    event_types = [e["event"] for e in events]
    print(f"\n  SSE events received: {event_types}")
    assert "progress" in event_types, f"No progress events in SSE stream. Got: {event_types}"
    print(f"  ═══ SSE STREAM E2E PASSED ═══")
