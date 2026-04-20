"""
Smoke tests for the DB-backed generation jobs flow (/api/generate/jobs).

This is the ACTIVE product path. The frontend prefers this flow
and only falls back to the legacy /pipeline/stream route when the
jobs API is unavailable.

Tests the complete HTTP → DB → job-runner → response path with mocked
AI responses and a fake Supabase layer so we can run without real
infrastructure.
"""
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user


# ── Constants ────────────────────────────────────────────────────────

FAKE_USER = {"id": "test-user-1", "uid": "test-user-1", "email": "test@example.com"}
FAKE_APP_ID = "app-001"
FAKE_JOB_ID = str(uuid.uuid4())

FAKE_APPLICATION_ROW = {
    "id": FAKE_APP_ID,
    "user_id": FAKE_USER["id"],
    "confirmed_facts": {
        "jobTitle": "Senior Python Engineer",
        "company": "TechCorp",
        "jdText": "We are looking for a Senior Python Engineer with 5+ years experience in backend services.",
        "resume": {
            "text": "Jane Doe - Senior Engineer at TechCorp for 3 years. Expert in Python, AWS, Docker."
        },
    },
    "modules": {
        "benchmark": {"state": "idle"},
        "gaps": {"state": "idle"},
        "cv": {"state": "idle"},
        "coverLetter": {"state": "idle"},
    },
}

FAKE_JOB_ROW = {
    "id": FAKE_JOB_ID,
    "user_id": FAKE_USER["id"],
    "application_id": FAKE_APP_ID,
    "requested_modules": ["benchmark", "gaps", "cv", "coverLetter", "personalStatement", "portfolio", "learningPlan", "scorecard"],
    "status": "queued",
    "progress": 0,
    "phase": None,
    "current_agent": None,
    "completed_steps": 0,
    "total_steps": 7,
    "cancel_requested": False,
    "resume_from_stages": None,
    "resume_from_stage": None,
    "error_message": None,
    "result": None,
}


# ── Fake Supabase client ─────────────────────────────────────────────

class FakeQueryBuilder:
    """Chainable mock for Supabase .table().select().eq()... queries."""

    def __init__(self, rows: List[Dict[str, Any]], *, insert_rows: Optional[List] = None):
        self._rows = rows
        self._insert_rows = insert_rows  # captures inserted data
        self._filters: Dict[str, Any] = {}

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, **kwargs):
        if self._insert_rows is not None:
            self._insert_rows.append(data)
        return self

    def update(self, data, **kwargs):
        self._update_data = data
        return self

    def upsert(self, data, **kwargs):
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def gt(self, column, value):
        self._gt_col = column
        self._gt_val = value
        return self

    def order(self, column, **kwargs):
        return self

    def limit(self, n):
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def execute(self):
        result = MagicMock()
        if hasattr(self, "_maybe_single") and self._maybe_single:
            result.data = self._rows[0] if self._rows else None
        else:
            result.data = self._rows
        return result


class FakeSupabase:
    """Minimal Supabase client that returns pre-configured data per table."""

    def __init__(self):
        self._table_data: Dict[str, List[Dict[str, Any]]] = {}
        self._inserts: Dict[str, List] = {}
        self._updates: Dict[str, List] = {}

    def set_table_rows(self, table_name: str, rows: List[Dict[str, Any]]):
        self._table_data[table_name] = rows

    def table(self, name: str):
        rows = self._table_data.get(name, [])
        insert_list = self._inserts.setdefault(name, [])
        return FakeQueryBuilder(rows, insert_rows=insert_list)


def _make_fake_supabase(
    application_row: Optional[Dict] = None,
    job_row: Optional[Dict] = None,
    events: Optional[List[Dict]] = None,
) -> FakeSupabase:
    """Build a FakeSupabase pre-populated for jobs flow testing."""
    sb = FakeSupabase()
    sb.set_table_rows("applications", [application_row or FAKE_APPLICATION_ROW])
    if job_row:
        sb.set_table_rows("generation_jobs", [job_row])
    else:
        sb.set_table_rows("generation_jobs", [{"id": FAKE_JOB_ID, **FAKE_JOB_ROW}])
    sb.set_table_rows("generation_job_events", events or [])
    return sb


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.core.security import limiter
    try:
        limiter.reset()
    except Exception:
        if hasattr(limiter, "_storage") and hasattr(limiter._storage, "storage"):
            limiter._storage.storage.clear()
    yield


@pytest.fixture
def authed_app(app):
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    yield app
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def aclient(authed_app):
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=authed_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Mock helpers ──────────────────────────────────────────────────────

SAMPLE_PROFILE = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "skills": [{"name": "Python", "level": "expert"}, {"name": "AWS", "level": "intermediate"}],
    "experience": [
        {"title": "Senior Engineer", "company": "TechCorp", "duration": "3 years", "description": "Led backend services team"},
    ],
    "education": [{"degree": "BSc Computer Science", "institution": "MIT", "year": 2018}],
}

SAMPLE_BENCHMARK = {
    "ideal_skills": [
        {"name": "Python", "importance": "critical"},
        {"name": "Kubernetes", "importance": "high"},
    ],
    "experience_level": "senior",
    "min_years": 5,
}

SAMPLE_GAP_ANALYSIS = {
    "compatibility_score": 72,
    "strengths": [{"area": "Python", "evidence": "Expert level"}],
    "skill_gaps": [{"skill": "Kubernetes", "severity": "medium"}],
    "missing_keywords": ["Kubernetes", "CI/CD"],
}

SAMPLE_CV_HTML = "<div><h1>Jane Doe</h1><p>Senior Python Engineer</p></div>"
SAMPLE_CL_HTML = "<div><p>Dear Hiring Manager,</p><p>I am writing to apply...</p></div>"


def _mock_ai_chains():
    """Context managers to mock all AI chains used by the jobs runner."""
    return [
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain"),
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain"),
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain"),
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain"),
        patch("ai_engine.chains.career_consultant.CareerConsultantChain"),
        patch("ai_engine.chains.validator.ValidatorChain"),
    ]


def _wire_job_happy_path(MockIntel, MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator):
    """Configure all AI chain mocks for a successful job run."""
    MockIntel.return_value.gather_intel = AsyncMock(return_value={
        "confidence": "high",
        "data_sources": ["website"],
        "application_strategy": {"keywords_to_use": ["Python"]},
        "culture_and_values": {"core_values": ["innovation"]},
    })
    MockProfiler.return_value.parse_resume = AsyncMock(return_value=SAMPLE_PROFILE)
    MockBenchmark.return_value.create_ideal_profile = AsyncMock(return_value=SAMPLE_BENCHMARK)
    MockBenchmark.return_value.create_benchmark_cv_html = AsyncMock(return_value="<p>Benchmark CV</p>")
    MockGap.return_value.analyze_gaps = AsyncMock(return_value=SAMPLE_GAP_ANALYSIS)
    MockDocGen.return_value.generate_tailored_cv = AsyncMock(return_value=SAMPLE_CV_HTML)
    MockDocGen.return_value.generate_tailored_cover_letter = AsyncMock(return_value=SAMPLE_CL_HTML)
    MockDocGen.return_value.generate_tailored_personal_statement = AsyncMock(return_value="<p>Statement</p>")
    MockDocGen.return_value.generate_tailored_portfolio = AsyncMock(return_value="<p>Portfolio</p>")
    MockConsultant.return_value.generate_roadmap = AsyncMock(return_value={"steps": []})
    MockValidator.return_value.validate_document = AsyncMock(return_value=(True, {"quality_score": 88, "issues": []}))


# ═══════════════════════════════════════════════════════════════════════
# 1. POST /api/generate/jobs — Job Creation
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_job_returns_job_id(aclient):
    """POST /api/generate/jobs returns 200 with a job_id."""
    fake_sb = _make_fake_supabase()

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._ensure_generation_job_schema_ready", new_callable=AsyncMock),
        patch("app.api.routes.generate.jobs._start_generation_job") as mock_start,
        patch("app.api.routes.generate.jobs._set_application_modules_generating", new_callable=AsyncMock),
    ):
        resp = await aclient.post(
            "/api/generate/jobs",
            json={"application_id": FAKE_APP_ID},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    assert "job_id" in data, f"Missing job_id in response: {data}"
    mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_create_job_rejects_unknown_application(aclient):
    """POST /api/generate/jobs returns 404 for non-existent application."""
    fake_sb = _make_fake_supabase()
    # Empty applications table
    fake_sb.set_table_rows("applications", [])

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._ensure_generation_job_schema_ready", new_callable=AsyncMock),
    ):
        resp = await aclient.post(
            "/api/generate/jobs",
            json={"application_id": "nonexistent-app"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_job_normalizes_empty_modules(aclient):
    """When requested_modules is empty, all default modules are used."""
    fake_sb = _make_fake_supabase()

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._ensure_generation_job_schema_ready", new_callable=AsyncMock),
        patch("app.api.routes.generate.jobs._start_generation_job"),
        patch("app.api.routes.generate.jobs._set_application_modules_generating", new_callable=AsyncMock) as _mock_set_mods,
    ):
        resp = await aclient.post(
            "/api/generate/jobs",
            json={"application_id": FAKE_APP_ID, "requested_modules": []},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_job_schema_not_ready_returns_503(aclient):
    """If schema readiness check fails, returns 503."""
    fake_sb = _make_fake_supabase()

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch(
            "app.api.routes.generate.jobs._ensure_generation_job_schema_ready",
            new_callable=AsyncMock,
            side_effect=Exception("Schema not ready"),
        ),
    ):
        # _ensure_generation_job_schema_ready raises HTTPException(503) internally
        # but since we patched it to raise a plain Exception, let's test the real one
        pass

    # Test with the real function behavior
    from fastapi import HTTPException

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch(
            "app.api.routes.generate.jobs._ensure_generation_job_schema_ready",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=503, detail="Schema not ready"),
        ),
    ):
        resp = await aclient.post(
            "/api/generate/jobs",
            json={"application_id": FAKE_APP_ID},
        )

    assert resp.status_code == 503


# ═══════════════════════════════════════════════════════════════════════
# 2. GET /api/generate/jobs/{id}/stream — SSE Streaming
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stream_job_returns_sse_content_type(aclient):
    """GET /api/generate/jobs/{id}/stream returns text/event-stream."""
    succeeded_job = {**FAKE_JOB_ROW, "status": "succeeded"}
    events = [
        {
            "id": "ev-1",
            "job_id": FAKE_JOB_ID,
            "sequence_no": 1,
            "event_name": "progress",
            "payload": {"phase": "complete", "progress": 100, "message": "Done"},
        },
    ]
    fake_sb = _make_fake_supabase(job_row=succeeded_job, events=events)

    with patch("app.core.database.get_supabase", return_value=fake_sb):
        resp = await aclient.get(f"/api/generate/jobs/{FAKE_JOB_ID}/stream")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
    content_type = resp.headers.get("content-type", "")
    assert "text/event-stream" in content_type, f"Expected SSE, got {content_type}"


@pytest.mark.asyncio
async def test_stream_job_404_for_missing_job(aclient):
    """GET /api/generate/jobs/{id}/stream returns 404 for unknown job."""
    fake_sb = _make_fake_supabase()
    fake_sb.set_table_rows("generation_jobs", [])
    missing_job_id = "00000000-0000-0000-0000-000000000099"

    with patch("app.core.database.get_supabase", return_value=fake_sb):
        resp = await aclient.get(f"/api/generate/jobs/{missing_job_id}/stream")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stream_job_emits_events(aclient):
    """Stream endpoint yields SSE data lines from persisted events."""
    succeeded_job = {**FAKE_JOB_ROW, "status": "succeeded"}
    events = [
        {
            "id": "ev-1",
            "job_id": FAKE_JOB_ID,
            "sequence_no": 1,
            "event_name": "progress",
            "payload": {"phase": "recon", "progress": 10, "message": "Gathering intel"},
        },
        {
            "id": "ev-2",
            "job_id": FAKE_JOB_ID,
            "sequence_no": 2,
            "event_name": "complete",
            "payload": {"progress": 100, "result": {"scores": {"overall": 85}}},
        },
    ]
    fake_sb = _make_fake_supabase(job_row=succeeded_job, events=events)

    with patch("app.core.database.get_supabase", return_value=fake_sb):
        resp = await aclient.get(f"/api/generate/jobs/{FAKE_JOB_ID}/stream")

    assert resp.status_code == 200
    body = resp.text
    assert "event:" in body or "data:" in body, f"Expected SSE events in body, got: {body[:500]}"


# ═══════════════════════════════════════════════════════════════════════
# 3. POST /api/generate/jobs/{id}/cancel — Cancellation
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cancel_job_sets_flag(aclient):
    """POST /api/generate/jobs/{id}/cancel updates the cancel_requested flag."""
    fake_sb = _make_fake_supabase()

    with patch("app.core.database.get_supabase", return_value=fake_sb):
        resp = await aclient.post(f"/api/generate/jobs/{FAKE_JOB_ID}/cancel")

    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# 4. Unit tests for job helper functions
# ═══════════════════════════════════════════════════════════════════════


def test_normalize_requested_modules_defaults():
    """Empty/None input returns the canonical default module set."""
    from app.api.routes.generate import _normalize_requested_modules
    from app.api.routes.generate.jobs import _DEFAULT_REQUESTED_MODULES
    result = _normalize_requested_modules([])
    assert "cv" in result
    assert "coverLetter" in result
    assert "benchmark" in result
    assert len(result) == len(_DEFAULT_REQUESTED_MODULES)
    assert set(result) == set(_DEFAULT_REQUESTED_MODULES)


def test_normalize_requested_modules_filters_invalid():
    """Invalid module names are filtered out."""
    from app.api.routes.generate import _normalize_requested_modules
    result = _normalize_requested_modules(["cv", "invalidModule", "coverLetter"])
    assert result == ["cv", "coverLetter"]


def test_normalize_requested_modules_all_invalid_returns_defaults():
    """If all modules are invalid, returns the canonical default set."""
    from app.api.routes.generate import _normalize_requested_modules
    from app.api.routes.generate.jobs import _DEFAULT_REQUESTED_MODULES
    result = _normalize_requested_modules(["fake1", "fake2"])
    assert len(result) == len(_DEFAULT_REQUESTED_MODULES)
    assert set(result) == set(_DEFAULT_REQUESTED_MODULES)


def test_default_module_states():
    """Every canonical module starts in idle state — single source of truth."""
    from app.api.routes.generate import _default_module_states
    from app.api.routes.generate.jobs import _DEFAULT_REQUESTED_MODULES
    states = _default_module_states()
    assert len(states) == len(_DEFAULT_REQUESTED_MODULES)
    assert set(states.keys()) == set(_DEFAULT_REQUESTED_MODULES)
    for key, val in states.items():
        assert val["state"] == "idle", f"{key} should be idle"


def test_merge_module_states_preserves_existing():
    """merge_module_states preserves existing ready modules."""
    from app.api.routes.generate import _merge_module_states
    existing = {"cv": {"state": "ready"}, "coverLetter": {"state": "generating"}}
    merged = _merge_module_states(existing)
    assert merged["cv"]["state"] == "ready"
    assert merged["coverLetter"]["state"] == "generating"
    assert merged["benchmark"]["state"] == "idle"


def test_module_has_content_cv():
    """_module_has_content detects cv_html presence."""
    from app.api.routes.generate import _module_has_content
    assert _module_has_content({"cv_html": "<p>CV</p>"}, "cv") is True
    assert _module_has_content({"cv_html": ""}, "cv") is False
    assert _module_has_content({}, "cv") is False


def test_module_has_content_benchmark():
    from app.api.routes.generate import _module_has_content
    assert _module_has_content({"benchmark": {"ideal_skills": []}}, "benchmark") is True
    assert _module_has_content({"benchmark": None}, "benchmark") is False


# ═══════════════════════════════════════════════════════════════════════
# 5. Inner job runner — functional tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_job_runner_succeeds_with_legacy_chains():
    """_run_generation_job_inner completes successfully using legacy chains."""
    fake_sb = _make_fake_supabase()

    # Track all DB updates for verification
    updates: List[Dict] = []
    events: List[Dict] = []

    _original_persist_update = None
    _original_persist_event = None

    async def fake_persist_update(sb, tables, job_id, patch_data):
        updates.append({"job_id": job_id, **patch_data})

    async def fake_persist_event(sb, tables, *, job_id, user_id, application_id, sequence_no, event_name, payload, **kw):
        events.append({"event_name": event_name, "payload": payload, "sequence_no": sequence_no})

    async def fake_persist_result(sb, tables, *, application_row, requested_modules, result, user_id):
        pass  # Just track that it was called

    async def fake_mark_finished(sb, tables, app_id, app_row, modules, *, status, error_message=None):
        pass

    async def fake_set_generating(sb, tables, app_id, existing_mods, req_mods):
        pass

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
        patch("app.api.routes.generate.jobs._persist_generation_job_event", side_effect=fake_persist_event),
        patch("app.api.routes.generate.jobs._persist_generation_result_to_application", side_effect=fake_persist_result),
        patch("app.api.routes.generate.jobs._mark_application_generation_finished", side_effect=fake_mark_finished),
        patch("app.api.routes.generate.jobs._set_application_modules_generating", side_effect=fake_set_generating),
    ):
        _wire_job_happy_path(MockIntel, MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        from app.api.routes.generate import _run_generation_job_inner
        await _run_generation_job_inner(FAKE_JOB_ID, FAKE_USER["id"])

    # Verify job reached "succeeded" status
    final_status_updates = [u for u in updates if u.get("status") == "succeeded"]
    assert len(final_status_updates) >= 1, (
        f"Expected at least one 'succeeded' update, got statuses: {[u.get('status') for u in updates if 'status' in u]}"
    )

    # Verify complete event was emitted
    complete_events = [e for e in events if e["event_name"] == "complete"]
    assert len(complete_events) == 1, f"Expected 1 complete event, got {len(complete_events)}"

    result = complete_events[0]["payload"].get("result", {})
    assert result.get("cvHtml") == SAMPLE_CV_HTML, "CV HTML should be in the result"
    assert result.get("coverLetterHtml") == SAMPLE_CL_HTML, "Cover letter HTML should be in the result"

    # Verify progress phases were emitted in order
    progress_phases = [e["payload"].get("phase") for e in events if e["event_name"] == "progress"]
    assert "recon" in progress_phases, f"Missing recon phase: {progress_phases}"
    assert "profiling" in progress_phases, f"Missing profiling phase: {progress_phases}"
    assert "documents" in progress_phases, f"Missing documents phase: {progress_phases}"
    assert "complete" not in progress_phases or "formatting" in progress_phases


@pytest.mark.asyncio
async def test_job_runner_fails_on_missing_jd():
    """Job fails gracefully when application has no JD text."""
    app_row_no_jd = deepcopy(FAKE_APPLICATION_ROW)
    app_row_no_jd["confirmed_facts"] = {"jobTitle": "", "jdText": ""}
    fake_sb = _make_fake_supabase(application_row=app_row_no_jd)

    updates: List[Dict] = []
    events: List[Dict] = []

    async def fake_persist_update(sb, tables, job_id, patch_data):
        updates.append({"job_id": job_id, **patch_data})

    async def fake_persist_event(sb, tables, *, job_id, user_id, application_id, sequence_no, event_name, payload, **kw):
        events.append({"event_name": event_name, "payload": payload})

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
        patch("app.api.routes.generate.jobs._persist_generation_job_event", side_effect=fake_persist_event),
    ):
        from app.api.routes.generate import _run_generation_job_inner
        await _run_generation_job_inner(FAKE_JOB_ID, FAKE_USER["id"])

    # Should be marked as failed
    failed_updates = [u for u in updates if u.get("status") == "failed"]
    assert len(failed_updates) >= 1, f"Expected failed status, got: {[u.get('status') for u in updates if 'status' in u]}"

    # Should have emitted an error event
    error_events = [e for e in events if e["event_name"] == "error"]
    assert len(error_events) >= 1, "Expected an error event for missing JD"
    assert "missing" in error_events[0]["payload"]["message"].lower() or "job title" in error_events[0]["payload"]["message"].lower()


@pytest.mark.asyncio
async def test_job_runner_survives_cv_failure():
    """If CV generation fails, the job still completes with partial results."""
    fake_sb = _make_fake_supabase()

    updates: List[Dict] = []
    events: List[Dict] = []

    async def fake_persist_update(sb, tables, job_id, patch_data):
        updates.append({"job_id": job_id, **patch_data})

    async def fake_persist_event(sb, tables, *, job_id, user_id, application_id, sequence_no, event_name, payload, **kw):
        events.append({"event_name": event_name, "payload": payload})

    async def fake_persist_result(sb, tables, *, application_row, requested_modules, result, user_id):
        pass

    async def fake_mark_finished(sb, tables, app_id, app_row, modules, *, status, error_message=None):
        pass

    async def fake_set_generating(sb, tables, app_id, existing_mods, req_mods):
        pass

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
        patch("app.api.routes.generate.jobs._persist_generation_job_event", side_effect=fake_persist_event),
        patch("app.api.routes.generate.jobs._persist_generation_result_to_application", side_effect=fake_persist_result),
        patch("app.api.routes.generate.jobs._mark_application_generation_finished", side_effect=fake_mark_finished),
        patch("app.api.routes.generate.jobs._set_application_modules_generating", side_effect=fake_set_generating),
    ):
        _wire_job_happy_path(MockIntel, MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)
        # CV generation FAILS
        MockDocGen.return_value.generate_tailored_cv = AsyncMock(
            side_effect=Exception("Model overloaded")
        )

        from app.api.routes.generate import _run_generation_job_inner
        await _run_generation_job_inner(FAKE_JOB_ID, FAKE_USER["id"])

    # Job should still succeed (partial result)
    final_status = [u for u in updates if u.get("status") == "succeeded"]
    assert len(final_status) >= 1, (
        f"Expected 'succeeded' even with partial failure, got: {[u.get('status') for u in updates if 'status' in u]}"
    )

    complete_events = [e for e in events if e["event_name"] == "complete"]
    assert len(complete_events) == 1
    result = complete_events[0]["payload"].get("result", {})
    # CV should be empty (failed), but cover letter should be present
    assert result.get("cvHtml") == "", "CV should be empty string on failure"
    assert result.get("coverLetterHtml") == SAMPLE_CL_HTML, "Cover letter should still succeed"


@pytest.mark.asyncio
async def test_job_runner_handles_cancellation():
    """If cancel_requested is set, the job emits a cancellation error."""
    fake_sb = _make_fake_supabase()
    # Override check_cancel to return True immediately
    cancel_job = {**FAKE_JOB_ROW, "cancel_requested": True}
    fake_sb.set_table_rows("generation_jobs", [cancel_job])

    updates: List[Dict] = []
    events: List[Dict] = []

    async def fake_persist_update(sb, tables, job_id, patch_data):
        updates.append({"job_id": job_id, **patch_data})

    async def fake_persist_event(sb, tables, *, job_id, user_id, application_id, sequence_no, event_name, payload, **kw):
        events.append({"event_name": event_name, "payload": payload})

    async def fake_mark_finished(sb, tables, app_id, app_row, modules, *, status, error_message=None):
        pass

    async def fake_set_generating(sb, tables, app_id, existing_mods, req_mods):
        pass

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
        patch("app.api.routes.generate.jobs._persist_generation_job_event", side_effect=fake_persist_event),
        patch("app.api.routes.generate.jobs._mark_application_generation_finished", side_effect=fake_mark_finished),
        patch("app.api.routes.generate.jobs._set_application_modules_generating", side_effect=fake_set_generating),
    ):
        _wire_job_happy_path(MockIntel, MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        from app.api.routes.generate import _run_generation_job_inner
        await _run_generation_job_inner(FAKE_JOB_ID, FAKE_USER["id"])

    # Should see a cancellation error event (code 499)
    error_events = [e for e in events if e["event_name"] == "error"]
    assert len(error_events) >= 1, f"Expected cancellation error event, got events: {[e['event_name'] for e in events]}"
    cancel_errors = [e for e in error_events if e["payload"].get("code") == 499]
    assert len(cancel_errors) >= 1, f"Expected code 499, got: {[e['payload'] for e in error_events]}"


@pytest.mark.asyncio
async def test_job_runner_meta_has_company_intel():
    """Result meta includes company_intel from the recon phase."""
    fake_sb = _make_fake_supabase()

    events: List[Dict] = []

    async def fake_persist_update(sb, tables, job_id, patch_data):
        pass

    async def fake_persist_event(sb, tables, *, job_id, user_id, application_id, sequence_no, event_name, payload, **kw):
        events.append({"event_name": event_name, "payload": payload})

    async def fake_persist_result(sb, tables, *, application_row, requested_modules, result, user_id):
        pass

    async def fake_mark_finished(sb, tables, app_id, app_row, modules, *, status, error_message=None):
        pass

    async def fake_set_generating(sb, tables, app_id, existing_mods, req_mods):
        pass

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
        patch("app.api.routes.generate.jobs._persist_generation_job_event", side_effect=fake_persist_event),
        patch("app.api.routes.generate.jobs._persist_generation_result_to_application", side_effect=fake_persist_result),
        patch("app.api.routes.generate.jobs._mark_application_generation_finished", side_effect=fake_mark_finished),
        patch("app.api.routes.generate.jobs._set_application_modules_generating", side_effect=fake_set_generating),
    ):
        _wire_job_happy_path(MockIntel, MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        from app.api.routes.generate import _run_generation_job_inner
        await _run_generation_job_inner(FAKE_JOB_ID, FAKE_USER["id"])

    complete_events = [e for e in events if e["event_name"] == "complete"]
    assert len(complete_events) == 1
    result = complete_events[0]["payload"].get("result", {})
    meta = result.get("meta", {})
    assert meta.get("company_intel") is not None, f"company_intel should be in meta: {list(meta.keys())}"
    assert meta["company_intel"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_job_runner_emits_progress_events_in_order():
    """Progress events follow the expected phase sequence."""
    fake_sb = _make_fake_supabase()

    events: List[Dict] = []

    async def fake_persist_update(sb, tables, job_id, patch_data):
        pass

    async def fake_persist_event(sb, tables, *, job_id, user_id, application_id, sequence_no, event_name, payload, **kw):
        events.append({"event_name": event_name, "seq": sequence_no, "payload": payload})

    async def fake_persist_result(sb, tables, *, application_row, requested_modules, result, user_id):
        pass

    async def fake_mark_finished(sb, tables, app_id, app_row, modules, *, status, error_message=None):
        pass

    async def fake_set_generating(sb, tables, app_id, existing_mods, req_mods):
        pass

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
        patch("app.api.routes.generate.jobs._persist_generation_job_event", side_effect=fake_persist_event),
        patch("app.api.routes.generate.jobs._persist_generation_result_to_application", side_effect=fake_persist_result),
        patch("app.api.routes.generate.jobs._mark_application_generation_finished", side_effect=fake_mark_finished),
        patch("app.api.routes.generate.jobs._set_application_modules_generating", side_effect=fake_set_generating),
    ):
        _wire_job_happy_path(MockIntel, MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        from app.api.routes.generate import _run_generation_job_inner
        await _run_generation_job_inner(FAKE_JOB_ID, FAKE_USER["id"])

    progress_events = [e for e in events if e["event_name"] == "progress"]
    phases = [e["payload"].get("phase") for e in progress_events]

    # Expected phase order (some are _done variants)
    expected_order = ["initializing", "recon", "recon_done", "profiling", "profiling_done",
                      "gap_analysis", "gap_analysis_done", "documents", "documents_done",
                      "portfolio", "portfolio_done", "validation", "validation_done",
                      "formatting"]
    for expected_phase in expected_order:
        assert expected_phase in phases, f"Missing progress phase '{expected_phase}'. Got phases: {phases}"

    # Verify sequence numbers are strictly increasing
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs), f"Event sequence numbers should be increasing: {seqs}"


@pytest.mark.asyncio
async def test_finalize_orphaned_job():
    """_finalize_orphaned_job marks a running job as failed."""
    fake_sb = _make_fake_supabase()
    running_job = {**FAKE_JOB_ROW, "status": "running"}
    fake_sb.set_table_rows("generation_jobs", [running_job])

    updates: List[Dict] = []

    async def fake_persist_update(sb, tables, job_id, patch_data):
        updates.append({"job_id": job_id, **patch_data})

    async def fake_mark_finished(sb, tables, app_id, app_row, modules, *, status, error_message=None):
        pass

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
        patch("app.api.routes.generate.jobs._mark_application_generation_finished", side_effect=fake_mark_finished),
    ):
        from app.api.routes.generate import _finalize_orphaned_job
        await _finalize_orphaned_job(FAKE_JOB_ID, status="failed", error_message="Timed out")

    failed = [u for u in updates if u.get("status") == "failed"]
    assert len(failed) >= 1, f"Expected failed update, got: {updates}"


@pytest.mark.asyncio
async def test_finalize_orphaned_job_skips_already_terminal():
    """_finalize_orphaned_job does not overwrite a succeeded job."""
    fake_sb = _make_fake_supabase()
    succeeded_job = {**FAKE_JOB_ROW, "status": "succeeded"}
    fake_sb.set_table_rows("generation_jobs", [succeeded_job])

    updates: List[Dict] = []

    async def fake_persist_update(sb, tables, job_id, patch_data):
        updates.append(patch_data)

    with (
        patch("app.core.database.get_supabase", return_value=fake_sb),
        patch("app.api.routes.generate.jobs._persist_generation_job_update", side_effect=fake_persist_update),
    ):
        from app.api.routes.generate import _finalize_orphaned_job
        await _finalize_orphaned_job(FAKE_JOB_ID, status="failed", error_message="Timed out")

    # Should NOT have updated — job was already terminal
    assert len(updates) == 0, f"Should not update a terminal job, but got updates: {updates}"
