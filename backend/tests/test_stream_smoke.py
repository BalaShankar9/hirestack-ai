"""
P1-02 Smoke Tests — /api/generate/pipeline/stream SSE endpoint.

Validates both the legacy (direct-chain) fallback and the agent-pipeline
path with mocked AI so we can run without API keys.

The SSE stream is the frontend's fallback when the DB-backed /jobs
flow is unavailable. Both code paths must emit correct SSE events.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user


# ── Constants ────────────────────────────────────────────────────────

FAKE_USER = {"id": "test-user-1", "uid": "test-user-1", "email": "test@example.com"}

SAMPLE_PROFILE = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "skills": [{"name": "Python", "level": "expert"}, {"name": "AWS", "level": "intermediate"}],
    "experience": [
        {"title": "Senior Engineer", "company": "TechCorp", "duration": "3 years", "description": "Led backend"},
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

VALID_STREAM_REQUEST = {
    "job_title": "Senior Python Engineer",
    "company": "TechCorp",
    "jd_text": "We are looking for a Senior Python Engineer with 5+ years experience in backend services.",
    "resume_text": "Jane Doe - Senior Engineer at TechCorp for 3 years. Expert in Python, AWS, Docker.",
}


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


# ── Helpers ───────────────────────────────────────────────────────────

def parse_sse_events(body: str) -> List[Dict[str, Any]]:
    """Parse SSE text into a list of {event, data} dicts."""
    events = []
    current_event = None
    current_data = []

    for line in body.split("\n"):
        if line.startswith("event:"):
            if current_event and current_data:
                raw = "\n".join(current_data)
                try:
                    events.append({"event": current_event, "data": json.loads(raw)})
                except json.JSONDecodeError:
                    events.append({"event": current_event, "data": raw})
            current_event = line[len("event:"):].strip()
            current_data = []
        elif line.startswith("data:"):
            current_data.append(line[len("data:"):].strip())
        elif line.strip() == "" and current_event and current_data:
            raw = "\n".join(current_data)
            try:
                events.append({"event": current_event, "data": json.loads(raw)})
            except json.JSONDecodeError:
                events.append({"event": current_event, "data": raw})
            current_event = None
            current_data = []

    # Handle trailing event
    if current_event and current_data:
        raw = "\n".join(current_data)
        try:
            events.append({"event": current_event, "data": json.loads(raw)})
        except json.JSONDecodeError:
            events.append({"event": current_event, "data": raw})

    return events


def _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator):
    """Configure chain mocks for the legacy stream path."""
    MockProfiler.return_value.parse_resume = AsyncMock(return_value=SAMPLE_PROFILE)
    MockBenchmark.return_value.create_ideal_profile = AsyncMock(return_value=SAMPLE_BENCHMARK)
    MockBenchmark.return_value.create_benchmark_cv_html = AsyncMock(return_value="<p>Benchmark</p>")
    MockGap.return_value.analyze_gaps = AsyncMock(return_value=SAMPLE_GAP_ANALYSIS)
    MockDocGen.return_value.generate_tailored_cv = AsyncMock(return_value=SAMPLE_CV_HTML)
    MockDocGen.return_value.generate_tailored_cover_letter = AsyncMock(return_value=SAMPLE_CL_HTML)
    MockDocGen.return_value.generate_tailored_personal_statement = AsyncMock(return_value="<p>Statement</p>")
    MockDocGen.return_value.generate_tailored_portfolio = AsyncMock(return_value="<p>Portfolio</p>")
    MockConsultant.return_value.generate_roadmap = AsyncMock(return_value={"steps": []})
    MockValidator.return_value.validate_document = AsyncMock(return_value=(True, {"quality_score": 88, "issues": []}))


@dataclass
class FakePipelineResult:
    """Minimal stand-in for PipelineResult from the agent orchestrator."""
    content: Any = ""
    quality_scores: dict = field(default_factory=dict)
    optimization_report: dict = field(default_factory=dict)
    fact_check_report: dict = field(default_factory=dict)
    iterations_used: int = 1
    total_latency_ms: int = 500
    trace_id: str = "test-trace-001"
    evidence_ledger: Optional[dict] = None
    citations: Optional[list] = None
    workflow_state: Optional[dict] = None
    validation_report: Optional[dict] = None
    final_analysis_report: Optional[dict] = None


def _make_fake_pipeline(return_content: Any):
    """Create a mock pipeline object with .execute() returning a FakePipelineResult."""
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=FakePipelineResult(content=return_content))
    pipe.db = None
    pipe.event_store = None
    return pipe


# ═══════════════════════════════════════════════════════════════════════
# 1. Input Validation (shared with /pipeline)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stream_rejects_empty_job_title(aclient):
    """POST /api/generate/pipeline/stream rejects missing job title."""
    resp = await aclient.post(
        "/api/generate/pipeline/stream",
        json={"job_title": "", "jd_text": "Some JD text"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stream_rejects_empty_jd(aclient):
    """POST /api/generate/pipeline/stream rejects missing JD."""
    resp = await aclient.post(
        "/api/generate/pipeline/stream",
        json={"job_title": "Engineer", "jd_text": ""},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stream_rejects_oversized_jd(aclient):
    """POST /api/generate/pipeline/stream rejects JD larger than 50KB."""
    resp = await aclient.post(
        "/api/generate/pipeline/stream",
        json={"job_title": "Engineer", "jd_text": "x" * 60_000},
    )
    assert resp.status_code == 413


# ═══════════════════════════════════════════════════════════════════════
# 2. Legacy Fallback Path (when _AGENT_PIPELINES_AVAILABLE is False)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_legacy_stream_returns_sse_with_events(aclient):
    """Legacy stream returns SSE content-type and emits progress + complete events."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
    content_type = resp.headers.get("content-type", "")
    assert "text/event-stream" in content_type, f"Expected SSE, got {content_type}"

    events = parse_sse_events(resp.text)
    event_types = [e["event"] for e in events]

    assert "progress" in event_types, f"Missing progress events in: {event_types}"
    assert "complete" in event_types, f"Missing complete event in: {event_types}"


@pytest.mark.asyncio
async def test_legacy_stream_progress_phases_in_order(aclient):
    """Legacy stream emits progress phases in the expected pipeline order."""
    with (        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    events = parse_sse_events(resp.text)
    progress_phases = [
        e["data"].get("phase") for e in events
        if e["event"] == "progress" and isinstance(e["data"], dict)
    ]

    expected_phases = [
        "initializing", "profiling", "profiling_done",
        "gap_analysis", "gap_analysis_done",
        "documents", "documents_done",
        "portfolio", "portfolio_done",
        "validation", "validation_done",
        "formatting",
    ]
    for phase in expected_phases:
        assert phase in progress_phases, f"Missing phase '{phase}' in stream. Got: {progress_phases}"


@pytest.mark.asyncio
async def test_legacy_stream_complete_has_result(aclient):
    """Legacy stream complete event contains the full generation result."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    events = parse_sse_events(resp.text)
    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1, f"Expected 1 complete event, got {len(complete_events)}"

    complete_data = complete_events[0]["data"]
    assert complete_data.get("progress") == 100
    result = complete_data.get("result", {})
    assert result.get("cvHtml") == SAMPLE_CV_HTML, f"CV HTML mismatch: {result.get('cvHtml', '')[:100]}"
    assert result.get("coverLetterHtml") == SAMPLE_CL_HTML
    assert "scores" in result
    assert result["scores"].get("overall", 0) > 0


@pytest.mark.asyncio
async def test_legacy_stream_progress_increases_monotonically(aclient):
    """Progress percentages in SSE events should increase monotonically."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    events = parse_sse_events(resp.text)
    progress_values = [
        e["data"]["progress"]
        for e in events
        if e["event"] == "progress" and isinstance(e["data"], dict) and "progress" in e["data"]
    ]

    for i in range(1, len(progress_values)):
        assert progress_values[i] >= progress_values[i - 1], (
            f"Progress decreased at index {i}: {progress_values[i - 1]} → {progress_values[i]}"
        )


@pytest.mark.asyncio
async def test_legacy_stream_survives_cv_failure(aclient):
    """If CV generation fails in legacy stream, cover letter should still be in the result."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)
        # CV fails
        MockDocGen.return_value.generate_tailored_cv = AsyncMock(
            side_effect=Exception("Model overloaded")
        )

        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1

    result = complete_events[0]["data"].get("result", {})
    assert result.get("cvHtml") == "", "CV should be empty on failure"
    assert result.get("coverLetterHtml") == SAMPLE_CL_HTML, "Cover letter should still succeed"


@pytest.mark.asyncio
async def test_legacy_stream_error_event_on_total_failure(aclient):
    """If the entire pipeline fails, stream emits an error SSE event."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient", side_effect=Exception("AI client init failed")),
    ):
        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    assert resp.status_code == 200  # SSE always returns 200, errors are in the event stream
    events = parse_sse_events(resp.text)
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) >= 1, f"Expected error event, got: {[e['event'] for e in events]}"
    assert error_events[0]["data"].get("code") in (500, 401, 429), (
        f"Error should have a status code: {error_events[0]['data']}"
    )


@pytest.mark.asyncio
async def test_legacy_stream_no_resume_still_works(aclient):
    """Legacy stream succeeds when no resume text is provided (JD-only mode)."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        no_resume_request = {**VALID_STREAM_REQUEST, "resume_text": ""}
        resp = await aclient.post("/api/generate/pipeline/stream", json=no_resume_request)

    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1, "Should complete even without resume"


# ═══════════════════════════════════════════════════════════════════════
# 3. Agent Pipeline Path (when _AGENT_PIPELINES_AVAILABLE is True)
# ═══════════════════════════════════════════════════════════════════════


def _agent_pipeline_mocks():
    """Context manager that wires all agent pipeline mocks correctly.

    Pipeline factories are used from the generate module namespace (top-level import),
    so they must be patched at ``app.api.routes.generate.*``.
    AIClient / CareerConsultantChain / BenchmarkBuilderChain are imported *locally*
    inside _stream_agent_pipeline, so they must be patched at their source modules.
    """
    return (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", True),
        patch("ai_engine.client.AIClient"),
        patch("app.api.routes.generate.resume_parse_pipeline", return_value=_make_fake_pipeline(SAMPLE_PROFILE)),
        patch("app.api.routes.generate.benchmark_pipeline", return_value=_make_fake_pipeline(SAMPLE_BENCHMARK)),
        patch("app.api.routes.generate.gap_analysis_pipeline", return_value=_make_fake_pipeline(SAMPLE_GAP_ANALYSIS)),
        patch("app.api.routes.generate.cv_generation_pipeline", return_value=_make_fake_pipeline({"html": SAMPLE_CV_HTML})),
        patch("app.api.routes.generate.cover_letter_pipeline", return_value=_make_fake_pipeline({"html": SAMPLE_CL_HTML})),
        patch("app.api.routes.generate.personal_statement_pipeline", return_value=_make_fake_pipeline({"html": "<p>Statement</p>"})),
        patch("app.api.routes.generate.portfolio_pipeline", return_value=_make_fake_pipeline({"html": "<p>Portfolio</p>"})),
        patch("ai_engine.chains.career_consultant.CareerConsultantChain"),
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain"),
    )


from contextlib import ExitStack  # noqa: E402

def _enter_agent_mocks():
    """Enter all agent pipeline mocks and configure chain return values."""
    stack = ExitStack()
    patches = _agent_pipeline_mocks()
    entered = []
    for p in patches:
        entered.append(stack.enter_context(p))
    # last two are MockConsultant and MockBenchmark
    mock_consultant = entered[-2]
    mock_benchmark = entered[-1]
    mock_consultant.return_value.generate_roadmap = AsyncMock(return_value={"steps": []})
    mock_benchmark.return_value.create_benchmark_cv_html = AsyncMock(return_value="<p>Benchmark</p>")
    return stack, entered


@pytest.mark.asyncio
async def test_agent_stream_returns_sse_with_events(aclient):
    """Agent pipeline stream returns SSE content-type and completes."""
    stack, _ = _enter_agent_mocks()
    with stack:
        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
    content_type = resp.headers.get("content-type", "")
    assert "text/event-stream" in content_type

    events = parse_sse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert "progress" in event_types, f"Missing progress events: {event_types}"
    assert "complete" in event_types, f"Missing complete event: {event_types}"


@pytest.mark.asyncio
async def test_agent_stream_complete_has_cv_and_meta(aclient):
    """Agent stream complete event has CV html and agent metadata."""
    stack, _ = _enter_agent_mocks()
    with stack:
        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    events = parse_sse_events(resp.text)
    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1

    result = complete_events[0]["data"].get("result", {})
    assert result.get("cvHtml") == SAMPLE_CV_HTML
    assert result.get("coverLetterHtml") == SAMPLE_CL_HTML
    assert "scores" in result

    meta = result.get("meta", {})
    assert meta.get("agent_powered") is True, f"meta should have agent_powered=True: {meta}"


@pytest.mark.asyncio
async def test_agent_stream_emits_agent_status_events(aclient):
    """Agent pipeline path should emit agent_status SSE events."""
    stack, _ = _enter_agent_mocks()
    with stack:
        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    events = parse_sse_events(resp.text)
    # The agent path always emits a final "pipeline complete" agent_status event
    agent_status_events = [e for e in events if e["event"] == "agent_status"]
    assert len(agent_status_events) >= 1, (
        f"Expected at least 1 agent_status event, got: {[e['event'] for e in events]}"
    )
    # The final agent_status should indicate completion
    final_agent = agent_status_events[-1]
    assert final_agent["data"].get("status") == "completed"


@pytest.mark.asyncio
async def test_agent_stream_survives_pipeline_failure(aclient):
    """If CV pipeline fails in agent path, cover letter should still succeed."""
    failing_cv_pipe = MagicMock()
    failing_cv_pipe.execute = AsyncMock(side_effect=Exception("CV pipeline exploded"))

    stack, entered = _enter_agent_mocks()
    with stack:
        # Override just the cv_generation_pipeline to return the failing pipe
        with patch("app.api.routes.generate.cv_generation_pipeline", return_value=failing_cv_pipe):
            resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1

    result = complete_events[0]["data"].get("result", {})
    assert result.get("cvHtml") == "", "CV should be empty on pipeline failure"
    assert result.get("coverLetterHtml") == SAMPLE_CL_HTML, "Cover letter should succeed"


# ═══════════════════════════════════════════════════════════════════════
# 4. SSE Format Correctness
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_sse_format_is_valid(aclient):
    """Every SSE line follows the 'event: ...' / 'data: ...' format."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    # Check each non-empty line matches SSE format
    for line in resp.text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        assert (
            stripped.startswith("event:") or
            stripped.startswith("data:") or
            stripped.startswith("id:") or
            stripped.startswith("retry:") or
            stripped.startswith(":")        # SSE comment/keepalive
        ), f"Invalid SSE line: '{stripped}'"


@pytest.mark.asyncio
async def test_sse_data_lines_are_valid_json(aclient):
    """Every data: line should contain valid JSON."""
    with (
        patch("app.api.routes.generate._RUNTIME_AVAILABLE", False),
        patch("app.api.routes.generate._AGENT_PIPELINES_AVAILABLE", False),
        patch("ai_engine.client.AIClient"),
        patch("ai_engine.chains.role_profiler.RoleProfilerChain") as MockProfiler,
        patch("ai_engine.chains.benchmark_builder.BenchmarkBuilderChain") as MockBenchmark,
        patch("ai_engine.chains.gap_analyzer.GapAnalyzerChain") as MockGap,
        patch("ai_engine.chains.document_generator.DocumentGeneratorChain") as MockDocGen,
        patch("ai_engine.chains.career_consultant.CareerConsultantChain") as MockConsultant,
        patch("ai_engine.chains.validator.ValidatorChain") as MockValidator,
    ):
        _wire_legacy_chain_mocks(MockProfiler, MockBenchmark, MockGap, MockDocGen, MockConsultant, MockValidator)

        resp = await aclient.post("/api/generate/pipeline/stream", json=VALID_STREAM_REQUEST)

    for line in resp.text.split("\n"):
        if line.startswith("data:"):
            raw = line[len("data:"):].strip()
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                pytest.fail(f"Invalid JSON in data line: {raw[:200]}")


# ═══════════════════════════════════════════════════════════════════════
# 5. Unit tests for SSE formatting helpers
# ═══════════════════════════════════════════════════════════════════════


def test_sse_helper_format():
    """_sse produces correct SSE format."""
    from app.api.routes.generate import _sse
    result = _sse("progress", {"phase": "test", "progress": 50})
    assert result.startswith("event: progress\n")
    assert "data:" in result
    assert result.endswith("\n\n")
    data = json.loads(result.split("data: ")[1].strip())
    assert data["phase"] == "test"
    assert data["progress"] == 50


def test_agent_sse_helper_format():
    """_agent_sse produces correct agent_status SSE event."""
    from app.api.routes.generate import _agent_sse
    result = _agent_sse("cv_generation", "drafter", "completed", latency_ms=150, message="Draft done")
    assert "event: agent_status" in result
    data = json.loads(result.split("data: ")[1].strip())
    assert data["pipeline_name"] == "cv_generation"
    assert data["stage"] == "drafter"
    assert data["status"] == "completed"
    assert data["latency_ms"] == 150
    assert "timestamp" in data
