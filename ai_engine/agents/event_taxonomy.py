"""
Canonical event taxonomy for HireStack pipeline + agent execution.

Phase 1 of the world-class roadmap (canonical execution + truth foundation).
Single source of truth for every event type emitted by:

* `backend/app/services/pipeline_runtime.py` (PipelineRuntime / EventSink)
* `ai_engine/agent_events.py` (in-process agent telemetry bus)
* `backend/app/api/routes/generate/jobs.py` (DB-backed job event log)

Goal: any consumer (frontend dock, eval replay, analytics) can validate
events against this taxonomy. New event types must be added here first
so the schema stays observable.
"""
from __future__ import annotations

from typing import FrozenSet


# ─── Pipeline lifecycle events ──────────────────────────────────────
# Emitted by PipelineRuntime through its EventSink.

PROGRESS = "progress"            # phase progress + percentage
DETAIL = "detail"                # human-readable substep / sub-message
COMPLETE = "complete"            # pipeline reached terminal success
ERROR = "error"                  # pipeline failed (terminal)
WARNING = "warning"              # non-fatal warning during a phase

# ─── Agent + orchestration events ───────────────────────────────────
# Emitted by AgentPipeline + agent_events.py emitter helpers.

AGENT_STATUS = "agent_status"          # named pipeline/stage status update
PLAN_CREATED = "plan_created"          # planner emitted a plan artifact
TOOL_CALL = "tool_call"                # tool/function invocation starting
TOOL_RESULT = "tool_result"            # tool invocation finished
CACHE_HIT = "cache_hit"                # cache lookup served from memory/db
EVIDENCE_ADDED = "evidence_added"      # ledger gained an evidence item
POLICY_DECISION = "policy_decision"    # orchestration branched/retried
VALIDATION_PASSED = "validation_passed"
VALIDATION_FAILED = "validation_failed"

# ─── Canonical sets (use for runtime validation / dashboards) ──────

PIPELINE_LIFECYCLE_EVENTS: FrozenSet[str] = frozenset({
    PROGRESS, DETAIL, COMPLETE, ERROR, WARNING,
})

AGENT_EVENTS: FrozenSet[str] = frozenset({
    AGENT_STATUS, PLAN_CREATED, TOOL_CALL, TOOL_RESULT,
    CACHE_HIT, EVIDENCE_ADDED, POLICY_DECISION,
    VALIDATION_PASSED, VALIDATION_FAILED,
})

CANONICAL_EVENT_TYPES: FrozenSet[str] = (
    PIPELINE_LIFECYCLE_EVENTS | AGENT_EVENTS
)

# ─── Execution path tags (Phase 1: canonical-vs-legacy auditing) ───
# Every PipelineRuntime event carries data["execution_path"] == one of these,
# so monitoring can alert when production traffic falls back to legacy.

EXECUTION_PATH_AGENT = "agent"      # full orchestrator stack (default)
EXECUTION_PATH_LEGACY = "legacy"    # direct chains, no orchestrator
EXECUTION_PATH_UNKNOWN = "unknown"  # pre-dispatch (early init events)


def is_canonical(event_type: str) -> bool:
    """Return True when ``event_type`` belongs to the documented taxonomy."""
    return event_type in CANONICAL_EVENT_TYPES
