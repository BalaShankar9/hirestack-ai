"""
Replay Report — structured diagnostic artifact from pipeline replay.

Produced by the ReplayRunner after analyzing a job's persisted state.
Can be attached to regression tests or gold corpus cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ai_engine.evals.failure_taxonomy import FailureClass


@dataclass
class ReplayReport:
    """Diagnostic report produced by replaying a failed/low-quality job."""

    job_id: str
    pipeline_name: str
    job_status: str

    # Stage timeline
    completed_stages: list[str] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)
    skipped_stages: list[str] = field(default_factory=list)
    timed_out_stages: list[str] = field(default_factory=list)

    # Artifact presence
    artifacts_present: list[str] = field(default_factory=list)
    artifacts_missing: list[str] = field(default_factory=list)

    # Evidence summary
    evidence_count: int = 0
    evidence_tier_distribution: dict[str, int] = field(default_factory=dict)

    # Citation summary
    citation_count: int = 0
    unlinked_citation_count: int = 0
    fabricated_claim_count: int = 0

    # Failure classification
    failure_class: FailureClass = FailureClass.UNKNOWN
    likely_root_cause: str = ""

    # Suggested regression target
    suggested_regression_target: Optional[str] = None

    # Total events processed
    event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "pipeline_name": self.pipeline_name,
            "job_status": self.job_status,
            "completed_stages": self.completed_stages,
            "failed_stages": self.failed_stages,
            "skipped_stages": self.skipped_stages,
            "timed_out_stages": self.timed_out_stages,
            "artifacts_present": self.artifacts_present,
            "artifacts_missing": self.artifacts_missing,
            "evidence_count": self.evidence_count,
            "evidence_tier_distribution": self.evidence_tier_distribution,
            "citation_count": self.citation_count,
            "unlinked_citation_count": self.unlinked_citation_count,
            "fabricated_claim_count": self.fabricated_claim_count,
            "failure_class": self.failure_class.value,
            "likely_root_cause": self.likely_root_cause,
            "suggested_regression_target": self.suggested_regression_target,
            "event_count": self.event_count,
        }

    @property
    def is_failure(self) -> bool:
        return self.job_status in ("failed", "error") or bool(self.failed_stages)

    @property
    def summary_line(self) -> str:
        return (
            f"[{self.failure_class.value}] {self.pipeline_name} job={self.job_id[:8]}… "
            f"— {self.likely_root_cause}"
        )
