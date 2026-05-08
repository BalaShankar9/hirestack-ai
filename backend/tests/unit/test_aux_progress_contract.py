from ai_engine.agents.orchestration import (
    ORCHESTRATION_PROGRESS_SCHEMA_VERSION,
    WorkflowProgressEvent,
    coerce_progress_event,
)
from ai_engine.agents.ppt.orchestrator import GenerationProgress, GenerationStatus


def test_workflow_progress_event_serializes_canonical_payload() -> None:
    event = WorkflowProgressEvent(
        pipeline_name="cv_generation",
        stage="drafter",
        status="running",
        latency_ms=125,
        message="Drafting first pass",
    )

    payload = event.to_payload()

    assert payload == {
        "schema_version": ORCHESTRATION_PROGRESS_SCHEMA_VERSION,
        "event_type": "agent_status",
        "pipeline_name": "cv_generation",
        "stage": "drafter",
        "phase": "drafter",
        "status": "running",
        "latency_ms": 125,
        "message": "Drafting first pass",
    }


def test_coerce_progress_event_accepts_legacy_payloads() -> None:
    event = coerce_progress_event(
        {
            "pipeline_name": "benchmark",
            "stage": "researcher",
            "status": "completed",
            "latency_ms": 240,
            "message": "done",
        }
    )

    assert event.pipeline_name == "benchmark"
    assert event.stage == "researcher"
    assert event.phase_name == "researcher"
    assert event.status_value == "completed"


def test_generation_progress_exports_shared_payload_shape() -> None:
    progress = GenerationProgress(
        status=GenerationStatus.PLANNING,
        percent=12,
        message="Planning deck",
        phase="outline",
        latency_so_far_ms=30,
        workflow_id="wf-1",
    )

    payload = progress.to_payload()

    assert payload["schema_version"] == ORCHESTRATION_PROGRESS_SCHEMA_VERSION
    assert payload["event_type"] == "progress"
    assert payload["pipeline_name"] == "ppt_generation"
    assert payload["stage"] == "outline"
    assert payload["phase"] == "outline"
    assert payload["status"] == GenerationStatus.PLANNING.value
    assert payload["progress"] == 12
    assert payload["workflow_id"] == "wf-1"