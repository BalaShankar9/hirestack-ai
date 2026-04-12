"""
Phase 1 — Lifecycle hardening tests.

Tests for:
- _finalize_orphaned_job: ensures jobs reach terminal state
- _mark_application_generation_finished: reads fresh DB state, protects ready modules
- _run_generation_job: CancelledError, TimeoutError finalize properly
- create_generation_job: job creation before module state setting
- Partial evidence persistence on pipeline failure
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _make_sb_mock(job_data=None, app_data=None):
    """Build a Supabase-like mock with chained `.table().select()...` support."""
    sb = MagicMock()

    def _table_factory(table_name):
        chain = MagicMock()
        if "generation_jobs" in table_name:
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.in_.return_value = chain
            chain.maybe_single.return_value = chain
            chain.update.return_value = chain
            chain.insert.return_value = chain
            chain.execute.return_value = SimpleNamespace(
                data=job_data if job_data is not None else []
            )
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
# _finalize_orphaned_job
# ---------------------------------------------------------------------------

class TestFinalizeOrphanedJob:
    """_finalize_orphaned_job must write terminal status to non-terminal jobs."""

    @pytest.mark.asyncio
    async def test_marks_running_job_as_failed(self):
        from app.api.routes.generate import _finalize_orphaned_job

        job_row = {
            "id": "job-1",
            "status": "running",
            "application_id": "app-1",
            "requested_modules": ["cv"],
            "user_id": "u-1",
        }
        sb = _make_sb_mock(job_data=job_row, app_data={"id": "app-1", "modules": {"cv": {"state": "generating"}}})
        patches_written = []

        async def capture_persist(sb_arg, tables, job_id, patch):
            patches_written.append(patch)

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.api.routes.generate._persist_generation_job_update", side_effect=capture_persist), \
             patch("app.api.routes.generate._mark_application_generation_finished", new_callable=AsyncMock):
            await _finalize_orphaned_job("job-1", status="failed", error_message="test error")

        assert len(patches_written) >= 1
        assert patches_written[0]["status"] == "failed"
        assert "test error" in patches_written[0]["error_message"]

    @pytest.mark.asyncio
    async def test_skips_already_terminal_job(self):
        from app.api.routes.generate import _finalize_orphaned_job

        job_row = {"id": "job-1", "status": "succeeded", "application_id": "app-1"}
        sb = _make_sb_mock(job_data=job_row)
        patches_written = []

        async def capture_persist(sb_arg, tables, job_id, patch):
            patches_written.append(patch)

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.api.routes.generate._persist_generation_job_update", side_effect=capture_persist):
            await _finalize_orphaned_job("job-1", status="failed")

        # Nothing should be written — job is already terminal
        assert len(patches_written) == 0


# ---------------------------------------------------------------------------
# _mark_application_generation_finished — fresh read + race protection
# ---------------------------------------------------------------------------

class TestMarkApplicationFinished:
    """_mark_application_generation_finished must read fresh state and protect ready modules."""

    @pytest.mark.asyncio
    async def test_reads_fresh_state_when_row_is_none(self):
        from app.api.routes.generate import _mark_application_generation_finished

        # Simulate: caller passes application_row=None → function reads fresh from DB
        fresh_app = {
            "id": "app-1",
            "modules": {"cv": {"state": "generating"}, "coverLetter": {"state": "ready"}},
            "cv_html": "",
            "cover_letter_html": "<p>CL</p>",
        }
        sb = _make_sb_mock(app_data=fresh_app)
        patches_written = []

        async def capture_patch(sb_arg, tables, app_id, patch):
            patches_written.append(patch)

        with patch("app.api.routes.generate._persist_application_patch", side_effect=capture_patch):
            await _mark_application_generation_finished(
                sb, TABLES, "app-1", None, ["cv", "coverLetter"],
                status="failed", error_message="oops",
            )

        assert len(patches_written) == 1
        modules = patches_written[0]["modules"]
        # cv was "generating" → should become "error"
        assert modules["cv"]["state"] == "error"
        # coverLetter was "ready" → should NOT be overwritten by a failure
        assert modules["coverLetter"]["state"] == "ready"

    @pytest.mark.asyncio
    async def test_protects_ready_module_on_cancellation(self):
        from app.api.routes.generate import _mark_application_generation_finished

        fresh_app = {
            "id": "app-1",
            "modules": {"cv": {"state": "ready"}, "coverLetter": {"state": "generating"}},
            "cv_html": "<p>CV</p>",
            "cover_letter_html": "",
        }
        sb = _make_sb_mock(app_data=fresh_app)
        patches_written = []

        async def capture_patch(sb_arg, tables, app_id, patch):
            patches_written.append(patch)

        with patch("app.api.routes.generate._persist_application_patch", side_effect=capture_patch):
            await _mark_application_generation_finished(
                sb, TABLES, "app-1", None, ["cv", "coverLetter"],
                status="cancelled",
            )

        modules = patches_written[0]["modules"]
        # cv was already "ready" — must remain ready
        assert modules["cv"]["state"] == "ready"
        # coverLetter was "generating" with no content → should become "idle"
        assert modules["coverLetter"]["state"] == "idle"


# ---------------------------------------------------------------------------
# _run_generation_job — CancelledError & TimeoutError finalization
# ---------------------------------------------------------------------------

class TestRunGenerationJobFinalization:
    """_run_generation_job must finalize the job on CancelledError and TimeoutError."""

    @pytest.mark.asyncio
    async def test_cancelled_error_finalizes_job(self):
        from app.api.routes.generate import _run_generation_job, _ACTIVE_GENERATION_TASKS

        finalize_calls = []

        async def mock_inner(job_id, user_id):
            raise asyncio.CancelledError()

        async def capture_finalize(job_id, *, status, error_message):
            finalize_calls.append({"job_id": job_id, "status": status})

        with patch("app.api.routes.generate._run_generation_job_inner", side_effect=mock_inner), \
             patch("app.api.routes.generate._finalize_orphaned_job", side_effect=capture_finalize):
            await _run_generation_job("job-1", "user-1")

        assert len(finalize_calls) == 1
        assert finalize_calls[0]["status"] == "cancelled"
        assert "job-1" not in _ACTIVE_GENERATION_TASKS

    @pytest.mark.asyncio
    async def test_timeout_finalizes_job(self):
        from app.api.routes.generate import _run_generation_job

        finalize_calls = []

        async def mock_inner(job_id, user_id):
            await asyncio.sleep(3600)  # simulate long run

        async def capture_finalize(job_id, *, status, error_message):
            finalize_calls.append({"job_id": job_id, "status": status})

        async def mock_wait_for(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError()

        with patch("app.api.routes.generate._run_generation_job_inner", side_effect=mock_inner), \
             patch("app.api.routes.generate._finalize_orphaned_job", side_effect=capture_finalize), \
             patch("app.api.routes.generate.asyncio.wait_for", new=mock_wait_for):
            await _run_generation_job("job-1", "user-1")

        assert len(finalize_calls) == 1
        assert finalize_calls[0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_unexpected_error_finalizes_job(self):
        from app.api.routes.generate import _run_generation_job

        finalize_calls = []

        async def mock_inner(job_id, user_id):
            raise RuntimeError("boom")

        async def capture_finalize(job_id, *, status, error_message):
            finalize_calls.append({"job_id": job_id, "status": status})

        with patch("app.api.routes.generate._run_generation_job_inner", side_effect=mock_inner), \
             patch("app.api.routes.generate._finalize_orphaned_job", side_effect=capture_finalize):
            await _run_generation_job("job-1", "user-1")

        assert len(finalize_calls) == 1
        assert finalize_calls[0]["status"] == "failed"


# ---------------------------------------------------------------------------
# Partial evidence persistence on pipeline failure
# ---------------------------------------------------------------------------

class TestPartialEvidencePersistence:
    """Orchestrator must persist evidence+citations even when pipeline fails."""

    @pytest.mark.asyncio
    async def test_evidence_persisted_on_stage_failure(self):
        from ai_engine.agents.orchestrator import AgentPipeline, PipelinePolicy
        from ai_engine.agents.base import AgentResult

        class ResearcherStub:
            async def run(self, _context):
                return AgentResult(
                    content={"tool_results": {}},
                    quality_scores={},
                    flags=[],
                    latency_ms=10,
                    metadata={},
                )

        class DrafterStub:
            async def run(self, _context):
                raise RuntimeError("LLM down")

        class RecordingStore:
            def __init__(self):
                self.events = []
                self.evidence_payloads = []
                self.citation_payloads = []

            async def emit(self, _state, event_name, **kwargs):
                self.events.append({"event_name": event_name, **kwargs})

            async def load_events_for_pipeline(self, _job_id, _pipeline_name):
                return []

            async def persist_artifact(self, _state, _stage_name, _artifact):
                return None

            async def persist_evidence(self, job_id, user_id, items):
                self.evidence_payloads.append(
                    {"job_id": job_id, "user_id": user_id, "items": items}
                )

            async def persist_citations(self, job_id, user_id, citations):
                self.citation_payloads.append(
                    {"job_id": job_id, "user_id": user_id, "citations": citations}
                )

            async def check_cancel(self, _job_id):
                return False

            async def update_job(self, _job_id, _patch):
                return None

        # Set up a pipeline where researcher succeeds but drafter explodes
        researcher = ResearcherStub()
        drafter = DrafterStub()
        mock_store = RecordingStore()

        pipe = AgentPipeline(
            name="cv_generation",
            researcher=researcher,
            drafter=drafter,
            event_store=mock_store,
            policy=PipelinePolicy(skip_critique=True, skip_fact_check=True),
        )

        with pytest.raises(Exception):
            await pipe.execute({
                "user_id": "u-1",
                "job_id": "j-1",
                "application_id": "a-1",
                "user_profile": {"skills": [{"name": "Python"}]},
            })

        # Evidence should have been persisted despite the failure
        assert len(mock_store.evidence_payloads) == 1
        # workflow_failed event should have been emitted
        workflow_failed_calls = [
            event for event in mock_store.events
            if event.get("event_name") == "workflow_failed"
        ]
        assert len(workflow_failed_calls) >= 1


# ---------------------------------------------------------------------------
# create_generation_job ordering: job before modules
# ---------------------------------------------------------------------------

class TestCreateJobOrdering:
    """Job row must be created before setting module state to 'generating'."""

    @pytest.mark.asyncio
    async def test_job_insert_before_module_state(self):
        """Verify the function body order: insert job → then set modules."""
        import inspect
        from app.api.routes.generate import create_generation_job

        source = inspect.getsource(create_generation_job)
        # The insert should come before _set_application_modules_generating
        insert_pos = source.find(".insert(job_row)")
        module_pos = source.find("_set_application_modules_generating")
        # Find the LAST occurrence (the one after insert) of modules_generating
        # First find the one that sets modules - it should be after insert
        assert insert_pos < module_pos, (
            "Job row must be inserted before module states are set to 'generating'"
        )
