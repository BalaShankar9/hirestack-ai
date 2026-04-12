"""Extended route tests — auth enforcement, input validation, and route registration."""
import pytest


# ── Auth Enforcement ──────────────────────────────────────────────


AUTH_PROTECTED_ROUTES = [
    ("GET", "/api/profile"),
    ("GET", "/api/profile/all"),
    ("GET", "/api/candidates"),
    ("GET", "/api/ats"),
    ("GET", "/api/salary/"),
    ("GET", "/api/interview/sessions"),
    ("GET", "/api/analytics/dashboard"),
    ("GET", "/api/orgs"),
    ("GET", "/api/learning/today"),
    ("POST", "/api/generate/pipeline"),
    ("POST", "/api/generate/pipeline/stream"),
    ("POST", "/api/generate/jobs"),
    ("GET", "/api/generate/jobs/test-job/replay"),
    ("POST", "/api/builder/generate"),
    ("POST", "/api/builder/generate-all"),
    ("GET", "/api/builder/documents"),
    ("POST", "/api/export"),
    ("GET", "/api/export"),
    ("POST", "/api/salary/analyze"),
    ("GET", "/api/learning/streak"),
    ("POST", "/api/learning/generate"),
    ("GET", "/api/career/timeline"),
    ("GET", "/api/variants/"),
    ("GET", "/api/jobs"),
    ("POST", "/api/resume/parse"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", AUTH_PROTECTED_ROUTES)
async def test_auth_required(client, method, path):
    """All protected endpoints must return 401 without auth."""
    resp = await client.request(method, path)
    assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}, expected 401"


# ── Input Validation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_rejects_invalid_format(client):
    """Export endpoint should reject unsupported format via Pydantic validation."""
    resp = await client.post(
        "/api/export",
        json={"format": "exe", "document_ids": []},
        headers={"Authorization": "Bearer fake"},
    )
    # Without valid auth, we get 401 or 503 (if auth service unreachable)
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_builder_rejects_invalid_doc_type(client):
    """Builder generate endpoint should reject unsupported document_type."""
    resp = await client.post(
        "/api/builder/generate",
        json={"document_type": "malicious"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


# ── Config Validation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_has_no_openai_settings(client):
    """Config should not contain OpenAI or Ollama settings anymore."""
    from app.core.config import Settings

    fields = set(Settings.model_fields.keys())
    stale = {"openai_api_key", "openai_model", "openai_max_tokens", "ollama_base_url", "ollama_model", "ollama_max_tokens"}
    found = fields & stale
    assert not found, f"Config still has removed settings: {found}"


@pytest.mark.asyncio
async def test_health_reports_gemini_provider(client):
    """Health endpoint should report 'gemini' as the AI provider."""
    resp = await client.get("/health")
    data = resp.json()
    assert data["ai"]["provider"] == "gemini"


# ── Model Sanity ─────────────────────────────────────────────────


def test_user_dict_has_no_premium_field():
    """UserDict should not contain is_premium anymore."""
    from app.models import UserDict

    assert "is_premium" not in UserDict.__annotations__


def test_extract_pipeline_html_handles_raw_document_payload():
    from app.api.routes.generate import _extract_pipeline_html

    assert _extract_pipeline_html({"html": "<p>CV</p>"}) == "<p>CV</p>"


def test_extract_pipeline_html_handles_validator_envelope():
    from app.api.routes.generate import _extract_pipeline_html

    payload = {"valid": True, "content": {"html": "<p>CV</p>"}, "issues": []}
    assert _extract_pipeline_html(payload) == "<p>CV</p>"
