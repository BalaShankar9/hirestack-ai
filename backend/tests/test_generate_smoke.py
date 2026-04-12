"""
Phase 1 Smoke Tests — verify the full generate pipeline wiring.

Tests the complete HTTP → chain → response path with mocked AI
responses so we can run without API keys.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.api.deps import get_current_user


# ── Auth override fixtures ──────────────────────────────────────────

FAKE_USER = {"id": "test-user-1", "uid": "test-user-1", "email": "test@example.com"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear in-memory rate-limiter state so tests don't interfere."""
    from app.core.security import limiter
    try:
        limiter.reset()
    except Exception:
        # In-memory backend may not have reset(); clear storage directly
        if hasattr(limiter, "_storage") and hasattr(limiter._storage, "storage"):
            limiter._storage.storage.clear()
    yield


@pytest.fixture
def authed_app(app):
    """Override auth dependency to bypass JWT verification."""
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    yield app
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def aclient(authed_app):
    """Async HTTP client with auth overrides."""
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=authed_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Sample data ─────────────────────────────────────────────────────

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
}

SAMPLE_CV_HTML = "<div><h1>Jane Doe</h1><p>Senior Python Engineer</p></div>"
SAMPLE_CL_HTML = "<div><p>Dear Hiring Manager,</p><p>I am writing to apply...</p></div>"


def _mock_all_chains():
    """Return a context manager that mocks all chain classes used by /generate/pipeline."""
    return [
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") ,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain"),
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain"),
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain"),
        patch("ai_engine.chains.career_consultant.CareerConsultantChain"),
        patch("ai_engine.chains.validator.ValidatorChain"),
        patch("ai_engine.chains.document_discovery.DocumentDiscoveryChain"),
        patch("ai_engine.chains.adaptive_document.AdaptiveDocumentChain"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain"),
    ]


def _wire_happy_path_mocks(
    MockProfiler, MockBenchmark, MockGap, MockDocGen,
    MockConsultant, MockValidator, MockDiscovery, MockIntel,
):
    """Set up all chain mocks for the happy path."""
    MockProfiler.return_value.parse_resume = AsyncMock(return_value=SAMPLE_PROFILE)
    MockBenchmark.return_value.create_ideal_profile = AsyncMock(return_value=SAMPLE_BENCHMARK)
    MockBenchmark.return_value.generate_perfect_application = AsyncMock(
        return_value={"benchmark_documents": {"cv": "<p>Perfect CV</p>"}}
    )
    MockBenchmark.return_value.create_benchmark_cv_html = AsyncMock(return_value="<p>Benchmark CV</p>")
    MockGap.return_value.analyze_gaps = AsyncMock(return_value=SAMPLE_GAP_ANALYSIS)
    MockDocGen.return_value.generate_tailored_cv = AsyncMock(return_value=SAMPLE_CV_HTML)
    MockDocGen.return_value.generate_tailored_cover_letter = AsyncMock(return_value=SAMPLE_CL_HTML)
    MockDocGen.return_value.generate_tailored_personal_statement = AsyncMock(return_value="<p>Statement</p>")
    MockDocGen.return_value.generate_tailored_portfolio = AsyncMock(return_value="<p>Portfolio</p>")
    MockConsultant.return_value.generate_roadmap = AsyncMock(return_value={"steps": []})
    MockValidator.return_value.validate_document = AsyncMock(return_value=(True, {"quality_score": 88, "issues": []}))
    MockDiscovery.return_value.discover = AsyncMock(return_value={
        "required_documents": [
            {"key": "cv", "label": "CV", "priority": "critical"},
            {"key": "cover_letter", "label": "Cover Letter", "priority": "critical"},
        ],
        "optional_documents": [],
        "industry": "technology",
        "tone": "professional",
        "key_themes": ["scalability"],
    })
    MockIntel.return_value.gather_intel = AsyncMock(return_value={
        "confidence": "high",
        "data_sources": ["website"],
        "application_strategy": {"keywords_to_use": ["Python"]},
        "culture_and_values": {"core_values": ["innovation"]},
    })


# ═══════════════════════════════════════════════════════════════════
# HTTP endpoint tests (require authed aclient)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_pipeline_returns_structured_response(aclient):
    """POST /api/generate/pipeline returns all expected fields when AI succeeds."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("ai_engine.chains.document_discovery.DocumentDiscoveryChain") as MockDiscovery,
        patch("ai_engine.chains.adaptive_document.AdaptiveDocumentChain"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
    ):
        _wire_happy_path_mocks(
            MockProfiler, MockBenchmark, MockGap, MockDocGen,
            MockConsultant, MockValidator, MockDiscovery, MockIntel,
        )

        resp = await aclient.post(
            "/api/generate/pipeline",
            json={
                "job_title": "Senior Python Engineer",
                "company": "TechCorp",
                "jd_text": "We are looking for a Senior Python Engineer with 5+ years experience...",
                "resume_text": "Jane Doe - Senior Engineer at TechCorp for 3 years...",
            },
        )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
        data = resp.json()

        assert "scores" in data, f"Missing 'scores': {list(data.keys())}"
        assert "benchmark" in data, f"Missing 'benchmark': {list(data.keys())}"
        assert "gaps" in data, f"Missing 'gaps': {list(data.keys())}"
        assert "cvHtml" in data, f"Missing 'cvHtml': {list(data.keys())}"
        assert "coverLetterHtml" in data, f"Missing 'coverLetterHtml': {list(data.keys())}"

        scores = data["scores"]
        assert "overall" in scores
        assert scores["overall"] > 0

        assert data["cvHtml"], "CV html is empty"
        assert data["coverLetterHtml"], "Cover letter html is empty"


@pytest.mark.asyncio
async def test_generate_pipeline_rejects_empty_job_title(aclient):
    """POST /api/generate/pipeline rejects missing job title."""
    resp = await aclient.post(
        "/api/generate/pipeline",
        json={"job_title": "", "jd_text": "Some JD text"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_generate_pipeline_rejects_empty_jd(aclient):
    """POST /api/generate/pipeline rejects missing JD."""
    resp = await aclient.post(
        "/api/generate/pipeline",
        json={"job_title": "Engineer", "jd_text": ""},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_generate_pipeline_rejects_oversized_jd(aclient):
    """POST /api/generate/pipeline rejects JD larger than 50KB."""
    resp = await aclient.post(
        "/api/generate/pipeline",
        json={"job_title": "Engineer", "jd_text": "x" * 60_000},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_stream_endpoint_returns_sse(aclient):
    """POST /api/generate/pipeline/stream returns text/event-stream."""
    with patch("app.api.routes.generate._RUNTIME_AVAILABLE", False):
        resp = await aclient.post(
            "/api/generate/pipeline/stream",
            json={
                "job_title": "Designer",
                "company": "DesignCo",
                "jd_text": "Looking for a UX designer with Figma experience...",
            },
        )
        # Should start streaming (200) or may error from AI (500 wrapped)
        assert resp.status_code in (200, 500), f"Unexpected status {resp.status_code}"
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            assert "text/event-stream" in content_type, f"Expected SSE, got {content_type}"


@pytest.mark.asyncio
async def test_generate_pipeline_survives_partial_failure(aclient):
    """If cover letter generation fails, CV should still be returned."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("ai_engine.chains.document_discovery.DocumentDiscoveryChain") as MockDiscovery,
        patch("ai_engine.chains.adaptive_document.AdaptiveDocumentChain"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
    ):
        _wire_happy_path_mocks(
            MockProfiler, MockBenchmark, MockGap, MockDocGen,
            MockConsultant, MockValidator, MockDiscovery, MockIntel,
        )
        # Cover letter FAILS
        MockDocGen.return_value.generate_tailored_cover_letter = AsyncMock(
            side_effect=Exception("AI model overloaded")
        )

        resp = await aclient.post(
            "/api/generate/pipeline",
            json={
                "job_title": "Senior Engineer",
                "company": "Co",
                "jd_text": "We need an engineer with Python...",
                "resume_text": "I am an engineer with Python experience...",
            },
        )

        assert resp.status_code == 200, f"Expected 200 with partial failure, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert data.get("cvHtml"), "CV should be present despite cover letter failure"


# ═══════════════════════════════════════════════════════════════════
# Unit tests for helper functions (no HTTP client needed)
# ═══════════════════════════════════════════════════════════════════


def test_format_response_structure():
    """_format_response returns expected top-level keys."""
    from app.api.routes.generate import _format_response
    result = _format_response(
        benchmark_data=SAMPLE_BENCHMARK,
        gap_analysis=SAMPLE_GAP_ANALYSIS,
        roadmap={"steps": []},
        cv_html=SAMPLE_CV_HTML,
        cl_html=SAMPLE_CL_HTML,
        ps_html="<p>Statement</p>",
        portfolio_html="<p>Portfolio</p>",
        validation={},
        keywords=["Python", "AWS"],
        job_title="Engineer",
        benchmark_cv_html="<p>Benchmark</p>",
    )

    assert isinstance(result, dict)
    required_keys = {"scores", "benchmark", "gaps", "learningPlan", "validation", "cvHtml", "coverLetterHtml", "scorecard"}
    missing = required_keys - set(result.keys())
    assert not missing, f"Missing keys in response: {missing}"

    assert result["cvHtml"] == SAMPLE_CV_HTML
    assert result["coverLetterHtml"] == SAMPLE_CL_HTML
    assert result["personalStatementHtml"] == "<p>Statement</p>"
    assert result["portfolioHtml"] == "<p>Portfolio</p>"


def test_extract_pipeline_html_from_string():
    from app.api.routes.generate import _extract_pipeline_html
    assert _extract_pipeline_html("<p>Hello</p>") == "<p>Hello</p>"


def test_extract_pipeline_html_from_dict():
    from app.api.routes.generate import _extract_pipeline_html
    assert _extract_pipeline_html({"html": "<p>Hello</p>"}) == "<p>Hello</p>"


def test_extract_pipeline_html_from_nested_dict():
    from app.api.routes.generate import _extract_pipeline_html
    assert _extract_pipeline_html({"content": {"html": "<p>Hello</p>"}}) == "<p>Hello</p>"


def test_quality_score_collapses_dimensions():
    from app.api.routes.generate import _quality_score_from_scores
    score = _quality_score_from_scores({"impact": 80, "clarity": 90, "tone_match": 70})
    assert 79 < score < 81


def test_quality_score_uses_overall_if_present():
    from app.api.routes.generate import _quality_score_from_scores
    assert _quality_score_from_scores({"overall": 92, "impact": 80}) == 92.0


def test_classify_ai_error_rate_limit():
    from app.api.routes.generate import _classify_ai_error
    result = _classify_ai_error(Exception("Resource exhausted: rate limit"))
    assert result is not None
    assert result["code"] == 429


def test_classify_ai_error_invalid_key():
    from app.api.routes.generate import _classify_ai_error
    result = _classify_ai_error(Exception("API key not valid"))
    assert result is not None
    assert result["code"] == 401


def test_classify_ai_error_unknown():
    from app.api.routes.generate import _classify_ai_error
    assert _classify_ai_error(Exception("Something weird happened")) is None


def test_build_evidence_summary_empty():
    from app.api.routes.generate import _build_evidence_summary
    assert _build_evidence_summary(None) is None


def test_build_evidence_summary_with_data():
    from app.api.routes.generate import _build_evidence_summary

    class FakeResult:
        evidence_ledger = {
            "items": [
                {"tier": "verbatim", "content": "fact 1"},
                {"tier": "derived", "content": "fact 2"},
            ]
        }
        citations = [
            {"classification": "verified", "evidence_ids": ["e1"]},
            {"classification": "fabricated", "evidence_ids": []},
        ]

    result = _build_evidence_summary(FakeResult())
    assert result["evidence_count"] == 2
    assert result["fabricated_count"] == 1
    assert result["tier_distribution"]["verbatim"] == 1


def test_extract_retry_after_seconds():
    from app.api.routes.generate import _extract_retry_after_seconds
    assert _extract_retry_after_seconds("Please retry in 51.7469s.") == 52
    assert _extract_retry_after_seconds("retryDelay': '30s'") == 30
    assert _extract_retry_after_seconds("no hint here") is None


# ═══════════════════════════════════════════════════════════════════
# P1-04 / P1-05 / P1-06 — Timeout, structured errors, partial results
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_timeout_returns_504(aclient):
    """Pipeline that exceeds PIPELINE_TIMEOUT returns 504."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain"),
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain"),
        patch("ai_engine.chains.career_consultant.CareerConsultantChain"),
        patch("ai_engine.chains.validator.ValidatorChain"),
        patch("ai_engine.chains.document_discovery.DocumentDiscoveryChain") as MockDiscovery,
        patch("ai_engine.chains.adaptive_document.AdaptiveDocumentChain"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
        patch("app.api.routes.generate.PIPELINE_TIMEOUT", 0.01),  # 10ms timeout
    ):
        # Discovery succeeds fast
        MockDiscovery.return_value.discover = AsyncMock(return_value={
            "required_documents": [{"key": "cv", "label": "CV", "priority": "critical"}],
            "optional_documents": [],
        })
        MockIntel.return_value.gather_intel = AsyncMock(return_value={})

        # Resume parsing hangs forever
        async def _hang(*a, **kw):
            await asyncio.sleep(999)
        MockProfiler.return_value.parse_resume = _hang
        MockBenchmark.return_value.create_ideal_profile = _hang

        resp = await aclient.post(
            "/api/generate/pipeline",
            json={
                "job_title": "Engineer",
                "company": "Co",
                "jd_text": "We need an engineer...",
                "resume_text": "I am an engineer...",
            },
        )
        assert resp.status_code == 504, f"Expected 504 timeout, got {resp.status_code}"
        assert "too long" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_partial_failure_reports_failed_modules(aclient):
    """When cover letter fails, response includes failedModules metadata."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
        patch("ai_engine.chains.document_discovery.DocumentDiscoveryChain") as MockDiscovery,
        patch("ai_engine.chains.adaptive_document.AdaptiveDocumentChain"),
        patch("ai_engine.chains.company_intel.CompanyIntelChain") as MockIntel,
    ):
        _wire_happy_path_mocks(
            MockProfiler, MockBenchmark, MockGap, MockDocGen,
            MockConsultant, MockValidator, MockDiscovery, MockIntel,
        )
        # Cover letter FAILS
        MockDocGen.return_value.generate_tailored_cover_letter = AsyncMock(
            side_effect=Exception("Model rate limited")
        )

        resp = await aclient.post(
            "/api/generate/pipeline",
            json={
                "job_title": "Senior Engineer",
                "company": "Co",
                "jd_text": "We need an engineer with Python...",
                "resume_text": "I am an engineer with Python experience...",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("cvHtml"), "CV should succeed"
        assert data.get("coverLetterHtml") == "", "Failed CL should be empty string"
        # P1-06: failedModules should list the failure
        failed = data.get("failedModules", [])
        assert len(failed) >= 1, f"Expected at least 1 failed module, got {failed}"
        failed_names = [m["module"] for m in failed]
        assert "cover_letter" in failed_names, f"Expected 'cover_letter' in failures: {failed_names}"


def test_pipeline_timeout_constant_exists():
    """PIPELINE_TIMEOUT constant is defined."""
    from app.api.routes.generate import PIPELINE_TIMEOUT
    assert PIPELINE_TIMEOUT == 300  # 5 minutes
