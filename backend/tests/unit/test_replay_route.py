# backend/tests/unit/test_replay_route.py
"""Tests for the replay route (GET /jobs/{job_id}/replay)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_engine.evals.failure_taxonomy import FailureClass
from ai_engine.evals.replay_report import ReplayReport


# ═══════════════════════════════════════════════════════════════════════
#  Route registration test
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_replay_route_registered(client):
    """GET /api/generate/jobs/{job_id}/replay should be registered and require auth."""
    resp = await client.get("/api/generate/jobs/fake-job-id/replay")
    # Should be 401 (no auth) — not 404 (not found)
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════
#  Unit tests for replay route logic (mocked DB + replay runner)
# ═══════════════════════════════════════════════════════════════════════

def _mock_supabase_table(table_responses: dict):
    """Build a mock Supabase client that supports .table(name).select()...execute() chains."""
    sb = MagicMock()

    def _table(name):
        chain = MagicMock()
        response = MagicMock()
        response.data = table_responses.get(name, [])
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = response
        return chain

    sb.table = _table
    return sb


class TestReplayRouteUnit:
    """Isolated unit tests for replay_generation_job (no HTTP needed)."""

    @pytest.mark.asyncio
    async def test_successful_replay(self):
        """When job exists and replay runs, should return a report dict."""
        from backend.app.api.routes.generate import replay_generation_job

        fake_user = {"id": "user-1", "uid": "user-1", "sub": "user-1"}
        fake_request = MagicMock()
        fake_request.client.host = "127.0.0.1"
        fake_request.state = MagicMock()
        fake_job = {
            "id": "d82916b4-99ea-43e2-b6e9-fc503f54ea7c",
            "user_id": "user-1",
            "status": "failed",
            "application_id": "app-1",
            "requested_modules": ["cv"],
        }
        fake_report = ReplayReport(
            job_id="d82916b4-99ea-43e2-b6e9-fc503f54ea7c",
            pipeline_name="cv_generation",
            job_status="failed",
            failure_class=FailureClass.PROVIDER_FAILURE,
            likely_root_cause="Stage failed",
            event_count=5,
        )

        sb = _mock_supabase_table({
            "generation_jobs": fake_job,
            "evidence_ledger_items": [],
            "claim_citations": [],
        })

        mock_runner_instance = AsyncMock()
        mock_runner_instance.replay_job = AsyncMock(return_value=fake_report)

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("ai_engine.evals.replay_runner.ReplayRunner", return_value=mock_runner_instance), \
             patch("ai_engine.agents.workflow_runtime.WorkflowEventStore"), \
             patch("app.core.security.limiter.enabled", False):

            result = await replay_generation_job(request=fake_request, job_id="d82916b4-99ea-43e2-b6e9-fc503f54ea7c", current_user=fake_user)
            assert "replay_report" in result
            assert result["replay_report"]["job_id"] == "d82916b4-99ea-43e2-b6e9-fc503f54ea7c"
            assert result["replay_report"]["failure_class"] == "provider_failure"

    @pytest.mark.asyncio
    async def test_missing_job_returns_404(self):
        """When job doesn't exist, should raise 404."""
        from fastapi import HTTPException

        fake_user = {"id": "user-1"}
        fake_request = MagicMock()
        fake_request.client.host = "127.0.0.1"
        fake_request.state = MagicMock()

        sb = _mock_supabase_table({"generation_jobs": None})

        with patch("app.core.database.get_supabase", return_value=sb), \
             patch("app.core.security.limiter.enabled", False):

            with pytest.raises(HTTPException) as exc_info:
                from backend.app.api.routes.generate import replay_generation_job
                await replay_generation_job(request=fake_request, job_id="d82916b4-99ea-43e2-b6e9-fc503f54ea7c", current_user=fake_user)
            assert exc_info.value.status_code == 404


class TestReplayReportSerialization:
    """Verify the replay report serializes cleanly for frontend consumption."""

    def test_report_to_dict_has_required_fields(self):
        report = ReplayReport(
            job_id="j1",
            pipeline_name="cv_generation",
            job_status="failed",
            completed_stages=["researcher"],
            failed_stages=["drafter"],
            failure_class=FailureClass.STAGE_TIMEOUT,
            likely_root_cause="drafter timed out",
            event_count=10,
            evidence_count=5,
            evidence_tier_distribution={"verbatim": 3, "derived": 2},
            citation_count=4,
            unlinked_citation_count=1,
            fabricated_claim_count=0,
            suggested_regression_target="test_lifecycle_hardening.py",
        )
        d = report.to_dict()

        # All expected frontend-facing fields present
        assert "job_id" in d
        assert "pipeline_name" in d
        assert "job_status" in d
        assert "completed_stages" in d
        assert "failed_stages" in d
        assert "skipped_stages" in d
        assert "timed_out_stages" in d
        assert "artifacts_present" in d
        assert "artifacts_missing" in d
        assert "evidence_count" in d
        assert "evidence_tier_distribution" in d
        assert "citation_count" in d
        assert "unlinked_citation_count" in d
        assert "fabricated_claim_count" in d
        assert "failure_class" in d
        assert "likely_root_cause" in d
        assert "suggested_regression_target" in d
        assert "event_count" in d

        # Values are JSON-serializable primitives
        assert isinstance(d["failure_class"], str)
        assert isinstance(d["completed_stages"], list)
        assert isinstance(d["evidence_tier_distribution"], dict)

    def test_report_is_failure_property(self):
        failed = ReplayReport(job_id="j1", pipeline_name="cv", job_status="failed")
        assert failed.is_failure is True

        succeeded = ReplayReport(job_id="j2", pipeline_name="cv", job_status="succeeded")
        assert succeeded.is_failure is False

        partial = ReplayReport(
            job_id="j3", pipeline_name="cv", job_status="succeeded",
            failed_stages=["optimizer"],
        )
        assert partial.is_failure is True
