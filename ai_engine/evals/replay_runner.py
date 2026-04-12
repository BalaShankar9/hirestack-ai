"""
Replay Runner — reconstructs and diagnoses failed/low-quality pipeline runs
from persisted state (events, evidence, citations).

Usage:
    report = await ReplayRunner(event_store).replay_job(job_id)
    print(report.summary_line)

The replay runner never re-invokes LLM agents. It reconstructs the job
timeline from the event log, loads evidence and citations, identifies the
last safe stage boundary, and classifies the failure.
"""
from __future__ import annotations

from typing import Any, Optional

import structlog

from ai_engine.agents.workflow_runtime import (
    WorkflowEventStore,
    WorkflowState,
    StageStatus,
    reconstruct_state,
    get_stage_artifacts,
)
from ai_engine.evals.failure_taxonomy import FailureClass, classify_failure
from ai_engine.evals.replay_report import ReplayReport

logger = structlog.get_logger("hirestack.evals.replay_runner")

# Expected stages that should have artifacts in a normal pipeline run
_EXPECTED_ARTIFACT_STAGES = frozenset({
    "researcher", "drafter",
})

# Map stage status values to ReplayReport lists
_STATUS_BUCKETS = {
    "completed": "completed_stages",
    "failed": "failed_stages",
    "skipped": "skipped_stages",
    "timed_out": "timed_out_stages",
}


class ReplayRunner:
    """Offline replay engine for failed or low-quality pipeline jobs."""

    def __init__(self, event_store: WorkflowEventStore):
        self._store = event_store

    async def replay_job(
        self,
        job_id: str,
        *,
        pipeline_name: Optional[str] = None,
        evidence_items: Optional[list[dict]] = None,
        citations: Optional[list[dict]] = None,
        job_status: str = "failed",
    ) -> ReplayReport:
        """Replay a job from its persisted event log.

        Args:
            job_id: The generation job ID.
            pipeline_name: Optional pipeline name filter. If None, uses
                           the first workflow_start event found.
            evidence_items: Pre-loaded evidence items (avoids DB call if
                           the caller already has them).
            citations: Pre-loaded citations.
            job_status: The job's current status from generation_jobs.

        Returns:
            A ReplayReport with timeline, artifact check, evidence summary,
            failure classification, and suggested regression target.
        """
        # Load events
        events = await self._store.load_events(job_id)
        if not events:
            return ReplayReport(
                job_id=job_id,
                pipeline_name=pipeline_name or "unknown",
                job_status=job_status,
                failure_class=FailureClass.UNKNOWN,
                likely_root_cause="No events found for job — cannot replay",
                event_count=0,
            )

        # Determine pipeline name from events if not provided
        if not pipeline_name:
            for ev in events:
                if ev.get("event_name") == "workflow_start":
                    pipeline_name = (ev.get("payload") or {}).get("pipeline_name", "unknown")
                    break
            pipeline_name = pipeline_name or "unknown"

        # Reconstruct stage statuses from events
        stage_statuses: dict[str, str] = {}
        for ev in events:
            stage = ev.get("stage") or ev.get("agent_name")
            status = ev.get("status")
            if stage and status:
                stage_statuses[stage] = status

        # Identify artifacts from artifact events
        artifacts_present: set[str] = set()
        for ev in events:
            if ev.get("event_name") == "artifact":
                payload = ev.get("payload") or {}
                key = payload.get("artifact_key", "") or ev.get("stage", "")
                if key:
                    artifacts_present.add(key)

        completed = {s for s, st in stage_statuses.items() if st == "completed"}
        artifacts_missing = list(
            (_EXPECTED_ARTIFACT_STAGES & completed) - artifacts_present
        )

        # Evidence summary
        evidence_items = evidence_items or []
        tier_dist: dict[str, int] = {}
        for item in evidence_items:
            tier = item.get("tier", "unknown")
            tier_dist[tier] = tier_dist.get(tier, 0) + 1

        # Citation summary
        citations = citations or []
        unlinked = sum(1 for c in citations if not c.get("evidence_ids"))
        fabricated = sum(
            1 for c in citations
            if c.get("classification") in ("fabricated", "unsupported")
        )

        # Classify failure
        failure_class, root_cause = classify_failure(
            events=events,
            evidence_items=evidence_items,
            citations=citations,
            job_status=job_status,
            stage_statuses=stage_statuses,
        )

        # Build suggested regression target
        regression_target = self._suggest_regression_target(
            failure_class, stage_statuses, pipeline_name,
        )

        # Build report
        report = ReplayReport(
            job_id=job_id,
            pipeline_name=pipeline_name,
            job_status=job_status,
            completed_stages=sorted(s for s, st in stage_statuses.items() if st == "completed"),
            failed_stages=sorted(s for s, st in stage_statuses.items() if st == "failed"),
            skipped_stages=sorted(s for s, st in stage_statuses.items() if st == "skipped"),
            timed_out_stages=sorted(s for s, st in stage_statuses.items() if st == "timed_out"),
            artifacts_present=sorted(artifacts_present),
            artifacts_missing=sorted(artifacts_missing),
            evidence_count=len(evidence_items),
            evidence_tier_distribution=tier_dist,
            citation_count=len(citations),
            unlinked_citation_count=unlinked,
            fabricated_claim_count=fabricated,
            failure_class=failure_class,
            likely_root_cause=root_cause,
            suggested_regression_target=regression_target,
            event_count=len(events),
        )

        logger.info(
            "replay_complete",
            job_id=job_id,
            pipeline=pipeline_name,
            failure_class=failure_class.value,
            root_cause=root_cause[:200],
        )

        return report

    @staticmethod
    def _suggest_regression_target(
        failure_class: FailureClass,
        stage_statuses: dict[str, str],
        pipeline_name: str,
    ) -> Optional[str]:
        """Suggest a test target for a given failure classification."""
        mapping = {
            FailureClass.CONTRACT_DRIFT: "test_contracts.py",
            FailureClass.ARTIFACT_GAP: "test_lifecycle_hardening.py",
            FailureClass.EVIDENCE_BINDING_MISS: "test_evidence.py",
            FailureClass.CITATION_FRESHNESS_MISS: "test_evidence.py",
            FailureClass.STAGE_TIMEOUT: "test_lifecycle_hardening.py",
            FailureClass.PROVIDER_FAILURE: "test_orchestrator.py",
            FailureClass.LOW_EVIDENCE_INPUT: "test_evidence.py",
            FailureClass.VALIDATOR_ESCAPE: "test_contracts.py",
        }
        return mapping.get(failure_class)
