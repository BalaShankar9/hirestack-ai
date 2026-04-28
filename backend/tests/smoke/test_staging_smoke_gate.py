"""Rank 4: Staging Smoke Gate — pytest-based blocking check for CI.

Requires environment variables:
  SMOKE_BASE_URL      e.g. http://localhost:8000 or https://staging.hirestack.dev
  SMOKE_EMAIL         test user email
  SMOKE_PASSWORD      test user password
  SUPABASE_URL        Supabase project URL (for polling)
  SUPABASE_SERVICE_KEY  service-role key (for polling job status and cleanup)

When SMOKE_BASE_URL is unset, all tests are skipped (safe for offline unit runs).

Gate contract:
  1. /health returns 200 with {"status": "ok"}
  2. Auth token can be obtained (sign-in works)
  3. /api/auth/me returns 200 with the authenticated user
  4. Create a generation job → returns job_id
  5. Job reaches a terminal status within SMOKE_JOB_TIMEOUT_SECONDS (default 180)
  6. Terminal status is in {"succeeded", "completed", "succeeded_with_warnings"}
  7. At least one generation_job_events row exists for the job
  8. All events that carry execution_path tag it as "agent" (canonical runtime)
"""
from __future__ import annotations

import os
import time
from typing import Any

import pytest
import requests


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_TERMINAL = frozenset({"succeeded", "completed", "succeeded_with_warnings", "failed", "cancelled"})
_SUCCESS = frozenset({"succeeded", "completed", "succeeded_with_warnings"})

_BASE = os.getenv("SMOKE_BASE_URL", "").rstrip("/")
_EMAIL = os.getenv("SMOKE_EMAIL", "")
_PASSWORD = os.getenv("SMOKE_PASSWORD", "")
_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_TIMEOUT = int(os.getenv("SMOKE_JOB_TIMEOUT_SECONDS", "180"))

pytestmark = pytest.mark.skipif(
    not _BASE,
    reason="SMOKE_BASE_URL not set — staging smoke gate skipped",
)


@pytest.fixture(scope="module")
def auth_token() -> str:
    """Sign in and return the bearer token."""
    assert _SUPABASE_URL, "SUPABASE_URL required for smoke gate"
    r = requests.post(
        f"{_SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": _SERVICE_KEY, "Content-Type": "application/json"},
        json={"email": _EMAIL, "password": _PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Sign-in failed ({r.status_code}): {r.text[:300]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def supabase_headers() -> dict[str, str]:
    assert _SERVICE_KEY, "SUPABASE_SERVICE_KEY required for smoke gate"
    return {
        "apikey": _SERVICE_KEY,
        "Authorization": f"Bearer {_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _supabase_get(path: str, supabase_headers: dict) -> Any:
    r = requests.get(
        f"{_SUPABASE_URL}/rest/v1/{path}",
        headers=supabase_headers,
        timeout=10,
    )
    assert r.status_code == 200, f"Supabase GET failed ({r.status_code}): {r.text[:200]}"
    return r.json()


# ---------------------------------------------------------------------------
# Gate 1: Health
# ---------------------------------------------------------------------------


class TestHealthGate:
    def test_health_returns_ok(self):
        r = requests.get(f"{_BASE}/health", timeout=10)
        assert r.status_code == 200, f"/health returned {r.status_code}"
        body = r.json()
        assert body.get("status") == "ok", f"/health body: {body}"


# ---------------------------------------------------------------------------
# Gate 2: Auth
# ---------------------------------------------------------------------------


class TestAuthGate:
    def test_sign_in_succeeds(self, auth_token: str):
        assert auth_token, "auth_token must be non-empty"

    def test_me_endpoint(self, auth_headers: dict):
        r = requests.get(f"{_BASE}/api/auth/me", headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"/api/auth/me returned {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "id" in body or "user_id" in body, f"Unexpected /me shape: {body}"


# ---------------------------------------------------------------------------
# Gate 3: Generation pipeline
# ---------------------------------------------------------------------------


def _create_test_application(auth_headers: dict) -> str:
    """Create a minimal application via the API and return its ID."""
    r = requests.post(
        f"{_BASE}/api/applications",
        headers=auth_headers,
        json={
            "title": "Smoke Test Engineer at SmokeTestCo",
            "status": "active",
            "job_description": (
                "We are looking for a software engineer with Python and API experience "
                "to join our smoke-test team."
            ),
        },
        timeout=15,
    )
    assert r.status_code in (200, 201), (
        f"Application creation failed ({r.status_code}): {r.text[:300]}"
    )
    body = r.json()
    app_id = body.get("id") or body.get("application_id")
    assert app_id, f"No id in application response: {body}"
    return app_id


def _create_generation_job(auth_headers: dict, application_id: str) -> str:
    """Submit a generation job and return its job_id."""
    r = requests.post(
        f"{_BASE}/api/generate/jobs",
        headers=auth_headers,
        json={"application_id": application_id},
        timeout=15,
    )
    assert r.status_code in (200, 201), (
        f"Job creation failed ({r.status_code}): {r.text[:300]}"
    )
    body = r.json()
    job_id = body.get("job_id") or body.get("id")
    assert job_id, f"No job_id in job response: {body}"
    return job_id


def _poll_until_terminal(job_id: str, supabase_headers: dict, timeout: int) -> dict:
    """Poll generation_jobs via Supabase until terminal status or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        rows = _supabase_get(
            f"generation_jobs?id=eq.{job_id}&select=*",
            supabase_headers,
        )
        if not rows:
            continue
        job = rows[0]
        if job.get("status") in _TERMINAL:
            return job
    # Return whatever we have at timeout
    rows = _supabase_get(f"generation_jobs?id=eq.{job_id}&select=*", supabase_headers)
    return rows[0] if rows else {}


class TestGenerationPipelineGate:
    """End-to-end pipeline smoke gate — creates a real job and waits for success."""

    @pytest.fixture(scope="class")
    def pipeline_result(self, auth_headers: dict, supabase_headers: dict):
        """Run the pipeline once and return (job_id, final_job_row, events)."""
        app_id = _create_test_application(auth_headers)
        job_id = _create_generation_job(auth_headers, app_id)
        final_job = _poll_until_terminal(job_id, supabase_headers, _TIMEOUT)
        events = _supabase_get(
            f"generation_job_events?job_id=eq.{job_id}&select=*&order=sequence_no",
            supabase_headers,
        )
        return job_id, final_job, events

    def test_job_created(self, pipeline_result):
        job_id, _, _ = pipeline_result
        assert job_id, "job_id must be non-empty"

    def test_job_reaches_terminal_status(self, pipeline_result):
        _, job, _ = pipeline_result
        status = job.get("status", "unknown")
        assert status in _TERMINAL, (
            f"Job did not reach terminal status within {_TIMEOUT}s — current status: {status}"
        )

    def test_job_succeeds(self, pipeline_result):
        _, job, _ = pipeline_result
        status = job.get("status", "unknown")
        assert status in _SUCCESS, (
            f"Job completed with non-success status: {status}. "
            f"Error: {job.get('error_message', 'none')}"
        )

    def test_events_exist(self, pipeline_result):
        job_id, _, events = pipeline_result
        assert len(events) > 0, (
            f"No generation_job_events found for job {job_id}. "
            "Pipeline must emit at least one event."
        )

    def test_canonical_execution_path_tagged(self, pipeline_result):
        """All events carrying an execution_path must be tagged 'agent' (not 'legacy')."""
        _, _, events = pipeline_result
        violations = []
        for ev in events:
            payload = ev.get("payload") or {}
            path = payload.get("execution_path")
            if path and path != "agent":
                violations.append(
                    f"event {ev.get('event_name', '?')} seq={ev.get('sequence_no')} "
                    f"has execution_path={path!r}"
                )
        assert not violations, (
            "Detected non-canonical execution_path in events:\n"
            + "\n".join(violations)
        )
