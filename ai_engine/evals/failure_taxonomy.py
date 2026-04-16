"""
Failure Taxonomy — fixed classification of pipeline failure modes.

Each class represents a distinct root-cause category that a replay
analysis can detect from persisted job state without requiring
access to the original LLM session.
"""
from __future__ import annotations

from enum import Enum


class FailureClass(str, Enum):
    """Top-level failure classification for pipeline replay analysis."""

    CONTRACT_DRIFT = "contract_drift"
    ARTIFACT_GAP = "artifact_gap"
    EVIDENCE_BINDING_MISS = "evidence_binding_miss"
    CITATION_FRESHNESS_MISS = "citation_freshness_miss"
    STAGE_TIMEOUT = "stage_timeout"
    PROVIDER_FAILURE = "provider_failure"
    PLANNER_MISCLASSIFICATION = "planner_misclassification"
    LOW_EVIDENCE_INPUT = "low_evidence_input"
    VALIDATOR_ESCAPE = "validator_escape"
    UNKNOWN = "unknown"

    @classmethod
    def all_classes(cls) -> list[str]:
        return [c.value for c in cls]


# ═══════════════════════════════════════════════════════════════════════
#  Classification engine — detects failure class from job artifacts
# ═══════════════════════════════════════════════════════════════════════

def classify_failure(
    *,
    events: list[dict],
    evidence_items: list[dict],
    citations: list[dict],
    job_status: str,
    stage_statuses: dict[str, str],
) -> tuple[FailureClass, str]:
    """Classify a failed or low-quality job into a taxonomy class.

    Returns (FailureClass, human-readable reason string).
    """

    # Check for stage timeout
    for stage, status in stage_statuses.items():
        if status == "timed_out":
            return FailureClass.STAGE_TIMEOUT, f"Stage '{stage}' timed out"

    # Check for provider failure (stage failed with no further detail)
    failed_stages = [s for s, st in stage_statuses.items() if st == "failed"]
    if failed_stages:
        # Check event payloads for provider-related error messages
        for ev in events:
            payload = ev.get("payload") or {}
            error = payload.get("error", "") or ev.get("message", "")
            if any(kw in error.lower() for kw in ("api", "rate limit", "429", "500", "503", "timeout", "provider")):
                return (
                    FailureClass.PROVIDER_FAILURE,
                    f"Provider failure in stage '{failed_stages[0]}': {error[:200]}",
                )
        return (
            FailureClass.PROVIDER_FAILURE,
            f"Stage '{failed_stages[0]}' failed",
        )

    # Check for artifact gap — expected stages completed but missing artifacts
    # Only flag if at least one artifact event exists (otherwise the pipeline
    # may not have had artifact persistence enabled at all)
    expected_artifact_stages = {"researcher", "drafter"}
    completed_stages = {s for s, st in stage_statuses.items() if st == "completed"}
    artifact_events = {
        ev.get("stage") or (ev.get("payload") or {}).get("artifact_key", "")
        for ev in events
        if ev.get("event_name") == "artifact"
    }
    if artifact_events:
        missing_artifacts = expected_artifact_stages & completed_stages - artifact_events
        if missing_artifacts:
            return (
                FailureClass.ARTIFACT_GAP,
                f"Stage(s) completed but missing artifacts: {sorted(missing_artifacts)}",
            )

    # Check for low evidence input
    if len(evidence_items) < 3:
        return (
            FailureClass.LOW_EVIDENCE_INPUT,
            f"Only {len(evidence_items)} evidence items — insufficient for reliable generation",
        )

    # Check for contract drift in events
    for ev in events:
        msg = ev.get("message", "")
        if "contract_drift" in msg.lower():
            stage = ev.get("stage", "unknown")
            return (
                FailureClass.CONTRACT_DRIFT,
                f"Contract drift detected at stage '{stage}'",
            )

    # Check for evidence binding miss — citations present but unlinked
    unlinked_citations = [
        c for c in citations
        if not c.get("evidence_ids")
    ]
    if citations and len(unlinked_citations) > len(citations) * 0.5:
        return (
            FailureClass.EVIDENCE_BINDING_MISS,
            f"{len(unlinked_citations)}/{len(citations)} citations have no linked evidence",
        )

    # Check for citation freshness miss — claims classified as unsupported/fabricated
    fabricated_count = sum(
        1 for c in citations
        if c.get("classification") in ("fabricated", "unsupported")
    )
    if fabricated_count > 0:
        return (
            FailureClass.CITATION_FRESHNESS_MISS,
            f"{fabricated_count} claims classified as fabricated/unsupported",
        )

    # Check for validator escape — validator passed but quality is questionable
    validator_events = [
        ev for ev in events
        if ev.get("stage") == "validator" and ev.get("event_name") == "stage_complete"
    ]
    for ev in validator_events:
        payload = ev.get("payload") or {}
        artifact = payload.get("artifact_data", {})
        content = artifact.get("content", {})
        if isinstance(content, dict) and content.get("valid") is True:
            issues = content.get("issues", [])
            critical = [i for i in issues if isinstance(i, dict) and i.get("severity") == "critical"]
            if critical:
                return (
                    FailureClass.VALIDATOR_ESCAPE,
                    f"Validator passed but {len(critical)} critical issues present",
                )

    # Default
    if job_status in ("failed", "error"):
        return FailureClass.UNKNOWN, "Job failed with no identifiable root cause"

    return FailureClass.UNKNOWN, "Unable to classify — manual review recommended"
