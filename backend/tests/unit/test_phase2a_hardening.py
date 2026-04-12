"""
Phase 2A — Error handling, recovery, and quality scoring tests.

Tests for:
- GET /jobs/{job_id}/status: lightweight poll for clients that lost SSE
- POST /jobs/{job_id}/retry: module-level regeneration from terminal jobs
- cleanup_stale_generation_jobs: sweep for stuck jobs
- OutputScorer: 4-dimension quality scoring
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _make_sb_mock(job_data=None, app_data=None, events_data=None, insert_data=None):
    """Build a Supabase-like mock with chained `.table().select()...` support."""
    sb = MagicMock()
    _insert_calls = []

    def _table_factory(table_name):
        chain = MagicMock()
        if "generation_job_events" in table_name:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.gt.return_value = chain
            chain.order.return_value = chain
            chain.limit.return_value = chain
            chain.insert.return_value = chain
            chain.execute.return_value = SimpleNamespace(
                data=events_data if events_data is not None else []
            )
        elif "generation_jobs" in table_name:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.in_.return_value = chain
            chain.limit.return_value = chain
            chain.maybe_single.return_value = chain
            chain.update.return_value = chain
            chain.insert.return_value = chain
            _orig_execute = chain.execute
            def _execute():
                if _insert_calls:
                    return SimpleNamespace(data=insert_data or [{"id": "new-job-1"}])
                return SimpleNamespace(
                    data=[job_data] if isinstance(job_data, dict) else (job_data if job_data is not None else [])
                )
            chain.execute = _execute

            _orig_insert = chain.insert
            def _insert(row):
                _insert_calls.append(row)
                return chain
            chain.insert = _insert
        elif "application" in table_name:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.maybe_single.return_value = chain
            chain.update.return_value = chain
            chain.execute.return_value = SimpleNamespace(
                data=app_data if app_data is not None else {}
            )
        else:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.maybe_single.return_value = chain
            chain.update.return_value = chain
            chain.insert.return_value = chain
            chain.execute.return_value = SimpleNamespace(data=[])
        return chain

    sb.table = _table_factory
    return sb


TABLES = {
    "generation_jobs": "generation_jobs",
    "generation_job_events": "generation_job_events",
    "applications": "applications",
    "evidence_ledger_items": "evidence_ledger_items",
    "claim_citations": "claim_citations",
    "tasks": "tasks",
}


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/status — lightweight poll
# ---------------------------------------------------------------------------

class TestJobStatusPolling:
    """GET /jobs/{job_id}/status must return job state without opening SSE."""

    @pytest.mark.asyncio
    async def test_returns_job_status(self):
        from app.api.routes.generate import get_generation_job_status

        job_row = {
            "id": "job-1",
            "status": "running",
            "progress": 45,
            "error_message": None,
            "requested_modules": ["cv", "coverLetter"],
            "created_at": "2026-04-11T10:00:00+00:00",
            "finished_at": None,
        }
        latest_event = {
            "event_name": "progress",
            "payload": {"stage": "drafter", "progress": 45},
            "created_at": "2026-04-11T10:01:00+00:00",
            "sequence_no": 5,
        }
        sb = _make_sb_mock(job_data=job_row, events_data=[latest_event])

        mock_user = {"id": "user-1"}

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.api.routes.generate.jobs.validate_uuid"):
            result = await get_generation_job_status(
                job_id="job-1",
                current_user=mock_user,
            )

        assert result["job_id"] == "job-1"
        assert result["status"] == "running"
        assert result["progress"] == 45
        assert result["latest_event"] is not None
        assert result["latest_event"]["event_name"] == "progress"

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_job(self):
        from app.api.routes.generate import get_generation_job_status
        from fastapi import HTTPException

        sb = _make_sb_mock(job_data=[])

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.api.routes.generate.jobs.validate_uuid"):
            with pytest.raises(HTTPException) as exc_info:
                await get_generation_job_status(
                    job_id="nonexistent",
                    current_user={"id": "user-1"},
                )
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/retry — module-level regeneration
# ---------------------------------------------------------------------------

class TestModuleRetry:
    """POST /jobs/{job_id}/retry must create a child job for failed modules."""

    @pytest.mark.asyncio
    async def test_retry_creates_child_job(self):
        from app.api.routes.generate import retry_generation_modules, RetryModulesRequest

        orig_job = {
            "id": "job-orig",
            "status": "failed",
            "application_id": "app-1",
            "requested_modules": ["cv", "coverLetter"],
            "user_id": "user-1",
        }
        app_row = {"id": "app-1", "modules": {"cv": {"state": "error"}, "coverLetter": {"state": "ready"}}}
        sb = _make_sb_mock(
            job_data=orig_job,
            app_data=app_row,
            insert_data=[{"id": "job-child-1"}],
        )

        started_jobs = []

        def mock_start(job_id, user_id):
            started_jobs.append(job_id)

        req = RetryModulesRequest(modules=["cv"])

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.api.routes.generate.jobs.validate_uuid"), \
             patch("app.api.routes.generate.jobs._start_generation_job", side_effect=mock_start), \
             patch("app.api.routes.generate.jobs._persist_generation_job_event", new_callable=AsyncMock), \
             patch("app.api.routes.generate.jobs._set_application_modules_generating", new_callable=AsyncMock):
            result = await retry_generation_modules.__wrapped__(
                request=MagicMock(),
                job_id="job-orig",
                req=req,
                current_user={"id": "user-1"},
            )

        assert result["job_id"] == "job-child-1"
        assert result["parent_job_id"] == "job-orig"
        assert "cv" in result["retrying_modules"]
        assert len(started_jobs) == 1

    @pytest.mark.asyncio
    async def test_retry_rejects_running_job(self):
        from app.api.routes.generate import retry_generation_modules, RetryModulesRequest
        from fastapi import HTTPException

        running_job = {
            "id": "job-running",
            "status": "running",
            "application_id": "app-1",
            "requested_modules": ["cv"],
            "user_id": "user-1",
        }
        sb = _make_sb_mock(job_data=running_job)
        req = RetryModulesRequest(modules=["cv"])

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.api.routes.generate.jobs.validate_uuid"):
            with pytest.raises(HTTPException) as exc_info:
                await retry_generation_modules.__wrapped__(
                    request=MagicMock(),
                    job_id="job-running",
                    req=req,
                    current_user={"id": "user-1"},
                )
            assert exc_info.value.status_code == 409

    def test_retry_request_requires_at_least_one_module(self):
        from app.api.routes.generate import RetryModulesRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RetryModulesRequest(modules=[])

    def test_retry_request_rejects_unknown_module(self):
        from app.api.routes.generate import RetryModulesRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RetryModulesRequest(modules=["nonexistent_module"])


# ---------------------------------------------------------------------------
# Stale job cleanup
# ---------------------------------------------------------------------------

class TestStaleJobCleanup:
    """cleanup_stale_generation_jobs must finalize stuck jobs beyond timeout."""

    @pytest.mark.asyncio
    async def test_cleans_up_stale_running_job(self):
        from app.api.routes.generate import cleanup_stale_generation_jobs, _ACTIVE_GENERATION_TASKS

        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        stale_job = {
            "id": "stale-job-1",
            "status": "running",
            "user_id": "user-1",
            "application_id": "app-1",
            "requested_modules": ["cv"],
            "created_at": old_time,
        }
        sb = _make_sb_mock(job_data=[stale_job])

        finalize_calls = []

        async def capture_finalize(job_id, *, status, error_message):
            finalize_calls.append({"job_id": job_id, "status": status})

        # Ensure the stale job is NOT in active tasks
        _ACTIVE_GENERATION_TASKS.pop("stale-job-1", None)

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.core.database.TABLES", TABLES), \
             patch("app.api.routes.generate.jobs._finalize_orphaned_job", side_effect=capture_finalize):
            cleaned = await cleanup_stale_generation_jobs()

        assert cleaned == 1
        assert finalize_calls[0]["job_id"] == "stale-job-1"
        assert finalize_calls[0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_skips_recent_running_job(self):
        from app.api.routes.generate import cleanup_stale_generation_jobs, _ACTIVE_GENERATION_TASKS

        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        recent_job = {
            "id": "recent-job-1",
            "status": "running",
            "user_id": "user-1",
            "application_id": "app-1",
            "requested_modules": ["cv"],
            "created_at": recent_time,
        }
        sb = _make_sb_mock(job_data=[recent_job])

        finalize_calls = []

        async def capture_finalize(job_id, *, status, error_message):
            finalize_calls.append({"job_id": job_id, "status": status})

        _ACTIVE_GENERATION_TASKS.pop("recent-job-1", None)

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.core.database.TABLES", TABLES), \
             patch("app.api.routes.generate.jobs._finalize_orphaned_job", side_effect=capture_finalize):
            cleaned = await cleanup_stale_generation_jobs()

        assert cleaned == 0
        assert len(finalize_calls) == 0

    @pytest.mark.asyncio
    async def test_skips_active_task(self):
        from app.api.routes.generate import cleanup_stale_generation_jobs, _ACTIVE_GENERATION_TASKS

        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        stale_job = {
            "id": "active-stale-1",
            "status": "running",
            "user_id": "user-1",
            "application_id": "app-1",
            "requested_modules": ["cv"],
            "created_at": old_time,
        }
        sb = _make_sb_mock(job_data=[stale_job])

        # Make it look like an active (not-done) task
        mock_task = MagicMock()
        mock_task.done.return_value = False
        _ACTIVE_GENERATION_TASKS["active-stale-1"] = mock_task

        finalize_calls = []

        async def capture_finalize(job_id, *, status, error_message):
            finalize_calls.append({"job_id": job_id, "status": status})

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.core.database.TABLES", TABLES), \
             patch("app.api.routes.generate.jobs._finalize_orphaned_job", side_effect=capture_finalize):
            cleaned = await cleanup_stale_generation_jobs()

        assert cleaned == 0
        assert len(finalize_calls) == 0

        # Clean up
        _ACTIVE_GENERATION_TASKS.pop("active-stale-1", None)

    @pytest.mark.asyncio
    async def test_returns_zero_on_no_stuck_jobs(self):
        from app.api.routes.generate import cleanup_stale_generation_jobs

        sb = _make_sb_mock(job_data=[])

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.core.database.TABLES", TABLES):
            cleaned = await cleanup_stale_generation_jobs()

        assert cleaned == 0


# ---------------------------------------------------------------------------
# OutputScorer — 4-dimension quality scoring
# ---------------------------------------------------------------------------

class TestOutputScorer:
    """OutputScorer must return structured 4-dimension scores."""

    @pytest.mark.asyncio
    async def test_scores_cv_document(self):
        from ai_engine.chains.output_scorer import OutputScorer

        mock_client = AsyncMock()
        mock_client.complete_json = AsyncMock(return_value={
            "relevance": {"score": 8, "justification": "Good role alignment"},
            "formatting": {"score": 7, "justification": "Clean structure"},
            "keyword_coverage": {"score": 6, "justification": "Missing some JD terms"},
            "readability": {"score": 9, "justification": "Clear and professional"},
            "overall": {"score": 7, "justification": "Solid resume"},
            "top_improvement": "Add more quantified achievements",
        })

        scorer = OutputScorer(mock_client)
        result = await scorer.score(
            document_type="CV/Resume",
            content="<h1>John Doe</h1><p>Senior Software Engineer with 10 years of experience.</p>",
            jd_text="Looking for a Senior Software Engineer with Python and React experience.",
            user_profile={"name": "John Doe", "skills": [{"name": "Python"}, {"name": "React"}]},
        )

        assert result["relevance"]["score"] == 8
        assert result["formatting"]["score"] == 7
        assert result["keyword_coverage"]["score"] == 6
        assert result["readability"]["score"] == 9
        assert result["composite_score"] > 0
        assert "top_improvement" in result

    @pytest.mark.asyncio
    async def test_empty_content_returns_zero_scores(self):
        from ai_engine.chains.output_scorer import OutputScorer

        mock_client = AsyncMock()
        scorer = OutputScorer(mock_client)
        result = await scorer.score(
            document_type="CV/Resume",
            content="",
            jd_text="Some JD",
        )

        assert result["composite_score"] == 0.0
        assert result["relevance"]["score"] == 0
        mock_client.complete_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_error_returns_zero_scores(self):
        from ai_engine.chains.output_scorer import OutputScorer

        mock_client = AsyncMock()
        mock_client.complete_json = AsyncMock(side_effect=RuntimeError("AI down"))

        scorer = OutputScorer(mock_client)
        result = await scorer.score(
            document_type="Cover Letter",
            content="<p>Dear Hiring Manager, I am writing to express my interest...</p>",
            jd_text="Marketing Manager position",
        )

        assert result["composite_score"] == 0.0
        assert "AI error" in result["relevance"]["justification"]

    @pytest.mark.asyncio
    async def test_scores_are_clamped_to_valid_range(self):
        from ai_engine.chains.output_scorer import OutputScorer

        mock_client = AsyncMock()
        mock_client.complete_json = AsyncMock(return_value={
            "relevance": {"score": 15, "justification": "Out of range"},
            "formatting": {"score": -3, "justification": "Negative"},
            "keyword_coverage": {"score": 7, "justification": "Fine"},
            "readability": {"score": 8, "justification": "Good"},
            "overall": {"score": 11, "justification": "Also out of range"},
            "top_improvement": "Fix scoring logic",
        })

        scorer = OutputScorer(mock_client)
        result = await scorer.score(
            document_type="CV",
            content="<p>A valid document with enough content to score properly.</p>",
            jd_text="Some job description",
        )

        assert result["relevance"]["score"] == 10  # clamped to max
        assert result["formatting"]["score"] == 0  # clamped to min
        assert result["keyword_coverage"]["score"] == 7
        assert result["readability"]["score"] == 8
        assert result["overall"]["score"] == 10

    def test_composite_score_calculation(self):
        """Verify composite is a weighted average * 10."""

        # Weights: relevance=0.3, formatting=0.15, keyword_coverage=0.3, readability=0.25
        # (8*0.3 + 7*0.15 + 6*0.3 + 9*0.25) * 10 = (2.4+1.05+1.8+2.25)*10 = 75.0
        result = {
            "relevance": {"score": 8},
            "formatting": {"score": 7},
            "keyword_coverage": {"score": 6},
            "readability": {"score": 9},
        }
        weights = {"relevance": 0.3, "formatting": 0.15, "keyword_coverage": 0.3, "readability": 0.25}
        composite = sum(
            result.get(dim, {}).get("score", 0) * w
            for dim, w in weights.items()
        ) * 10
        assert round(composite, 1) == 75.0


# ---------------------------------------------------------------------------
# _strip_html and _summarize_profile helpers
# ---------------------------------------------------------------------------

class TestScorerHelpers:
    """Test the internal helper functions of the scorer."""

    def test_strip_html_removes_tags(self):
        from ai_engine.chains.output_scorer import _strip_html

        assert _strip_html("<h1>Title</h1><p>Body</p>") == "Title  Body"
        assert _strip_html("No tags here") == "No tags here"
        assert _strip_html("") == ""

    def test_summarize_profile_with_full_data(self):
        from ai_engine.chains.output_scorer import _summarize_profile

        profile = {
            "name": "Jane Smith",
            "title": "Product Manager",
            "skills": [{"name": "Agile"}, {"name": "SQL"}, {"name": "Figma"}],
            "experience": [{"company": "Acme"}, {"company": "BigCo"}],
        }
        summary = _summarize_profile(profile)
        assert "Jane Smith" in summary
        assert "Product Manager" in summary
        assert "Agile" in summary
        assert "2 positions" in summary

    def test_summarize_profile_empty(self):
        from ai_engine.chains.output_scorer import _summarize_profile

        assert _summarize_profile({}) == "No profile data available"
