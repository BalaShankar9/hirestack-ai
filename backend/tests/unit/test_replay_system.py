# backend/tests/unit/test_replay_system.py
"""Tests for Brief 2: Replay and Failure Intelligence (taxonomy, report, runner)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_engine.evals.failure_taxonomy import FailureClass, classify_failure
from ai_engine.evals.replay_report import ReplayReport
from ai_engine.evals.replay_runner import ReplayRunner


# ═══════════════════════════════════════════════════════════════════════
#  Failure Taxonomy tests
# ═══════════════════════════════════════════════════════════════════════

class TestFailureClass:
    def test_all_classes_has_ten_entries(self):
        assert len(FailureClass.all_classes()) == 10

    def test_all_classes_are_strings(self):
        for cls in FailureClass.all_classes():
            assert isinstance(cls, str)


class TestClassifyFailure:
    def _base_kwargs(self, **overrides):
        defaults = {
            "events": [],
            "evidence_items": [{"tier": "verbatim"} for _ in range(5)],
            "citations": [],
            "job_status": "failed",
            "stage_statuses": {},
        }
        defaults.update(overrides)
        return defaults

    def test_stage_timeout(self):
        cls, reason = classify_failure(
            **self._base_kwargs(stage_statuses={"drafter": "timed_out"})
        )
        assert cls == FailureClass.STAGE_TIMEOUT
        assert "drafter" in reason

    def test_provider_failure_from_failed_stage(self):
        cls, reason = classify_failure(
            **self._base_kwargs(
                stage_statuses={"researcher": "failed"},
                events=[{
                    "event_name": "stage_failed",
                    "stage": "researcher",
                    "payload": {"error": "API rate limit exceeded (429)"},
                    "message": "",
                }],
            )
        )
        assert cls == FailureClass.PROVIDER_FAILURE

    def test_provider_failure_generic(self):
        cls, _ = classify_failure(
            **self._base_kwargs(stage_statuses={"drafter": "failed"})
        )
        assert cls == FailureClass.PROVIDER_FAILURE

    def test_low_evidence_input(self):
        cls, reason = classify_failure(
            **self._base_kwargs(
                evidence_items=[{"tier": "verbatim"}],  # only 1 item
                stage_statuses={"researcher": "completed", "drafter": "completed"},
            )
        )
        assert cls == FailureClass.LOW_EVIDENCE_INPUT
        assert "1 evidence items" in reason

    def test_contract_drift(self):
        cls, _ = classify_failure(
            **self._base_kwargs(
                events=[{
                    "event_name": "warning",
                    "stage": "optimizer",
                    "message": "optimizer_contract_drift detected",
                    "payload": {},
                }],
                stage_statuses={"researcher": "completed", "drafter": "completed"},
            )
        )
        assert cls == FailureClass.CONTRACT_DRIFT

    def test_evidence_binding_miss(self):
        citations = [
            {"claim_text": "claim1", "evidence_ids": [], "classification": "verified"},
            {"claim_text": "claim2", "evidence_ids": [], "classification": "verified"},
            {"claim_text": "claim3", "evidence_ids": ["e1"], "classification": "verified"},
        ]
        cls, reason = classify_failure(
            **self._base_kwargs(
                citations=citations,
                stage_statuses={"researcher": "completed", "drafter": "completed"},
            )
        )
        assert cls == FailureClass.EVIDENCE_BINDING_MISS
        assert "2/3" in reason

    def test_citation_freshness_miss(self):
        citations = [
            {"claim_text": "claim1", "evidence_ids": ["e1"], "classification": "fabricated"},
        ]
        cls, _ = classify_failure(
            **self._base_kwargs(
                citations=citations,
                stage_statuses={"researcher": "completed", "drafter": "completed"},
            )
        )
        assert cls == FailureClass.CITATION_FRESHNESS_MISS

    def test_unknown_fallback(self):
        cls, _ = classify_failure(
            **self._base_kwargs(
                stage_statuses={"researcher": "completed", "drafter": "completed"},
            )
        )
        assert cls == FailureClass.UNKNOWN


# ═══════════════════════════════════════════════════════════════════════
#  Replay Report tests
# ═══════════════════════════════════════════════════════════════════════

class TestReplayReport:
    def test_to_dict(self):
        report = ReplayReport(
            job_id="j1",
            pipeline_name="cv_generation",
            job_status="failed",
            completed_stages=["researcher"],
            failed_stages=["drafter"],
            failure_class=FailureClass.PROVIDER_FAILURE,
            likely_root_cause="API error",
        )
        d = report.to_dict()
        assert d["job_id"] == "j1"
        assert d["failure_class"] == "provider_failure"
        assert d["likely_root_cause"] == "API error"

    def test_is_failure(self):
        report = ReplayReport(job_id="j1", pipeline_name="cv", job_status="failed")
        assert report.is_failure is True

        report2 = ReplayReport(
            job_id="j2", pipeline_name="cv", job_status="succeeded",
            failed_stages=["drafter"],
        )
        assert report2.is_failure is True

        report3 = ReplayReport(job_id="j3", pipeline_name="cv", job_status="succeeded")
        assert report3.is_failure is False

    def test_summary_line(self):
        report = ReplayReport(
            job_id="abcdef12-3456-7890-abcd-ef1234567890",
            pipeline_name="cv_generation",
            job_status="failed",
            failure_class=FailureClass.STAGE_TIMEOUT,
            likely_root_cause="Stage 'drafter' timed out",
        )
        line = report.summary_line
        assert "stage_timeout" in line
        assert "cv_generation" in line


# ═══════════════════════════════════════════════════════════════════════
#  Replay Runner tests
# ═══════════════════════════════════════════════════════════════════════

def _make_mock_store(events=None):
    store = MagicMock()
    store.load_events = AsyncMock(return_value=events or [])
    return store


class TestReplayRunner:
    @pytest.mark.asyncio
    async def test_replay_with_no_events(self):
        store = _make_mock_store([])
        runner = ReplayRunner(store)
        report = await runner.replay_job("j1", job_status="failed")
        assert report.failure_class == FailureClass.UNKNOWN
        assert "No events found" in report.likely_root_cause
        assert report.event_count == 0

    @pytest.mark.asyncio
    async def test_replay_detects_timeout(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cv_generation", "workflow_id": "w1"}, "message": ""},
            {"event_name": "stage_start", "stage": "researcher", "status": "running", "payload": {}, "message": ""},
            {"event_name": "stage_complete", "stage": "researcher", "status": "completed", "payload": {}, "message": ""},
            {"event_name": "stage_start", "stage": "drafter", "status": "running", "payload": {}, "message": ""},
            {"event_name": "stage_timeout", "stage": "drafter", "status": "timed_out", "payload": {}, "message": ""},
        ]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job("j1", job_status="failed")
        assert report.failure_class == FailureClass.STAGE_TIMEOUT
        assert report.pipeline_name == "cv_generation"
        assert "drafter" in report.timed_out_stages

    @pytest.mark.asyncio
    async def test_replay_detects_low_evidence(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cover_letter", "workflow_id": "w1"}, "message": ""},
            {"event_name": "stage_complete", "stage": "researcher", "status": "completed", "payload": {}, "message": ""},
            {"event_name": "stage_complete", "stage": "drafter", "status": "completed", "payload": {}, "message": ""},
        ]
        evidence = [{"tier": "verbatim", "text": "one item"}]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job(
            "j1", job_status="succeeded", evidence_items=evidence,
        )
        assert report.failure_class == FailureClass.LOW_EVIDENCE_INPUT
        assert report.evidence_count == 1

    @pytest.mark.asyncio
    async def test_replay_detects_evidence_binding_miss(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cv_generation", "workflow_id": "w1"}, "message": ""},
            {"event_name": "stage_complete", "stage": "researcher", "status": "completed", "payload": {}, "message": ""},
            {"event_name": "stage_complete", "stage": "drafter", "status": "completed", "payload": {}, "message": ""},
        ]
        citations = [
            {"claim_text": "c1", "evidence_ids": [], "classification": "verified"},
            {"claim_text": "c2", "evidence_ids": [], "classification": "verified"},
        ]
        evidence = [{"tier": "verbatim"} for _ in range(5)]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job(
            "j1", job_status="succeeded",
            evidence_items=evidence, citations=citations,
        )
        assert report.failure_class == FailureClass.EVIDENCE_BINDING_MISS
        assert report.unlinked_citation_count == 2

    @pytest.mark.asyncio
    async def test_replay_infers_pipeline_name_from_events(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cover_letter", "workflow_id": "w1"}, "message": ""},
        ]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job("j1", job_status="failed")
        assert report.pipeline_name == "cover_letter"

    @pytest.mark.asyncio
    async def test_replay_tracks_artifacts_present(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cv_generation", "workflow_id": "w1"}, "message": ""},
            {"event_name": "stage_complete", "stage": "researcher", "status": "completed", "payload": {}, "message": ""},
            {"event_name": "artifact", "stage": "researcher", "status": "completed", "payload": {"artifact_key": "researcher", "artifact_data": {}}, "message": ""},
            {"event_name": "stage_complete", "stage": "drafter", "status": "completed", "payload": {}, "message": ""},
        ]
        evidence = [{"tier": "verbatim"} for _ in range(5)]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job(
            "j1", job_status="succeeded", evidence_items=evidence,
        )
        assert "researcher" in report.artifacts_present
        assert "drafter" in report.artifacts_missing

    @pytest.mark.asyncio
    async def test_replay_suggests_regression_target(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cv_generation", "workflow_id": "w1"}, "message": ""},
            {"event_name": "stage_timeout", "stage": "drafter", "status": "timed_out", "payload": {}, "message": ""},
        ]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job("j1", job_status="failed")
        assert report.suggested_regression_target == "test_lifecycle_hardening.py"

    @pytest.mark.asyncio
    async def test_replay_evidence_tier_distribution(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cv_generation", "workflow_id": "w1"}, "message": ""},
        ]
        evidence = [
            {"tier": "verbatim"},
            {"tier": "verbatim"},
            {"tier": "derived"},
            {"tier": "inferred"},
            {"tier": "inferred"},
            {"tier": "inferred"},
        ]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job(
            "j1", job_status="failed", evidence_items=evidence,
        )
        assert report.evidence_tier_distribution == {
            "verbatim": 2, "derived": 1, "inferred": 3,
        }

    @pytest.mark.asyncio
    async def test_report_to_dict_roundtrip(self):
        events = [
            {"event_name": "workflow_start", "stage": None, "status": None, "payload": {"pipeline_name": "cv_generation", "workflow_id": "w1"}, "message": ""},
            {"event_name": "stage_timeout", "stage": "researcher", "status": "timed_out", "payload": {}, "message": ""},
        ]
        store = _make_mock_store(events)
        runner = ReplayRunner(store)
        report = await runner.replay_job("j1", job_status="failed")
        d = report.to_dict()
        assert d["failure_class"] == "stage_timeout"
        assert d["job_id"] == "j1"
        assert isinstance(d["completed_stages"], list)
