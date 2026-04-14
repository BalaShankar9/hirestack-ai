"""Tests for PipelineRuntime, EventSink implementations, and error classification."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Ensure project root on sys.path ──────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ═══════════════════════════════════════════════════════════════════════
#  Imports under test
# ═══════════════════════════════════════════════════════════════════════

from app.services.pipeline_runtime import (  # noqa: E402
    CollectorSink,
    DatabaseSink,
    ExecutionMode,
    NullSink,
    PipelineEvent,
    PipelineRuntime,
    RuntimeConfig,
    SSESink,
    classify_ai_error,
)


# ═══════════════════════════════════════════════════════════════════════
#  EventSink tests
# ═══════════════════════════════════════════════════════════════════════

class TestNullSink:
    @pytest.mark.asyncio
    async def test_emit_does_nothing(self):
        sink = NullSink()
        await sink.emit(PipelineEvent(event_type="progress", phase="atlas", progress=10))
        await sink.close()  # should not raise


class TestCollectorSink:
    @pytest.mark.asyncio
    async def test_collects_events(self):
        sink = CollectorSink()
        e1 = PipelineEvent(event_type="progress", phase="atlas", progress=10)
        e2 = PipelineEvent(event_type="progress", phase="cipher", progress=50)
        await sink.emit(e1)
        await sink.emit(e2)
        assert len(sink.events) == 2
        assert sink.events[0].phase == "atlas"
        assert sink.events[1].progress == 50


class TestSSESink:
    @pytest.mark.asyncio
    async def test_progress_event_format(self):
        sink = SSESink()
        event = PipelineEvent(
            event_type="progress", phase="atlas", progress=15,
            message="Parsing resume…",
        )
        await sink.emit(event)
        raw = await sink.queue.get()
        assert raw.startswith("event: progress\n")
        data_line = raw.split("\n")[1]
        data_json = json.loads(data_line.replace("data: ", ""))
        assert data_json["phase"] == "atlas"
        assert data_json["progress"] == 15

    @pytest.mark.asyncio
    async def test_agent_status_event_format(self):
        sink = SSESink()
        event = PipelineEvent(
            event_type="agent_status", pipeline_name="benchmark",
            stage="researcher", status="running", latency_ms=120,
        )
        await sink.emit(event)
        raw = await sink.queue.get()
        assert "agent_status" in raw
        data_line = raw.split("\n")[1]
        data_json = json.loads(data_line.replace("data: ", ""))
        assert data_json["pipeline_name"] == "benchmark"
        assert data_json["stage"] == "researcher"

    @pytest.mark.asyncio
    async def test_close_sends_sentinel(self):
        sink = SSESink()
        await sink.close()
        item = await sink.queue.get()
        assert item is None

    @pytest.mark.asyncio
    async def test_iter_events_terminates_on_close(self):
        sink = SSESink()
        await sink.emit(PipelineEvent(event_type="progress", progress=50))
        await sink.close()

        events = []
        async for ev in sink.iter_events():
            events.append(ev)
        assert len(events) == 1


class TestDatabaseSink:
    @pytest.mark.asyncio
    async def test_emit_persists_events(self):
        mock_db = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[])
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_db.table.return_value = mock_table

        sink = DatabaseSink(
            db=mock_db,
            tables={"generation_job_events": "generation_job_events", "generation_jobs": "generation_jobs"},
            job_id="job-1", user_id="user-1", application_id="app-1",
        )
        await sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=10, message="Starting…",
        ))
        mock_db.table.assert_any_call("generation_job_events")
        call_args = mock_table.insert.call_args[0][0]
        assert call_args["job_id"] == "job-1"
        assert call_args["sequence_no"] == 1

    @pytest.mark.asyncio
    async def test_skip_duplicate_job_updates_when_progress_state_is_unchanged(self):
        mock_db = MagicMock()

        mock_event_insert = MagicMock()
        mock_event_insert.execute.return_value = MagicMock(data=[])
        mock_event_table = MagicMock()
        mock_event_table.insert.return_value = mock_event_insert

        mock_job_update = MagicMock()
        mock_job_update.eq.return_value = mock_job_update
        mock_job_update.execute.return_value = MagicMock(data=[])
        mock_job_table = MagicMock()
        mock_job_table.update.return_value = mock_job_update

        def table_side_effect(name):
            if name == "generation_job_events":
                return mock_event_table
            if name == "generation_jobs":
                return mock_job_table
            raise AssertionError(f"unexpected table: {name}")

        mock_db.table.side_effect = table_side_effect

        sink = DatabaseSink(
            db=mock_db,
            tables={"generation_job_events": "generation_job_events", "generation_jobs": "generation_jobs"},
            job_id="job-1", user_id="user-1", application_id="app-1",
        )

        event = PipelineEvent(
            event_type="progress",
            phase="atlas",
            progress=15,
            message="Resume parsed",
        )

        await sink.emit(event)
        await sink.emit(event)

        assert mock_event_table.insert.call_count == 2
        assert mock_job_table.update.call_count == 1


# ═══════════════════════════════════════════════════════════════════════
#  Error classification tests
# ═══════════════════════════════════════════════════════════════════════

class TestClassifyAiError:
    def test_invalid_api_key(self):
        result = classify_ai_error(Exception("API key not valid for project"))
        assert result is not None
        assert result["code"] == 401

    def test_permission_denied(self):
        result = classify_ai_error(Exception("PERMISSION_DENIED: insufficient"))
        assert result is not None
        assert result["code"] == 403

    def test_model_not_found(self):
        result = classify_ai_error(Exception("404 model not found"))
        assert result is not None
        assert result["code"] == 404

    def test_rate_limit(self):
        result = classify_ai_error(Exception("429 Resource Exhausted, retry in 30s"))
        assert result is not None
        assert result["code"] == 429
        assert result["retry_after_seconds"] == 30

    def test_unknown_error_returns_none(self):
        result = classify_ai_error(Exception("Something weird happened"))
        assert result is None

    def test_credentials_missing(self):
        result = classify_ai_error(Exception("credentials_missing"))
        assert result is not None
        assert result["code"] == 401


# ═══════════════════════════════════════════════════════════════════════
#  RuntimeConfig tests
# ═══════════════════════════════════════════════════════════════════════

class TestRuntimeConfig:
    def test_defaults(self):
        config = RuntimeConfig()
        assert config.mode == ExecutionMode.SYNC
        assert config.timeout == 300.0
        assert config.user_id == ""

    def test_custom(self):
        config = RuntimeConfig(
            mode=ExecutionMode.STREAM,
            timeout=120.0,
            user_id="u-123",
            requested_modules=["cv", "cover_letter"],
        )
        assert config.mode == ExecutionMode.STREAM
        assert "cv" in config.requested_modules


# ═══════════════════════════════════════════════════════════════════════
#  PipelineEvent tests
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineEvent:
    def test_defaults(self):
        e = PipelineEvent(event_type="progress")
        assert e.phase == ""
        assert e.progress == 0
        assert e.data == {}

    def test_full_event(self):
        e = PipelineEvent(
            event_type="agent_status",
            pipeline_name="cv_generation",
            stage="drafter",
            status="completed",
            latency_ms=3500,
        )
        assert e.pipeline_name == "cv_generation"
        assert e.latency_ms == 3500


# ═══════════════════════════════════════════════════════════════════════
#  PipelineRuntime helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestRuntimeHelpers:
    def test_extract_pipeline_html_string(self):
        assert PipelineRuntime._extract_pipeline_html("hello") == "hello"

    def test_extract_pipeline_html_dict_with_html_key(self):
        assert PipelineRuntime._extract_pipeline_html({"html": "<p>hi</p>"}) == "<p>hi</p>"

    def test_extract_pipeline_html_dict_with_content_key(self):
        assert PipelineRuntime._extract_pipeline_html({"content": "<p>x</p>"}) == "<p>x</p>"

    def test_extract_pipeline_html_nested(self):
        payload = {"content": {"html": "<p>nested</p>"}}
        assert PipelineRuntime._extract_pipeline_html(payload) == "<p>nested</p>"

    def test_extract_pipeline_html_fallback(self):
        assert PipelineRuntime._extract_pipeline_html(42) == ""
        assert PipelineRuntime._extract_pipeline_html({}) == ""

    def test_quality_score_overall(self):
        assert PipelineRuntime._quality_score({"overall": 85.5}) == 85.5

    def test_quality_score_average(self):
        score = PipelineRuntime._quality_score({"clarity": 80, "tone": 90})
        assert score == 85.0

    def test_quality_score_empty(self):
        assert PipelineRuntime._quality_score({}) == 0.0
        assert PipelineRuntime._quality_score(None) == 0.0

    def test_extract_keywords_from_jd(self):
        jd = "Looking for Python and JavaScript developers with React experience"
        kw = PipelineRuntime._extract_keywords_from_jd(jd)
        assert isinstance(kw, list)
        assert "Python" in kw
        assert "JavaScript" in kw
        assert "React" in kw

    def test_extract_keywords_empty(self):
        assert PipelineRuntime._extract_keywords_from_jd("") == []


class TestFormatResponse:
    def test_basic_response_shape(self):
        resp = PipelineRuntime._format_response(
            benchmark_data={"ideal_skills": [{"name": "Python", "level": "expert", "importance": "critical"}]},
            gap_analysis={"compatibility_score": 75, "skill_gaps": [], "strengths": [], "recommendations": []},
            roadmap={"steps": []},
            cv_html="<p>CV</p>",
            cl_html="<p>CL</p>",
            ps_html="<p>PS</p>",
            portfolio_html="<p>PF</p>",
            validation={"cv": {"valid": True, "qualityScore": 80}},
            keywords=["Python", "React"],
            job_title="Engineer",
        )
        assert "benchmark" in resp
        assert "gaps" in resp
        assert "scores" in resp
        assert "documents" in resp
        assert "validation" in resp
        assert "learningPlan" in resp

        assert resp["documents"]["cv"] == "<p>CV</p>"
        assert resp["scores"]["compatibility"] == 75
        assert "Python" in resp["benchmark"]["keywords"]

    def test_empty_inputs(self):
        resp = PipelineRuntime._format_response(
            benchmark_data={}, gap_analysis={}, roadmap={},
            cv_html="", cl_html="", ps_html="", portfolio_html="",
            validation={}, keywords=[], job_title="Tester",
        )
        assert resp["scores"]["overall"] == 50  # default
        assert resp["documents"]["cv"] == ""

    def test_benchmark_rubric_formatting(self):
        resp = PipelineRuntime._format_response(
            benchmark_data={
                "ideal_skills": [
                    {"name": "Python", "level": "expert", "importance": "critical"},
                    {"name": "SQL", "level": "intermediate", "importance": "important"},
                ],
            },
            gap_analysis={}, roadmap={},
            cv_html="", cl_html="", ps_html="", portfolio_html="",
            validation={}, keywords=[], job_title="Dev",
        )
        rubric = resp["benchmark"]["rubric"]
        assert len(rubric) == 2
        assert "Python" in rubric[0]
        assert "expert" in rubric[0]


# ═══════════════════════════════════════════════════════════════════════
#  Evidence summary builder
# ═══════════════════════════════════════════════════════════════════════

class TestBuildEvidenceSummary:
    def test_none_result_returns_none(self):
        assert PipelineRuntime._build_evidence_summary(None) is None

    def test_no_ledger_no_citations_returns_none(self):
        result_mock = MagicMock()
        result_mock.evidence_ledger = None
        result_mock.citations = None
        assert PipelineRuntime._build_evidence_summary(result_mock) is None

    def test_with_citations(self):
        result_mock = MagicMock()
        result_mock.evidence_ledger = {"items": [{"tier": "verbatim"}, {"tier": "derived"}], "count": 2}
        result_mock.citations = [
            {"classification": "supported", "evidence_ids": ["ev_1"]},
            {"classification": "fabricated", "evidence_ids": []},
        ]
        summary = PipelineRuntime._build_evidence_summary(result_mock)
        assert summary is not None
        assert summary["evidence_count"] == 2
        assert summary["tier_distribution"]["verbatim"] == 1
        assert summary["fabricated_count"] == 1
        assert summary["citation_count"] == 2
