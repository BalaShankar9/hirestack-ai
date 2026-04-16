"""
Durable Workflow Runtime — event-sourced, resumable pipeline execution.

Wraps AgentPipeline.execute() with:
  - Per-stage checkpointing to generation_job_events
  - Heartbeat emission during long-running stages
  - Per-stage timeout enforcement
  - Resumability: can reconstruct state from event log after restart
  - Cancellation propagation via DB flag polling
  - Structured StageResult artifacts passed between stages

This replaces raw asyncio.create_task() with durable, observable execution.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.workflow_runtime")


# ═══════════════════════════════════════════════════════════════════════
#  Stage definitions
# ═══════════════════════════════════════════════════════════════════════

class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass
class StageCheckpoint:
    """Persisted checkpoint for a single pipeline stage."""
    stage_name: str
    status: StageStatus
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    latency_ms: int = 0
    output_key: Optional[str] = None       # Key in WorkflowState.artifacts
    error: Optional[str] = None
    attempt: int = 1
    max_retries: int = 1
    heartbeat_at: Optional[str] = None


@dataclass
class WorkflowState:
    """In-memory state for a running workflow, reconstructable from event log."""
    workflow_id: str
    pipeline_name: str
    user_id: str
    job_id: str
    application_id: str
    stages: dict[str, StageCheckpoint] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    current_stage: Optional[str] = None
    status: str = "running"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sequence_no: int = 0

    def next_sequence(self) -> int:
        self.sequence_no += 1
        return self.sequence_no


# ═══════════════════════════════════════════════════════════════════════
#  Stage definitions with timeout and retry config
# ═══════════════════════════════════════════════════════════════════════

# Per-stage timeout in seconds.  Set to None to disable timeouts.
# Phase-level timeouts have been removed — future document types may
# take variable time and premature timeouts waste effort.
DEFAULT_STAGE_TIMEOUTS: dict[str, int] = {}

DEFAULT_STAGE_RETRIES: dict[str, int] = {
    "researcher": 2,
    "drafter": 1,
    "critic": 1,
    "optimizer": 1,
    "fact_checker": 1,
    "validator": 1,
    "drafter_revision": 1,
    "critic_re_eval": 1,
}

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 10


# ═══════════════════════════════════════════════════════════════════════
#  Event persistence interface
# ═══════════════════════════════════════════════════════════════════════

class WorkflowEventStore:
    """Persists workflow events to generation_job_events table.

    Accepts a Supabase client and table name map. All writes use
    asyncio.to_thread to avoid blocking the event loop.
    """

    def __init__(self, db: Any, tables: dict[str, str]):
        self._db = db
        self._tables = tables

    async def emit(
        self,
        state: WorkflowState,
        event_name: str,
        stage: Optional[str] = None,
        status: Optional[str] = None,
        message: str = "",
        payload: Optional[dict] = None,
        latency_ms: int = 0,
    ) -> None:
        """Persist a single event row."""
        seq = state.next_sequence()
        row = {
            "job_id": state.job_id,
            "user_id": state.user_id,
            "application_id": state.application_id,
            "sequence_no": seq,
            "event_name": event_name,
            "agent_name": stage,
            "stage": stage,
            "status": status,
            "message": message,
            "latency_ms": latency_ms,
            "payload": payload or {},
        }
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_job_events"])
                .upsert(row, on_conflict="job_id,sequence_no")
                .execute()
            )
        except Exception as e:
            # NOTE: 'event' is a reserved keyword in structlog — use 'event_name' instead
            logger.warning("workflow_event_persist_failed", event_name=event_name, error_msg=str(e))

    async def load_events(self, job_id: str) -> list[dict]:
        """Load all events for a job, ordered by auto-increment id for deterministic replay."""
        try:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_job_events"])
                .select("*")
                .eq("job_id", job_id)
                .order("id")
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.warning("workflow_events_load_failed", job_id=job_id, error=str(e))
            return []

    async def update_job(self, job_id: str, patch: dict) -> None:
        """Update the generation_jobs row."""
        if not patch:
            return
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_jobs"])
                .update(patch)
                .eq("id", job_id)
                .execute()
            )
        except Exception as e:
            logger.warning("workflow_job_update_failed", job_id=job_id, error=str(e))

    async def check_cancel(self, job_id: str) -> bool:
        """Poll the cancel_requested flag."""
        try:
            r = await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_jobs"])
                .select("cancel_requested")
                .eq("id", job_id)
                .maybe_single()
                .execute()
            )
            return bool((r.data or {}).get("cancel_requested"))
        except Exception as exc:
            logger.warning("cancel_check_failed", job_id=job_id, error=str(exc)[:200])
            return False

    async def persist_evidence(
        self, job_id: str, user_id: str, ledger_items: list[dict],
    ) -> None:
        """Bulk-insert evidence ledger items into evidence_ledger_items table."""
        table_name = self._tables.get("evidence_ledger_items")
        if not table_name or not ledger_items:
            return
        rows = [
            {
                "id": item["id"],
                "job_id": job_id,
                "user_id": user_id,
                "tier": item["tier"],
                "source": item["source"],
                "source_field": item.get("source_field", ""),
                "evidence_text": item["text"],
                "metadata": item.get("metadata", {}),
            }
            for item in ledger_items
        ]
        try:
            await asyncio.to_thread(
                lambda: self._db.table(table_name)
                .upsert(rows, on_conflict="job_id,id")
                .execute()
            )
        except Exception as e:
            logger.warning("evidence_persist_failed", job_id=job_id, error=str(e))

    async def persist_citations(
        self, job_id: str, user_id: str, citations: list[dict],
    ) -> None:
        """Bulk-insert claim citations into claim_citations table."""
        table_name = self._tables.get("claim_citations")
        if not table_name or not citations:
            return
        rows = [
            {
                "job_id": job_id,
                "user_id": user_id,
                "claim_text": c.get("claim_text", ""),
                "evidence_ids": c.get("evidence_ids", []),
                "classification": c.get("classification", ""),
                "confidence": c.get("confidence", 0),
                "tier": c.get("tier", ""),
            }
            for c in citations
        ]
        try:
            await asyncio.to_thread(
                lambda: self._db.table(table_name)
                .insert(rows)
                .execute()
            )
        except Exception as e:
            logger.warning("citations_persist_failed", job_id=job_id, error=str(e))

    async def persist_artifact(
        self,
        state: WorkflowState,
        stage_name: str,
        artifact: dict,
    ) -> None:
        """Persist a stage output artifact as an event for later rehydration."""
        await self.emit(
            state,
            event_name="artifact",
            stage=stage_name,
            status="completed",
            message=f"Artifact for {stage_name}",
            payload={
                "artifact_key": stage_name,
                "artifact_data": artifact,
            },
        )

    async def load_events_for_pipeline(
        self, job_id: str, pipeline_name: str,
    ) -> list[dict]:
        """Load events for a specific pipeline within a job.

        Filters by workflow_start payload.pipeline_name to isolate
        events belonging to one pipeline (CV, cover_letter, etc.).
        """
        all_events = await self.load_events(job_id)
        if not all_events:
            return []

        # Find workflow_start events to segment by pipeline
        pipeline_workflow_ids: set[str] = set()
        for ev in all_events:
            if ev.get("event_name") == "workflow_start":
                payload = ev.get("payload") or {}
                if payload.get("pipeline_name") == pipeline_name:
                    wid = payload.get("workflow_id", "")
                    if wid:
                        pipeline_workflow_ids.add(wid)

        if not pipeline_workflow_ids:
            return []

        # Filter events: include workflow_start for this pipeline plus all
        # subsequent events that share the same sequence range
        # Simple approach: collect events between workflow_start and workflow_complete
        # for this pipeline by tracking active workflow_id in payloads
        result: list[dict] = []
        active = False
        for ev in all_events:
            payload = ev.get("payload") or {}
            if ev.get("event_name") == "workflow_start":
                wid = payload.get("workflow_id", "")
                if wid in pipeline_workflow_ids:
                    active = True
                else:
                    active = False
            if active:
                result.append(ev)
            if active and ev.get("event_name") in ("workflow_complete", "workflow_failed"):
                active = False

        return result


# ═══════════════════════════════════════════════════════════════════════
#  Stage executor — runs a single stage with timeout, retry, heartbeat
# ═══════════════════════════════════════════════════════════════════════

async def _heartbeat_loop(
    store: WorkflowEventStore,
    state: WorkflowState,
    stage_name: str,
    cancel_event: asyncio.Event,
) -> None:
    """Emit heartbeat events until the stage completes or is cancelled."""
    while not cancel_event.is_set():
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=HEARTBEAT_INTERVAL)
            return  # cancel_event was set
        except asyncio.TimeoutError:
            pass  # interval elapsed, emit heartbeat

        now = datetime.now(timezone.utc).isoformat()
        checkpoint = state.stages.get(stage_name)
        if checkpoint:
            checkpoint.heartbeat_at = now

        await store.emit(
            state,
            event_name="heartbeat",
            stage=stage_name,
            status="running",
            message=f"{stage_name} still running",
            payload={"heartbeat_at": now},
        )

        # Piggyback cancel check on heartbeat
        if await store.check_cancel(state.job_id):
            cancel_event.set()
            return


async def execute_stage(
    stage_name: str,
    coro_factory: Callable[[], Any],
    state: WorkflowState,
    store: WorkflowEventStore,
    *,
    timeout: Optional[int] = None,
    max_retries: Optional[int] = None,
    on_progress: Optional[Callable] = None,
) -> Any:
    """Execute a single pipeline stage with durability guarantees.

    v3.1: True mid-stage cancellation — the stage coroutine runs as an
    asyncio.Task.  When the heartbeat detects cancel_requested in the DB,
    it sets cancel_event which triggers a watcher that cancels the running
    task immediately rather than waiting for natural completion.

    Note: cancellation is best-effort.  If the underlying LLM call does
    not honour asyncio cancellation, the HTTP request may complete in the
    background after the stage is marked cancelled.

    Args:
        stage_name: Unique name for this stage (e.g., "researcher", "drafter_revision_1")
        coro_factory: Zero-arg callable that returns the coroutine to run.
        state: Current workflow state (mutated in place).
        store: Event persistence store.
        timeout: Per-stage timeout in seconds (default from config).
        max_retries: Max retry attempts (default from config).
        on_progress: Optional SSE callback for frontend updates.

    Returns:
        The result of the coroutine.

    Raises:
        WorkflowCancelled: If cancel was requested.
        WorkflowStageTimeout: If stage exceeded timeout.
        WorkflowStageFailed: If all retries exhausted.
    """
    timeout = timeout or DEFAULT_STAGE_TIMEOUTS.get(stage_name.split("_")[0]) or None
    max_retries = max_retries or DEFAULT_STAGE_RETRIES.get(stage_name.split("_")[0], 1)

    checkpoint = StageCheckpoint(
        stage_name=stage_name,
        status=StageStatus.PENDING,
        max_retries=max_retries,
    )
    state.stages[stage_name] = checkpoint
    state.current_stage = stage_name

    for attempt in range(1, max_retries + 1):
        checkpoint.attempt = attempt
        checkpoint.status = StageStatus.RUNNING
        checkpoint.started_at = datetime.now(timezone.utc).isoformat()

        # Emit stage_start event
        await store.emit(
            state,
            event_name="stage_start",
            stage=stage_name,
            status="running",
            message=f"Starting {stage_name} (attempt {attempt}/{max_retries})",
            payload={"attempt": attempt, "max_retries": max_retries, "timeout": timeout},
        )

        if on_progress:
            try:
                await on_progress({
                    "pipeline_name": state.pipeline_name,
                    "stage": stage_name,
                    "status": "running",
                    "message": f"Starting {stage_name}",
                })
            except Exception:
                pass

        # Start heartbeat (sets cancel_event when DB cancel detected)
        cancel_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(store, state, stage_name, cancel_event)
        )

        # Run stage as a cancellable task
        stage_task = asyncio.create_task(coro_factory())

        # Watcher: propagate cancel_event → task.cancel()
        async def _cancel_watcher(_task: asyncio.Task = stage_task, _evt: asyncio.Event = cancel_event) -> None:
            await _evt.wait()
            if not _task.done():
                _task.cancel()

        watcher = asyncio.create_task(_cancel_watcher())

        try:
            # Wait for the task to complete or timeout
            done, _ = await asyncio.wait({stage_task}, timeout=timeout)

            if not done:
                # ── Timeout ──
                stage_task.cancel()
                try:
                    await stage_task
                except (asyncio.CancelledError, Exception):
                    pass
                elapsed = _elapsed_ms(checkpoint.started_at)

                if attempt >= max_retries:
                    checkpoint.status = StageStatus.TIMED_OUT
                    checkpoint.finished_at = datetime.now(timezone.utc).isoformat()
                    checkpoint.latency_ms = elapsed
                    checkpoint.error = f"Timed out after {timeout}s"

                    await store.emit(
                        state,
                        event_name="stage_timeout",
                        stage=stage_name,
                        status="timed_out",
                        message=f"{stage_name} timed out after {timeout}s",
                        latency_ms=elapsed,
                    )
                    raise WorkflowStageTimeout(stage_name, timeout)

                logger.warning("stage_timeout_retrying", stage=stage_name, attempt=attempt)
                # Check cancel between retries
                if await store.check_cancel(state.job_id):
                    checkpoint.status = StageStatus.CANCELLED
                    checkpoint.finished_at = datetime.now(timezone.utc).isoformat()
                    raise WorkflowCancelled(stage_name)
                continue  # retry

            # Task completed — check outcome
            if stage_task.cancelled():
                # ── Cancelled by watcher (DB cancel_requested) ──
                elapsed = _elapsed_ms(checkpoint.started_at)
                checkpoint.status = StageStatus.CANCELLED
                checkpoint.finished_at = datetime.now(timezone.utc).isoformat()
                checkpoint.error = "Cancelled"
                await store.emit(
                    state,
                    event_name="stage_cancelled",
                    stage=stage_name,
                    status="cancelled",
                    message=f"{stage_name} cancelled",
                    latency_ms=elapsed,
                )
                raise WorkflowCancelled(stage_name)

            exc = stage_task.exception()
            if exc is not None:
                if isinstance(exc, WorkflowCancelled):
                    checkpoint.status = StageStatus.CANCELLED
                    checkpoint.finished_at = datetime.now(timezone.utc).isoformat()
                    raise exc

                # ── Stage raised an error ──
                elapsed = _elapsed_ms(checkpoint.started_at)
                if attempt >= max_retries:
                    checkpoint.status = StageStatus.FAILED
                    checkpoint.finished_at = datetime.now(timezone.utc).isoformat()
                    checkpoint.latency_ms = elapsed
                    checkpoint.error = str(exc)

                    await store.emit(
                        state,
                        event_name="stage_failed",
                        stage=stage_name,
                        status="failed",
                        message=f"{stage_name} failed: {str(exc)[:200]}",
                        latency_ms=elapsed,
                        payload={"attempt": attempt, "error": str(exc)[:500]},
                    )
                    raise WorkflowStageFailed(stage_name, exc)

                logger.warning(
                    "stage_error_retrying",
                    stage=stage_name,
                    attempt=attempt,
                    error=str(exc),
                )
                # Check cancel between retries
                if await store.check_cancel(state.job_id):
                    checkpoint.status = StageStatus.CANCELLED
                    checkpoint.finished_at = datetime.now(timezone.utc).isoformat()
                    raise WorkflowCancelled(stage_name)
                continue  # retry

            # ── Success ──
            result = stage_task.result()
            elapsed = _elapsed_ms(checkpoint.started_at)
            checkpoint.status = StageStatus.COMPLETED
            checkpoint.finished_at = datetime.now(timezone.utc).isoformat()
            checkpoint.latency_ms = elapsed

            await store.emit(
                state,
                event_name="stage_complete",
                stage=stage_name,
                status="completed",
                message=f"{stage_name} completed",
                latency_ms=elapsed,
                payload={"attempt": attempt},
            )

            if on_progress:
                try:
                    await on_progress({
                        "pipeline_name": state.pipeline_name,
                        "stage": stage_name,
                        "status": "completed",
                        "latency_ms": elapsed,
                    })
                except Exception:
                    pass

            return result

        finally:
            # Ensure heartbeat and watcher are cleaned up
            cancel_event.set()
            watcher.cancel()
            try:
                await watcher
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass

    # Should not reach here, but satisfy type checker
    raise WorkflowStageFailed(stage_name, RuntimeError("Exhausted retries"))


async def skip_stage(
    stage_name: str,
    state: WorkflowState,
    reason: str = "Policy: skipped",
    store: Optional[WorkflowEventStore] = None,
) -> None:
    """Mark a stage as skipped in the workflow state and persist the event."""
    state.stages[stage_name] = StageCheckpoint(
        stage_name=stage_name,
        status=StageStatus.SKIPPED,
    )
    if store:
        await store.emit(
            state,
            event_name="stage_skipped",
            stage=stage_name,
            status="skipped",
            message=reason,
        )


# ═══════════════════════════════════════════════════════════════════════
#  State reconstruction from event log (for resumability)
# ═══════════════════════════════════════════════════════════════════════

def reconstruct_state(events: list[dict], job_id: str) -> WorkflowState:
    """Rebuild WorkflowState from persisted event log.

    Used after server restart to determine which stages completed
    and what the last known state was, enabling resume decisions.
    """
    state = WorkflowState(
        workflow_id="",
        pipeline_name="",
        user_id="",
        job_id=job_id,
        application_id="",
    )

    for event in events:
        seq = event.get("sequence_no", 0)
        state.sequence_no = max(state.sequence_no, seq)

        event_name = event.get("event_name", "")
        stage = event.get("stage") or event.get("agent_name")
        payload = event.get("payload") or {}

        if event_name == "workflow_start":
            state.workflow_id = payload.get("workflow_id", "")
            state.pipeline_name = payload.get("pipeline_name", "")
            state.user_id = event.get("user_id", "")
            state.application_id = event.get("application_id", "")

        elif event_name == "stage_start" and stage:
            state.stages[stage] = StageCheckpoint(
                stage_name=stage,
                status=StageStatus.RUNNING,
                started_at=event.get("created_at"),
                attempt=payload.get("attempt", 1),
                max_retries=payload.get("max_retries", 1),
            )
            state.current_stage = stage

        elif event_name == "stage_complete" and stage:
            if stage in state.stages:
                state.stages[stage].status = StageStatus.COMPLETED
                state.stages[stage].finished_at = event.get("created_at")
                state.stages[stage].latency_ms = event.get("latency_ms", 0)

        elif event_name == "stage_failed" and stage:
            if stage in state.stages:
                state.stages[stage].status = StageStatus.FAILED
                state.stages[stage].finished_at = event.get("created_at")
                state.stages[stage].error = payload.get("error")

        elif event_name == "stage_timeout" and stage:
            if stage in state.stages:
                state.stages[stage].status = StageStatus.TIMED_OUT
                state.stages[stage].finished_at = event.get("created_at")

        elif event_name in ("stage_cancelled", "workflow_cancelled"):
            state.status = "cancelled"
            if stage and stage in state.stages:
                state.stages[stage].status = StageStatus.CANCELLED

        elif event_name == "workflow_complete":
            state.status = "succeeded"

        elif event_name == "workflow_failed":
            state.status = "failed"

        elif event_name == "artifact" and stage:
            artifact_key = payload.get("artifact_key")
            if artifact_key:
                # Prefer full artifact_data (v3.1); fall back to artifact_summary
                data = payload.get("artifact_data") or payload.get("artifact_summary") or {}
                state.artifacts[artifact_key] = data

        elif event_name == "heartbeat" and stage:
            if stage in state.stages:
                state.stages[stage].heartbeat_at = payload.get("heartbeat_at")

        elif event_name == "stage_skipped" and stage:
            state.stages[stage] = StageCheckpoint(
                stage_name=stage,
                status=StageStatus.SKIPPED,
            )

    return state


def get_completed_stages(state: WorkflowState) -> set[str]:
    """Return the set of stage names that completed successfully."""
    return {
        name for name, cp in state.stages.items()
        if cp.status == StageStatus.COMPLETED
    }


def get_last_completed_stage(state: WorkflowState, stage_order: list[str]) -> Optional[str]:
    """Return the last stage in order that completed, or None."""
    completed = get_completed_stages(state)
    last = None
    for stage in stage_order:
        if stage in completed:
            last = stage
    return last


def is_safely_resumable(state: WorkflowState) -> bool:
    """Determine if a reconstructed workflow state is safe to resume.

    Conservative policy:
    - The workflow must not already be in a terminal state.
    - At least one stage must have completed (we have progress to skip).
    - No stage should be in a RUNNING state (which indicates an incomplete
      operation that we can't reliably pick up mid-stream).

    If all stages are PENDING, there's nothing to resume — just restart.
    """
    if state.status in ("succeeded", "failed", "cancelled"):
        return False

    completed = get_completed_stages(state)
    if not completed:
        return False

    # If any stage is stuck in RUNNING, it was interrupted and its output
    # is unreliable — mark it as needing restart, not resume.
    for cp in state.stages.values():
        if cp.status == StageStatus.RUNNING:
            return False

    return True


def get_resume_point(state: WorkflowState, stage_order: list[str]) -> Optional[str]:
    """Return the stage name to resume from (the first non-completed stage).

    Returns None if all stages are completed or if no safe resume point exists.
    """
    completed = get_completed_stages(state)
    skipped = {name for name, cp in state.stages.items() if cp.status == StageStatus.SKIPPED}
    done = completed | skipped

    for stage in stage_order:
        if stage not in done:
            return stage
    return None


def get_stage_artifacts(state: WorkflowState) -> dict[str, Any]:
    """Return all persisted stage artifacts from the reconstructed state.

    Keys are stage names (e.g. "researcher", "drafter"), values are the
    serialised AgentResult dicts that were persisted via persist_artifact().
    """
    return dict(state.artifacts)


# ═══════════════════════════════════════════════════════════════════════
#  Exceptions
# ═══════════════════════════════════════════════════════════════════════

class WorkflowCancelled(Exception):
    """Raised when a workflow is cancelled via DB flag."""
    def __init__(self, stage: str):
        self.stage = stage
        super().__init__(f"Workflow cancelled during {stage}")


class WorkflowStageTimeout(Exception):
    """Raised when a stage exceeds its timeout."""
    def __init__(self, stage: str, timeout: int):
        self.stage = stage
        self.timeout = timeout
        super().__init__(f"Stage {stage} timed out after {timeout}s")


class WorkflowStageFailed(Exception):
    """Raised when a stage fails after all retries."""
    def __init__(self, stage: str, cause: Exception):
        self.stage = stage
        self.cause = cause
        super().__init__(f"Stage {stage} failed: {cause}")


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _elapsed_ms(started_at: Optional[str]) -> int:
    """Compute elapsed milliseconds since started_at ISO string."""
    if not started_at:
        return 0
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, int((now - start).total_seconds() * 1000))
    except (ValueError, TypeError):
        return 0
