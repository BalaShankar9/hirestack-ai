"""
PipelineRuntime — single canonical execution path for all AI generation modes.

Eliminates the 3-way route fragmentation (sync / stream / job) by providing
one orchestration engine that emits events to pluggable sinks.

Usage:
    runtime = PipelineRuntime(config=RuntimeConfig(...), event_sink=SSESink())
    result = await runtime.execute(request_params)
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

logger = structlog.get_logger("hirestack.pipeline_runtime")

PHASE_SLO_MS: Dict[str, int] = {
    "recon": 8_000,
    "atlas": 12_000,
    "cipher": 10_000,
    "quill": 20_000,
    "forge": 15_000,
    "sentinel": 5_000,
    "nova": 2_000,
    "persist": 5_000,
}


# ═══════════════════════════════════════════════════════════════════════
#  Execution mode & configuration
# ═══════════════════════════════════════════════════════════════════════

class ExecutionMode(str, Enum):
    SYNC = "sync"
    STREAM = "stream"
    JOB = "job"
    WORKER = "worker"


@dataclass
class RuntimeConfig:
    """Controls execution behavior per mode."""
    mode: ExecutionMode = ExecutionMode.SYNC
    timeout: float = 300.0          # seconds
    user_id: str = ""
    job_id: str = ""                # only for JOB mode
    application_id: str = ""        # only for JOB mode
    requested_modules: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
#  Event system — pluggable sinks decouple orchestration from delivery
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PipelineEvent:
    """A single event emitted during pipeline execution."""
    event_type: str             # progress, agent_status, complete, error
    phase: str = ""             # atlas, cipher, quill, forge, sentinel, nova
    progress: int = 0           # 0-100
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    pipeline_name: str = ""     # for agent_status events
    stage: str = ""             # researcher, drafter, critic, etc.
    status: str = ""            # running, completed, failed
    latency_ms: int = 0


class EventSink(ABC):
    """Abstract interface for consuming pipeline events."""

    @abstractmethod
    async def emit(self, event: PipelineEvent) -> None:
        """Process a pipeline event."""

    async def close(self) -> None:
        """Cleanup when pipeline completes."""


class NullSink(EventSink):
    """No-op sink for synchronous execution — events are discarded."""

    async def emit(self, event: PipelineEvent) -> None:
        pass


class CollectorSink(EventSink):
    """Collects events in memory — useful for sync mode and testing."""

    def __init__(self) -> None:
        self.events: list[PipelineEvent] = []

    async def emit(self, event: PipelineEvent) -> None:
        self.events.append(event)


class SSESink(EventSink):
    """Formats events as SSE strings and pushes to an async queue."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def emit(self, event: PipelineEvent) -> None:
        if event.event_type == "agent_status":
            sse_data = {
                "pipeline_name": event.pipeline_name,
                "stage": event.stage,
                "status": event.status,
                "latency_ms": event.latency_ms,
                "message": event.message,
            }
            sse_str = f"event: agent_status\ndata: {json.dumps(sse_data)}\n\n"
        else:
            sse_data = {
                "phase": event.phase,
                "progress": event.progress,
                "message": event.message,
                **({"status": event.status} if event.status else {}),
                **event.data,
            }
            sse_str = f"event: {event.event_type}\ndata: {json.dumps(sse_data)}\n\n"
        await self.queue.put(sse_str)

    async def close(self) -> None:
        await self.queue.put(None)  # sentinel

    async def iter_events(self) -> AsyncGenerator[str, None]:
        """Yield SSE strings until close() sentinel."""
        while True:
            item = await self.queue.get()
            if item is None:
                break
            yield item


class DatabaseSink(EventSink):
    """Persists events to the generation_job_events table and keeps the
    generation_jobs row fully up-to-date so polling clients see real state."""

    # Phase → step index (1-based) for tracking completed_steps
    _PHASE_STEP: Dict[str, int] = {
        "recon": 1, "atlas": 2, "cipher": 3, "quill": 4,
        "forge": 5, "sentinel": 6, "nova": 7,
    }
    # Phase names that signal the *previous* phase is done
    _PHASE_ORDER = ["recon", "atlas", "cipher", "quill", "forge", "sentinel", "nova"]
    _TOTAL_STEPS = 7

    def __init__(
        self,
        db: Any,
        tables: Dict[str, str],
        job_id: str,
        user_id: str,
        application_id: str,
        requested_modules: Optional[List[str]] = None,
    ) -> None:
        self._db = db
        self._tables = tables
        self._job_id = job_id
        self._user_id = user_id
        self._application_id = application_id
        self._requested_modules = requested_modules or []
        self._sequence_no = 0
        self._last_module_progress = -1  # track to avoid redundant DB writes
        self._completed_steps = 0
        self._current_phase = ""
        self._last_job_snapshot: Dict[str, Any] = {}

    async def emit(self, event: PipelineEvent) -> None:
        self._sequence_no += 1
        payload = {
            "phase": event.phase,
            "progress": event.progress,
            "message": event.message,
            "status": event.status,
            **event.data,
        }
        # Persist event row
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_job_events"])
                .insert({
                    "job_id": self._job_id,
                    "user_id": self._user_id,
                    "application_id": self._application_id,
                    "sequence_no": self._sequence_no,
                    "event_name": event.event_type,
                    "payload": payload,
                })
                .execute()
            )
        except Exception as e:
            logger.warning("db_sink.event_persist_failed",
                           job_id=self._job_id, seq=self._sequence_no, error=str(e)[:200])

        # Update generation_jobs row with full state for polling clients
        if event.event_type == "progress" and event.progress is not None:
            phase = event.phase or ""
            agent_name = self._phase_to_agent(phase)

            # Track completed_steps: when we move to a new phase, the previous one is done
            if phase and phase != self._current_phase:
                new_idx = self._phase_index(phase)
                if new_idx > 0:
                    self._completed_steps = max(self._completed_steps, new_idx)
                self._current_phase = phase

            await self._update_job_full(
                progress=event.progress,
                status="running",
                phase=phase,
                message=event.message or "",
                current_agent=agent_name,
                completed_steps=self._completed_steps,
                total_steps=self._TOTAL_STEPS,
            )
            # Update module-level progress so frontend module cards show real %
            await self._update_module_progress(event.progress)

        elif event.event_type == "complete":
            await self._update_job_full(
                progress=100,
                status="running",
                phase="complete",
                message="All pipelines completed",
                current_agent="nova",
                completed_steps=self._TOTAL_STEPS,
                total_steps=self._TOTAL_STEPS,
            )

        elif event.event_type == "agent_status":
            agent_name = event.pipeline_name or event.stage or ""
            await self._update_job_partial(
                current_agent=agent_name,
                message=event.message or f"{agent_name} {event.status or 'updated'}",
            )

    def _phase_to_agent(self, phase: str) -> str:
        """Map a progress phase name to the agent persona name."""
        mapping = {
            "recon": "recon", "atlas": "atlas", "cipher": "cipher",
            "quill": "quill", "forge": "forge", "sentinel": "sentinel",
            "nova": "nova", "initializing": "recon",
        }
        return mapping.get(phase, phase or "pipeline")

    def _phase_index(self, phase: str) -> int:
        """Return 0-based index for a phase name, or -1 if unknown."""
        try:
            return self._PHASE_ORDER.index(phase)
        except ValueError:
            return -1

    async def _update_job_full(
        self,
        *,
        progress: int,
        status: str,
        phase: str,
        message: str,
        current_agent: str,
        completed_steps: int,
        total_steps: int,
    ) -> None:
        """Write all tracking fields to the generation_jobs row."""
        fields = {
            "progress": progress,
            "status": status,
            "phase": phase,
            "message": message,
            "current_agent": current_agent,
            "completed_steps": completed_steps,
            "total_steps": total_steps,
        }
        if all(self._last_job_snapshot.get(key) == value for key, value in fields.items()):
            return
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_jobs"])
                .update(fields)
                .eq("id", self._job_id)
                .execute()
            )
            self._last_job_snapshot.update(fields)
        except Exception as e:
            logger.warning("db_sink.job_update_failed", job_id=self._job_id, error=str(e)[:200])

    async def _update_job_partial(self, **fields: Any) -> None:
        """Update a subset of fields on the generation_jobs row."""
        if fields and all(self._last_job_snapshot.get(key) == value for key, value in fields.items()):
            return
        try:
            await asyncio.to_thread(
                lambda: self._db.table(self._tables["generation_jobs"])
                .update(fields)
                .eq("id", self._job_id)
                .execute()
            )
            self._last_job_snapshot.update(fields)
        except Exception as e:
            logger.warning("db_sink.job_partial_update_failed", job_id=self._job_id, error=str(e)[:200])

    async def update_job_progress(self, progress: int, status: str = "running") -> None:
        """Legacy helper — now delegates to _update_job_full with current state."""
        await self._update_job_full(
            progress=progress,
            status=status,
            phase=self._current_phase or "",
            message="",
            current_agent=self._phase_to_agent(self._current_phase or ""),
            completed_steps=self._completed_steps,
            total_steps=self._TOTAL_STEPS,
        )

    async def _update_module_progress(self, progress: int) -> None:
        """Push progress into applications.modules so module cards update in real-time."""
        if not self._requested_modules or not self._application_id:
            return
        # Throttle: only write when progress changes by ≥5%
        if abs(progress - self._last_module_progress) < 5:
            return
        self._last_module_progress = progress
        try:
            resp = await asyncio.to_thread(
                lambda: self._db.table(self._tables["applications"])
                .select("modules")
                .eq("id", self._application_id)
                .maybe_single()
                .execute()
            )
            modules = (resp.data or {}).get("modules") or {}
            timestamp = int(time.time() * 1000)
            for mod in self._requested_modules:
                cur = modules.get(mod) or {}
                if cur.get("state") in ("generating", "queued"):
                    modules[mod] = {**cur, "progress": progress, "updatedAt": timestamp}
            await asyncio.to_thread(
                lambda: self._db.table(self._tables["applications"])
                .update({"modules": modules})
                .eq("id", self._application_id)
                .execute()
            )
        except Exception as e:
            logger.warning("db_sink.module_progress_failed",
                           application_id=self._application_id, error=str(e)[:200])


# ═══════════════════════════════════════════════════════════════════════
#  Error classification (consolidated from generate.py)
# ═══════════════════════════════════════════════════════════════════════

def classify_ai_error(exc: Exception) -> Optional[Dict[str, Any]]:
    """Classify an AI provider exception into a structured response."""

    err = str(exc).lower()

    if any(k in err for k in (
        "api key not valid", "api_key_invalid",
        "api keys are not supported", "expected oauth2 access token",
        "credentials_missing",
    )):
        return {
            "code": 401,
            "message": (
                "Your Gemini credential isn't a valid API key. "
                "Create a Google AI Studio API key and set GEMINI_API_KEY."
            ),
        }
    if "permission denied" in err or "permission_denied" in err:
        return {"code": 403, "message": "Gemini API permission denied. Check your API key and project settings."}
    if "not found" in err and ("model" in err or "404" in err):
        return {"code": 404, "message": "The AI model was not found. Check your GEMINI_MODEL setting."}
    if "resource exhausted" in err or "rate limit" in err or "429" in err:
        retry_after = _extract_retry_after(str(exc))
        return {
            "code": 429,
            "message": "AI rate limit reached. Please wait a moment and try again.",
            "retry_after_seconds": retry_after,
        }
    return None


def _extract_retry_after(err: str) -> Optional[int]:
    """Parse provider retry hints into whole seconds."""
    import math
    import re

    m = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", err, flags=re.IGNORECASE)
    if m:
        try:
            return max(1, int(math.ceil(float(m.group(1)))))
        except Exception:
            pass
    m = re.search(r"retryDelay'\s*:\s*'(\d+)s'", err)
    if m:
        try:
            return max(1, int(m.group(1)))
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Runtime — core execution engine
# ═══════════════════════════════════════════════════════════════════════

class PipelineRuntime:
    """
    Canonical execution engine for the full AI generation pipeline.

    Phases:
      1. Recon — Company intelligence gathering
      2. Atlas — Resume parsing + benchmark building
      3. Cipher — Gap analysis
      4. Quill — CV + Cover letter + Roadmap (parallel)
      5. Forge — Personal statement + Portfolio (parallel)
      6. Sentinel — Validation
      7. Nova — Format final response

    All phases emit events through the configured EventSink, making the
    execution path identical regardless of sync/stream/job mode.
    """

    def __init__(
        self,
        config: RuntimeConfig,
        event_sink: Optional[EventSink] = None,
    ) -> None:
        self.config = config
        self.sink = event_sink or NullSink()
        self._cancelled = False
        self._failed_modules: List[Dict[str, str]] = []
        self._phase_started_at: Dict[str, float] = {}
        self._phase_latencies: Dict[str, int] = {}
        # Recon overlap state — populated when intel kicks off.
        self._intel_task: Optional[asyncio.Task] = None
        self._intel_started_at: Optional[float] = None
        self._intel_resolved: bool = False
        # Per-doc deterministic quality breakdowns (W2). Populated by
        # the Sentinel phase via app.services.quality_scorer.
        self._per_doc_quality: Dict[str, Dict[str, Any]] = {}

    async def _await_company_intel(
        self,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Block until the recon intel task resolves (or times out).

        Idempotent — once resolved, subsequent callers get the cached
        result without re-awaiting. On timeout, emits a warning event,
        cancels the underlying task cleanly, and returns an empty dict
        so the pipeline can continue with JD-only context.
        """
        if self._intel_resolved:
            return getattr(self, "_company_intel_cached", {}) or {}

        task = self._intel_task
        if task is None:
            self._intel_resolved = True
            self._company_intel_cached = {}
            return {}

        # Compute remaining budget: total intel budget is `timeout`
        # measured from intel kickoff, not from this call site, so a
        # later consumer cannot extend the deadline.
        if self._intel_started_at is not None:
            elapsed = time.perf_counter() - self._intel_started_at
            remaining = max(0.5, timeout - elapsed)
        else:
            remaining = timeout

        company_intel: Dict[str, Any] = {}
        try:
            company_intel = await asyncio.wait_for(
                asyncio.shield(task), timeout=remaining,
            )
            logger.info(
                "pipeline_runtime.intel_done",
                confidence=(company_intel or {}).get("confidence", "unknown"),
                overlap_savings_ms=(
                    int((time.perf_counter() - self._intel_started_at) * 1000)
                    if self._intel_started_at else 0
                ),
            )
        except asyncio.TimeoutError:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            logger.warning("pipeline_runtime.intel_timeout")
            await self.sink.emit(PipelineEvent(
                event_type="detail",
                phase="recon",
                message="Recon timed out; continuing with JD-based intel.",
                status="warning",
                data={"agent": "recon", "source": "analysis"},
            ))
            self._failed_modules.append(
                {"module": "company_intel", "error": "intel_timeout"}
            )
        except Exception as intel_err:
            logger.warning("pipeline_runtime.intel_skipped",
                           error=str(intel_err)[:200])
            await self.sink.emit(PipelineEvent(
                event_type="detail",
                phase="recon",
                message="Recon failed; continuing with available inputs.",
                status="warning",
                data={
                    "agent": "recon", "source": "analysis",
                    "metadata": {"error": str(intel_err)[:200]},
                },
            ))
            self._failed_modules.append(
                {"module": "company_intel", "error": str(intel_err)[:200]}
            )
        finally:
            self._intel_resolved = True
            self._company_intel_cached = company_intel or {}
            # Close out the recon phase here so its measured latency
            # reflects intel-resolution time (matches what jobs.py + the
            # progress UI display).
            try:
                self._finish_phase("recon")
            except Exception:
                pass

        return company_intel or {}

    def _begin_phase(self, phase: str) -> None:
        self._phase_started_at[phase] = time.perf_counter()

    def _finish_phase(self, phase: str, *, success: bool = True, error_class: str = "") -> int:
        started_at = self._phase_started_at.pop(phase, None)
        if started_at is None:
            return self._phase_latencies.get(phase, 0)

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        self._phase_latencies[phase] = duration_ms

        try:
            from app.core.metrics import MetricsCollector, StageMetric

            finished_at = time.time()
            stage_metric = StageMetric(
                pipeline_name=f"runtime_{self.config.mode.value}",
                stage_name=phase,
                started_at=finished_at - (duration_ms / 1000),
                finished_at=finished_at,
                success=success,
                error_class=error_class,
            )
            MetricsCollector.get().record_stage(stage_metric)
        except Exception as metric_err:
            logger.warning("pipeline_runtime.phase_metric_failed", phase=phase, error=str(metric_err)[:200])

        threshold_ms = PHASE_SLO_MS.get(phase)
        if threshold_ms and duration_ms > threshold_ms:
            logger.warning(
                "pipeline_runtime.phase_slow",
                phase=phase,
                duration_ms=duration_ms,
                threshold_ms=threshold_ms,
                mode=self.config.mode.value,
                job_id=self.config.job_id or None,
            )

        return duration_ms

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run the full pipeline and return the formatted response dict."""
        start = time.perf_counter()

        job_title = params.get("job_title", "")
        company = params.get("company", "") or "the company"
        jd_text = params.get("jd_text", "")
        resume_text = params.get("resume_text", "")
        user_id = self.config.user_id

        logger.info("pipeline_runtime.start",
                     mode=self.config.mode.value, job_title=job_title,
                     company=company, user_id=user_id)

        metrics = None
        pipeline_metric = None
        try:
            from app.core.metrics import MetricsCollector, PipelineRunMetric

            metrics = MetricsCollector.get()
            metrics.job_started()
            pipeline_metric = PipelineRunMetric(
                pipeline_name=f"runtime_{self.config.mode.value}",
                user_id=user_id,
                mode=self.config.mode.value,
                started_at=time.time(),
            )
        except Exception as metric_err:
            logger.warning("pipeline_runtime.metrics_unavailable", error=str(metric_err)[:200])

        try:
            from ai_engine.client import AIClient
            from app.core.database import get_supabase, TABLES

            ai = AIClient()
            sb = get_supabase()
            use_agents = self._agents_available()

            if use_agents:
                result = await self._run_agent_pipeline(
                    ai=ai, sb=sb, tables=TABLES,
                    job_title=job_title, company=company,
                    jd_text=jd_text, resume_text=resume_text,
                    user_id=user_id,
                )
            else:
                result = await self._run_legacy_pipeline(
                    ai=ai,
                    job_title=job_title, company=company,
                    jd_text=jd_text, resume_text=resume_text,
                )

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.info("pipeline_runtime.complete",
                         mode=self.config.mode.value, elapsed_ms=elapsed_ms,
                         score=result.get("scores", {}).get("overall", 0))

            # ── Pipeline Telemetry — persist runtime-level cost + token summary ─
            try:
                if user_id:
                    from app.services.career_analytics import PipelineTelemetryService
                    tel = PipelineTelemetryService()
                    tu = ai.token_usage
                    await tel.record_telemetry(
                        user_id=user_id,
                        job_id=self.config.job_id or "runtime",
                        pipeline_name=f"runtime_{self.config.mode.value}",
                        model_used=getattr(ai, "model", ""),
                        total_latency_ms=elapsed_ms,
                        stage_latencies=self._phase_latencies.copy(),
                        token_usage={
                            "prompt_tokens": tu.get("prompt_tokens", 0),
                            "completion_tokens": tu.get("completion_tokens", 0),
                            "total_tokens": tu.get("total_tokens", 0),
                            "call_count": tu.get("call_count", 0),
                        },
                        quality_scores=result.get("scores") or {},
                        evidence_stats=((result.get("meta") or {}).get("evidence_summary") or {}),
                        cost_usd_cents=tu.get("estimated_cost_usd_cents", 0),
                        pipeline_config={
                            "requested_modules": self.config.requested_modules,
                            "mode": self.config.mode.value,
                        },
                    )
            except Exception as tel_err:
                logger.warning("pipeline_runtime.telemetry_failed", error=str(tel_err)[:200])

            # ── Usage-guard counter: increment per-user + platform daily totals ─
            try:
                if user_id:
                    from app.services.usage_guard import record_generation
                    await record_generation(
                        user_id,
                        cost_cents=int(ai.token_usage.get("estimated_cost_usd_cents", 0) or 0),
                        token_total=int(ai.token_usage.get("total_tokens", 0) or 0),
                    )
            except Exception as ug_err:
                logger.warning("pipeline_runtime.usage_guard_record_failed", error=str(ug_err)[:200])

            if pipeline_metric is not None:
                pipeline_metric.finished_at = time.time()
                pipeline_metric.success = True
                pipeline_metric.total_tokens_input = ai.token_usage.get("prompt_tokens", 0)
                pipeline_metric.total_tokens_output = ai.token_usage.get("completion_tokens", 0)
                pipeline_metric.stages = []
                if metrics is not None:
                    metrics.record_run(pipeline_metric)

            await self.sink.emit(PipelineEvent(
                event_type="complete", phase="nova", progress=100,
                message="All pipelines completed",
                data={"result": result},
            ))

            if self._failed_modules:
                result["failedModules"] = self._failed_modules

            return result

        except Exception as e:
            if pipeline_metric is not None:
                pipeline_metric.finished_at = time.time()
                pipeline_metric.success = False
                pipeline_metric.error_class = e.__class__.__name__
                if metrics is not None:
                    metrics.record_run(pipeline_metric)
            classified = classify_ai_error(e)
            if classified:
                await self.sink.emit(PipelineEvent(
                    event_type="error", message=str(classified["message"]),
                    data={"code": classified["code"],
                          "retryAfterSeconds": classified.get("retry_after_seconds")},
                ))
                raise
            else:
                logger.error("pipeline_runtime.error",
                             error=str(e), traceback=traceback.format_exc())
                await self.sink.emit(PipelineEvent(
                    event_type="error",
                    message="AI generation failed due to an unexpected error.",
                    data={"code": 500},
                ))
                raise
        finally:
            if metrics is not None:
                metrics.job_finished()
            await self.sink.close()

    # ── Agent pipeline path ───────────────────────────────────────────

    async def _run_agent_pipeline(
        self,
        ai: Any,
        sb: Any,
        tables: Dict[str, str],
        job_title: str,
        company: str,
        jd_text: str,
        resume_text: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Full agent-powered pipeline execution with catalog-driven document planning."""
        from ai_engine.agents.pipelines import (
            resume_parse_pipeline,
            benchmark_pipeline,
            gap_analysis_pipeline,
            cv_generation_pipeline,
            cover_letter_pipeline,
            personal_statement_pipeline,
            portfolio_pipeline,
        )
        from ai_engine.agents.orchestrator import PipelineResult
        from ai_engine.chains.career_consultant import CareerConsultantChain
        from ai_engine.chains.adaptive_document import AdaptiveDocumentChain

        # Pipeline registry: doc_key → factory function (for dedicated pipelines)
        _PIPELINE_REGISTRY = {
            "cv": cv_generation_pipeline,
            "cover_letter": cover_letter_pipeline,
            "personal_statement": personal_statement_pipeline,
            "portfolio": portfolio_pipeline,
        }

        async def stage_callback(event: dict) -> None:
            """Emit agent_status events directly so the frontend sees
            real-time sub-agent progress instead of batched updates."""
            pe = PipelineEvent(
                event_type="agent_status",
                pipeline_name=event.get("pipeline_name", ""),
                stage=event.get("stage", ""),
                status=event.get("status", ""),
                latency_ms=event.get("latency_ms", 0),
                message=event.get("message", ""),
            )
            await self.sink.emit(pe)

        # ── v4 orchestration: BuildPlan + ArtifactStore + EventBusBridge ─
        # Wires the new typed orchestration foundation in beside the existing
        # 7-phase execution path. Failures here never abort the pipeline —
        # the legacy path is still authoritative this round; the v4 layer
        # adds a typed BuildPlan artifact + Critic gates + truthful progress
        # + a bridge that forwards typed OrchestrationEvents onto the same
        # PipelineEvent sink so any future agent emits land in SSE/DB.
        build_plan = None
        artifact_store = None
        progress_calc = None
        orchestration_bus = None
        orchestration_bridge = None
        try:
            from ai_engine.agents.build_planner import BuildPlanner
            from ai_engine.agents.orchestration import InMemoryEventBus
            from app.services.artifact_store import ArtifactStore as _ArtifactStore
            from app.services.event_bus_bridge import EventBusBridge
            from app.services.progress_calculator import ProgressCalculator

            orchestration_bus = InMemoryEventBus()
            orchestration_bridge = EventBusBridge(orchestration_bus, self.sink)
            artifact_store = _ArtifactStore(sb, tables)
            build_plan = BuildPlanner().plan(
                application_id=self.config.application_id or None,
                job_title=job_title,
                company=company,
                requested_modules=self.config.requested_modules,
            )
            progress_calc = ProgressCalculator(plan=build_plan)
            # Persist the plan for replay / Mission Control.
            await artifact_store.put(
                build_plan,
                user_id=user_id,
                agent_name="build_planner",
                artifact_type="BuildPlan",
            )
            await self.sink.emit(PipelineEvent(
                event_type="plan_created",
                phase="recon",
                progress=1,
                message="Build plan created.",
                data={
                    "stage_count": len(build_plan.stages),
                    "stage_ids": [s.stage_id for s in build_plan.stages],
                    "modules": build_plan.requested_modules,
                },
            ))
            # Also publish through the typed bus so the bridge round-trips
            # and we have at least one verified end-to-end forward in prod.
            try:
                from ai_engine.agents.orchestration import (
                    EventLevel as _EL,
                    OrchestrationEvent as _OE,
                )
                await orchestration_bus.publish(_OE(
                    event_name="orchestration.plan_created",
                    application_id=self.config.application_id or None,
                    agent_name="build_planner",
                    level=_EL.INFO,
                    message="Build plan created.",
                    data={
                        "phase": "recon",
                        "progress": 1,
                        "stage_count": len(build_plan.stages),
                        "stage_ids": [s.stage_id for s in build_plan.stages],
                        "modules": build_plan.requested_modules,
                    },
                ))
            except Exception:
                pass
        except Exception as plan_err:
            logger.warning("pipeline_runtime.build_plan_skipped",
                           error=str(plan_err)[:200])
        # Stash on self so the rest of the pipeline (and tests) can reach it.
        self._build_plan = build_plan
        self._artifact_store = artifact_store
        self._progress_calc = progress_calc
        self._orchestration_bus = orchestration_bus
        self._orchestration_bridge = orchestration_bridge

        # Per-stage critic summaries (best-effort).
        sentinel_validation: Optional[Dict[str, Any]] = None

        # ── Phase 0: Company Intelligence (best-effort, parallel-ready) ─
        self._begin_phase("recon")
        if progress_calc is not None:
            try:
                progress_calc.mark_started("recon.intel")
            except Exception:
                pass
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="recon", progress=3,
            message="Gathering company intelligence…",
        ))

        company_intel: dict = {}
        recon_sources_completed: set[str] = set()

        async def _on_recon_event(event: dict) -> None:
            """Forward Recon source-level updates to sinks for live timeline logs.

            This keeps the UI moving during intel gathering instead of appearing
            stalled at the initial recon progress value.
            """
            source = str(event.get("source") or "recon")
            status = str(event.get("status") or "info")
            message = str(event.get("message") or "Recon update")
            url = event.get("url") if isinstance(event.get("url"), str) else None
            metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else None

            await self.sink.emit(
                PipelineEvent(
                    event_type="detail",
                    phase="recon",
                    message=message,
                    status=status,
                    data={
                        "agent": "recon",
                        "source": source,
                        **({"url": url} if url else {}),
                        **({"metadata": metadata} if metadata else {}),
                    },
                )
            )

            # Advance recon progress in small steps as sources complete so
            # the user sees sequential movement similar to the landing flow.
            if status in {"completed", "warning", "failed"} and source not in recon_sources_completed:
                recon_sources_completed.add(source)
                recon_progress = min(7, 3 + len(recon_sources_completed))
                await self.sink.emit(
                    PipelineEvent(
                        event_type="progress",
                        phase="recon",
                        progress=recon_progress,
                        message=f"Recon: processed {len(recon_sources_completed)} source(s)…",
                    )
                )
        # ── Recon overlap optimization ────────────────────────────────
        # Launch company intel as a background task and let Atlas (resume
        # parse + benchmark) start immediately. company_intel is only
        # consumed at the document-pack-plan step (~15-20s into Atlas),
        # so this overlaps the entire Atlas duration with intel gathering.
        # First-time consumers self.await_company_intel() with a strict
        # timeout. Net p95 saving: ~15-25s on cold runs.
        intel_task: Optional[asyncio.Task] = None
        try:
            from ai_engine.chains.company_intel import CompanyIntelChain
            intel_chain = CompanyIntelChain(ai)
            intel_task = asyncio.create_task(
                intel_chain.gather_intel(
                    company=company,
                    job_title=job_title,
                    jd_text=jd_text,
                    on_event=_on_recon_event,
                ),
                name="recon.company_intel",
            )
            # Stash on self so any consumer in this run can await it.
            self._intel_task = intel_task
            self._intel_started_at = time.perf_counter()
        except Exception as intel_setup_err:
            logger.warning("pipeline_runtime.intel_setup_failed",
                           error=str(intel_setup_err)[:200])
            self._failed_modules.append(
                {"module": "company_intel", "error": str(intel_setup_err)[:200]}
            )
            self._finish_phase("recon")
            self._intel_task = None
            self._intel_started_at = None
        else:
            # Recon is now "in flight" — phase will be finalised when the
            # first downstream consumer awaits company_intel. Keep the
            # phase counter "open" by skipping _finish_phase here; it's
            # called from _await_company_intel() instead.
            await self.sink.emit(PipelineEvent(
                event_type="detail",
                phase="recon",
                message="Recon launched; running in parallel with Atlas…",
                status="running",
                data={"agent": "recon", "source": "analysis"},
            ))

        # ── Phase 1: Resume parse ─────────────────────────────────────
        self._begin_phase("atlas")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=8,
            message="Agent: parsing resume…",
        ))

        # ── Seed planned document library rows so the UI shows all 6 ─
        # benchmark slots immediately as "planned", flipping to "ready"
        # or "error" as each generation completes. Best-effort — never
        # fatal: a failure here just means the UI catches up at persist.
        application_id = self.config.application_id
        if application_id and "document_library" in tables:
            try:
                from app.services.document_library import DocumentLibraryService as _DLS
                _seed_service = _DLS(sb, tables)
                # Only seed if no benchmark rows exist yet for this app — re-runs
                # of the same application should reuse existing planned rows.
                _existing = await _seed_service.get_application_documents(user_id, application_id)
                _has_bench = bool(_existing.get("benchmark"))
                _has_tailored = bool(_existing.get("tailored"))
                if not _has_bench:
                    await _seed_service.create_benchmark_library(user_id, application_id)
                    logger.info("pipeline_runtime.benchmark_planned_seeded", application_id=application_id)
                if not _has_tailored:
                    # Seed canonical tailored slots up-front (CV, Resume, Cover
                    # Letter, Personal Statement, Portfolio). Planner-driven
                    # extras land later via persist's upsert.
                    await _seed_service.create_tailored_documents_from_plan(
                        user_id, application_id,
                        [
                            {"key": "cv", "label": "Tailored CV"},
                            {"key": "resume", "label": "Tailored Résumé"},
                            {"key": "cover_letter", "label": "Tailored Cover Letter"},
                            {"key": "personal_statement", "label": "Tailored Personal Statement"},
                            {"key": "portfolio", "label": "Tailored Portfolio"},
                        ],
                    )
                    logger.info("pipeline_runtime.tailored_planned_seeded", application_id=application_id)
            except Exception as seed_err:
                logger.warning("pipeline_runtime.seed_planned_rows_failed", error=str(seed_err)[:200])

        user_profile: dict = {}
        if resume_text.strip():
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="atlas",
                message="Extracting sections, skills, and experience from resume…",
                status="running",
                data={"agent": "atlas", "source": "resume_parse"},
            ))
            try:
                pipe = resume_parse_pipeline(
                    ai_client=ai, on_stage_update=stage_callback,
                    db=sb, tables=tables, user_id=user_id,
                )
                parse_result: PipelineResult = await pipe.execute({"user_id": user_id, "resume_text": resume_text})
                user_profile = parse_result.content if isinstance(parse_result.content, dict) else {}
                await self.sink.emit(PipelineEvent(
                    event_type="detail", phase="atlas",
                    message="Resume parsed — extracted skills, experience & education ✓",
                    status="completed",
                    data={"agent": "atlas", "source": "resume_parse"},
                ))
            except Exception as rp_err:
                logger.warning("pipeline_runtime.resume_parse_failed", error=str(rp_err)[:200])
                self._failed_modules.append({"module": "resume_parse", "error": str(rp_err)[:200]})
                await self.sink.emit(PipelineEvent(
                    event_type="detail", phase="atlas",
                    message="Resume parse encountered an issue; continuing with available data",
                    status="warning",
                    data={"agent": "atlas", "source": "resume_parse"},
                ))
        else:
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="atlas",
                message="No resume provided — building profile from job context",
                status="info",
                data={"agent": "atlas", "source": "resume_parse"},
            ))

        # ── Phase 1b: Benchmark ───────────────────────────────────────
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=15,
            message="Agent: building candidate benchmark…",
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="atlas",
            message="Analyzing ideal candidate profile against job requirements…",
            status="running",
            data={"agent": "atlas", "source": "benchmark"},
        ))

        bench_result = None
        benchmark_data: dict = {}
        try:
            bench_pipe = benchmark_pipeline(
                ai_client=ai, on_stage_update=stage_callback,
                db=sb, tables=tables, user_id=user_id,
            )
            bench_result = await bench_pipe.execute({
                "user_id": user_id,
                "job_title": job_title,
                "company": company,
                "jd_text": jd_text,
                "user_profile": user_profile,
            })
            benchmark_data = bench_result.content if isinstance(bench_result.content, dict) else {}
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="atlas",
                message="Benchmark built — ideal skills, scores & comparisons ready ✓",
                status="completed",
                data={"agent": "atlas", "source": "benchmark"},
            ))
        except Exception as bench_err:
            logger.warning("pipeline_runtime.benchmark_failed", error=str(bench_err)[:200])
            self._failed_modules.append({"module": "benchmark", "error": str(bench_err)[:200]})
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="atlas",
                message="Benchmark generation encountered an issue; using fallback scoring",
                status="warning",
                data={"agent": "atlas", "source": "benchmark"},
            ))

        ideal_skills = benchmark_data.get("ideal_skills", [])
        keywords = [s.get("name", "") for s in ideal_skills if isinstance(s, dict) and s.get("name")]
        if not keywords:
            keywords = self._extract_keywords_from_jd(jd_text)

        n_skills = len(keywords)
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="atlas",
            message=f"Mapped {n_skills} target skill{'s' if n_skills != 1 else ''} from job requirements ✓",
            status="completed",
            data={"agent": "atlas", "source": "skill_mapping"},
        ))

        # Start independent benchmark artifacts early so they overlap with gap analysis.
        # Both CV (long-form) and Resume (1-2 page) are first-class benchmark documents.
        benchmark_cv_html = ""
        benchmark_resume_html = ""
        resume_html = ""  # tailored resume — defined here to avoid late-stage NameError in Nova
        benchmark_cv_task: Optional[asyncio.Task[str]] = None
        benchmark_resume_task: Optional[asyncio.Task[str]] = None
        doc_pack_plan_task: Optional[asyncio.Task[Any]] = None

        try:
            from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
            bc = BenchmarkBuilderChain(ai)
            benchmark_cv_task = asyncio.create_task(
                bc.create_benchmark_cv_html(
                    user_profile=user_profile, benchmark_data=benchmark_data,
                    job_title=job_title, company=company, jd_text=jd_text,
                )
            )
            # Resume = US-style 1–2 page achievement-focused, generated alongside CV.
            benchmark_resume_task = asyncio.create_task(
                bc.create_resume_html(
                    user_profile=user_profile, benchmark_data=benchmark_data,
                    job_title=job_title, company=company, jd_text=jd_text,
                )
            )
        except Exception as bcv_err:
            logger.warning("pipeline_runtime.benchmark_cv_task_failed", error=str(bcv_err)[:200])

        # First real consumer of company_intel — block here so that
        # downstream document planning has the recon context. Atlas
        # work above ran fully overlapped with intel. _await_company_intel
        # never raises (timeout/errors return {} and emit warnings).
        company_intel = await self._await_company_intel(timeout=30.0)

        try:
            from app.services.document_catalog import discover_and_observe

            doc_pack_plan_task = asyncio.create_task(
                discover_and_observe(
                    db=sb, tables=tables, ai_client=ai,
                    jd_text=jd_text, job_title=job_title,
                    company=company, user_profile=user_profile,
                    user_id=user_id,
                    company_intel=company_intel,
                )
            )
        except Exception as doc_task_err:
            logger.warning("pipeline_runtime.doc_pack_plan_task_failed", error=str(doc_task_err)[:200])

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=25,
            message="Resume parsed & benchmark built ✓",
        ))
        # Per-stage critic gate (soft-fail): benchmark artifact validation.
        try:
            atlas_artifact = self._build_benchmark_profile_artifact(
                job_title=job_title,
                company=company,
                benchmark_data=benchmark_data,
            )
            await self._run_critic_gate(
                phase="atlas",
                artifact=atlas_artifact,
                review="benchmark",
                user_id=user_id,
                progress_pass=24,
                progress_fail=20,
                message_pass="Benchmark critic gate passed.",
                message_fail="Benchmark critic gate found issues; continuing.",
            )
        except Exception as atlas_gate_err:
            logger.warning("pipeline_runtime.atlas_gate_failed", error=str(atlas_gate_err)[:200])

        # Emit explicit pipeline-done markers so frontend deliverable chips
        # transition to "done" even if individual stage events arrived out-of-order.
        for pn in ("resume_parse", "benchmark"):
            await self.sink.emit(PipelineEvent(
                event_type="agent_status",
                pipeline_name=pn, stage="pipeline_done", status="completed",
                message=f"{pn} complete",
            ))
        self._finish_phase("atlas")

        # ── Phase 2: Gap analysis ─────────────────────────────────────
        self._begin_phase("cipher")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=30,
            message="Agent: analyzing skill gaps…",
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="cipher",
            message="Comparing your skills against job requirements…",
            status="running",
            data={"agent": "cipher", "source": "gap_detection"},
        ))

        gap_result = None
        gap_analysis: dict = {}
        try:
            gap_pipe = gap_analysis_pipeline(
                ai_client=ai, on_stage_update=stage_callback,
                db=sb, tables=tables, user_id=user_id,
            )
            gap_result = await gap_pipe.execute({
                "user_id": user_id,
                "user_profile": user_profile,
                "benchmark": benchmark_data,
                "job_title": job_title,
                "company": company,
            })
            gap_analysis = gap_result.content if isinstance(gap_result.content, dict) else {}
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="cipher",
                message="Skill gaps identified & ranked by importance ✓",
                status="completed",
                data={"agent": "cipher", "source": "gap_detection"},
            ))
        except Exception as gap_err:
            logger.warning("pipeline_runtime.gap_analysis_failed", error=str(gap_err)[:200])
            self._failed_modules.append({"module": "gap_analysis", "error": str(gap_err)[:200]})
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="cipher",
                message="Gap analysis encountered an issue; using available data",
                status="warning",
                data={"agent": "cipher", "source": "gap_detection"},
            ))

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=45,
            message="Gap analysis complete ✓",
        ))

        # ── Evidence graph canonicalization + plan artifact ───────────
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="cipher",
            message="Building evidence graph & scoring skill matches…",
            status="running",
            data={"agent": "cipher", "source": "skill_matching"},
        ))
        evidence_score = 0
        plan_artifact = None
        try:
            from ai_engine.agents.evidence_graph import EvidenceGraphBuilder
            from ai_engine.agents.evidence import EvidenceLedger
            from ai_engine.agents.planner import PlannerAgent, PipelinePlan, PipelineStep

            graph_builder = EvidenceGraphBuilder(db=sb, user_id=user_id)
            for result in (bench_result, gap_result):
                ledger_raw = getattr(result, "evidence_ledger", None)
                if ledger_raw:
                    # PipelineResult.evidence_ledger is a serialised dict;
                    # canonicalize() expects an EvidenceLedger instance.
                    if isinstance(ledger_raw, dict):
                        ledger_raw = EvidenceLedger.from_dict(ledger_raw)
                    graph_builder.canonicalize(ledger_raw)

            evidence_score = graph_builder.compute_evidence_strength_score()

            planner = PlannerAgent(ai_client=ai)
            plan = PipelinePlan(
                steps=[
                    PipelineStep(pipeline_name="resume_parse", reason="initial"),
                    PipelineStep(pipeline_name="benchmark", reason="scoring"),
                    PipelineStep(pipeline_name="gap_analysis", reason="gaps"),
                    PipelineStep(pipeline_name="cv_generation", reason="doc"),
                    PipelineStep(pipeline_name="cover_letter", reason="doc"),
                ],
                reasoning="standard_full_pipeline",
            )
            plan_artifact = planner.build_plan_artifact(
                plan=plan, jd_text=jd_text,
                user_profile=user_profile, evidence_score=evidence_score,
            )
            logger.info(
                "pipeline_runtime.plan_artifact",
                risk_mode=plan_artifact.risk_mode,
                jd_score=plan_artifact.jd_quality_score,
                profile_score=plan_artifact.profile_quality_score,
                evidence_score=evidence_score,
            )
        except Exception as eg_err:
            logger.warning("pipeline_runtime.evidence_graph_skipped", error=str(eg_err)[:200])

        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="cipher",
            message=f"Evidence strength score: {evidence_score} — skill matching complete ✓",
            status="completed",
            data={"agent": "cipher", "source": "skill_matching"},
        ))

        # ── Phase 2b: Document Pack Planning ──────────────────────────
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=48,
            message="Planning optimal document pack…",
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="cipher",
            message="Ranking document priorities & planning strategy…",
            status="running",
            data={"agent": "cipher", "source": "priority_ranking"},
        ))

        doc_pack_plan = None
        discovered_documents: list = []
        try:
            if doc_pack_plan_task is not None:
                doc_pack_plan = await doc_pack_plan_task

            if doc_pack_plan:
                discovered_documents = (
                    doc_pack_plan.core
                    + doc_pack_plan.required
                    + doc_pack_plan.optional
                    + doc_pack_plan.new_candidates
                )
                logger.info(
                    "pipeline_runtime.doc_pack_planned",
                    core=len(doc_pack_plan.core),
                    required=len(doc_pack_plan.required),
                    optional=len(doc_pack_plan.optional),
                )
        except Exception as dpp_err:
            logger.warning("pipeline_runtime.doc_pack_plan_skipped", error=str(dpp_err)[:200])
            self._failed_modules.append({"module": "doc_pack_planner", "error": str(dpp_err)[:200]})

        if benchmark_cv_task is not None:
            try:
                benchmark_cv_html = await benchmark_cv_task
            except Exception as bcv_err:
                logger.warning("pipeline_runtime.benchmark_cv_failed", error=str(bcv_err)[:200])

        if benchmark_resume_task is not None:
            try:
                benchmark_resume_html = await benchmark_resume_task
            except Exception as br_err:
                logger.warning("pipeline_runtime.benchmark_resume_failed", error=str(br_err)[:200])

        # ── Generate benchmark core document set (canonical 6) ────────
        # The canonical Benchmark base set is: CV, Resume, Cover Letter,
        # Personal Statement, Portfolio, Learning Plan.
        # CV + Resume are already running in parallel above (benchmark_cv_task /
        # benchmark_resume_task). Here we generate the remaining 4 with per-doc
        # isolation: each gets its own try/except so one failure cannot collapse
        # the whole benchmark foundation. Learning Plan is sourced from Quill's
        # roadmap result later — we record a placeholder here so the UI shows
        # all 6 prefixed slots from the start.
        benchmark_documents: Dict[str, str] = {}
        # cover_letter, personal_statement, portfolio generated here.
        # learning_plan is filled later when roadmap completes.
        BENCHMARK_REMAINING_TYPES = [
            ("cover_letter", "Cover Letter"),
            ("personal_statement", "Personal Statement"),
            ("portfolio", "Portfolio"),
        ]
        try:
            from ai_engine.chains.adaptive_document import AdaptiveDocumentChain
            bench_adaptive = AdaptiveDocumentChain(ai)
            intel_summary = ""
            if company_intel and isinstance(company_intel, dict):
                intel_summary = company_intel.get("summary", "")

            bench_context = {
                "job_title": job_title,
                "company": company,
                "jd_text": jd_text,
                "user_profile": user_profile,
                "benchmark_data": benchmark_data,
                "gap_analysis": gap_analysis,
                "strengths_summary": ", ".join(
                    s.get("area", "") for s in gap_analysis.get("strengths", [])[:8]
                    if isinstance(s, dict)
                ) or "None identified",
                "benchmark_keywords": ", ".join(keywords[:15]),
                "company_intel": intel_summary,
            }

            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="cipher",
                message="Generating benchmark document foundation (canonical 6 docs)…",
                status="running",
                data={"agent": "cipher", "source": "benchmark_core_docs"},
            ))

            # Per-doc isolation: each generation runs with its own try/except +
            # one bounded retry. Failures are recorded but never block other docs.
            async def _gen_with_retry(doc_key: str, doc_label: str) -> Optional[str]:
                for attempt in (1, 2):
                    try:
                        result = await bench_adaptive.generate(
                            doc_type=doc_key,
                            doc_label=doc_label,
                            context=bench_context,
                            mode="benchmark",
                        )
                        if isinstance(result, str) and result.strip():
                            return result
                    except Exception as ex:
                        logger.warning(
                            f"pipeline_runtime.benchmark_core_{doc_key}_attempt_{attempt}_failed",
                            error=str(ex)[:200],
                        )
                        if attempt == 1:
                            await asyncio.sleep(1.5)
                            continue
                self._failed_modules.append({"module": f"benchmark_{doc_key}", "error": "generation_failed_after_retry"})
                return None

            # Run remaining 3 in parallel — isolated, so one failure cannot
            # take down the others.
            bench_tasks = [
                _gen_with_retry(key, label) for key, label in BENCHMARK_REMAINING_TYPES
            ]
            bench_results = await asyncio.gather(*bench_tasks, return_exceptions=True)
            for (key, _label), result in zip(BENCHMARK_REMAINING_TYPES, bench_results):
                if isinstance(result, Exception):
                    logger.warning(
                        f"pipeline_runtime.benchmark_core_{key}_unexpected",
                        error=str(result)[:200],
                    )
                elif isinstance(result, str) and result.strip():
                    benchmark_documents[key] = result

            ready_count = (
                len(benchmark_documents)
                + (1 if benchmark_cv_html else 0)
                + (1 if benchmark_resume_html else 0)
            )
            logger.info(
                "pipeline_runtime.benchmark_core_docs_done",
                count=len(benchmark_documents),
                cv=bool(benchmark_cv_html),
                resume=bool(benchmark_resume_html),
                ready=ready_count,
            )

            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="cipher",
                message=f"Benchmark foundation: {ready_count}/6 core documents ready ✓",
                status="completed",
                data={"agent": "cipher", "source": "benchmark_core_docs", "ready": ready_count, "target": 6},
            ))
        except Exception as bench_core_err:
            logger.warning("pipeline_runtime.benchmark_core_docs_failed", error=str(bench_core_err)[:200])

        n_docs = len(discovered_documents)
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="cipher",
            message=f"Document strategy planned — {n_docs} document{'s' if n_docs != 1 else ''} queued ✓",
            status="completed",
            data={"agent": "cipher", "source": "priority_ranking"},
        ))

        # Per-stage critic gate (soft-fail): gap map validation.
        try:
            cipher_artifact = self._build_skill_gap_map_artifact(gap_analysis=gap_analysis)
            await self._run_critic_gate(
                phase="cipher",
                artifact=cipher_artifact,
                review="gap_map",
                user_id=user_id,
                progress_pass=46,
                progress_fail=42,
                message_pass="Gap-map critic gate passed.",
                message_fail="Gap-map critic gate found issues; continuing.",
            )
        except Exception as cipher_gate_err:
            logger.warning("pipeline_runtime.cipher_gate_failed", error=str(cipher_gate_err)[:200])

        for pn in ("gap_analysis",):
            await self.sink.emit(PipelineEvent(
                event_type="agent_status",
                pipeline_name=pn, stage="pipeline_done", status="completed",
                message=f"{pn} complete",
            ))
        self._finish_phase("cipher")

        # ── Phase 3: Core docs + Roadmap (parallel) ──────────────────
        self._begin_phase("quill")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="quill", progress=50,
            message="Agents: generating CV, cover letter & learning plan…",
        ))
        # Detail events — one per parallel sub-agent starting
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="quill",
            message="Generating tailored CV optimized for ATS keywords…",
            status="running",
            data={"agent": "quill", "source": "cv_generation"},
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="quill",
            message="Crafting personalized cover letter for role…",
            status="running",
            data={"agent": "quill", "source": "cover_letter"},
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="quill",
            message="Building learning & development roadmap…",
            status="running",
            data={"agent": "quill", "source": "learning_plan"},
        ))

        doc_context = {
            "user_id": user_id,
            "user_profile": user_profile,
            "job_title": job_title,
            "company": company,
            "jd_text": jd_text,
            "gap_analysis": gap_analysis,
            "resume_text": resume_text,
            "company_intel": self._build_intel_summary(company_intel),
        }

        cv_pipe = cv_generation_pipeline(
            ai_client=ai, on_stage_update=stage_callback,
            db=sb, tables=tables, user_id=user_id,
        )
        cl_pipe = cover_letter_pipeline(
            ai_client=ai, on_stage_update=stage_callback,
            db=sb, tables=tables, user_id=user_id,
        )
        consultant = CareerConsultantChain(ai)

        # Wrap each parallel task to emit mid-phase progress as they complete
        async def _run_cv():
            r = await cv_pipe.execute(doc_context)
            await self.sink.emit(PipelineEvent(
                event_type="progress", phase="quill", progress=58,
                message="CV generation complete, finishing others…",
            ))
            return r

        async def _run_cl():
            r = await cl_pipe.execute(doc_context)
            await self.sink.emit(PipelineEvent(
                event_type="progress", phase="quill", progress=63,
                message="Cover letter complete, finishing others…",
            ))
            return r

        async def _run_roadmap():
            r = await consultant.generate_roadmap(gap_analysis, user_profile, job_title, company)
            await self.sink.emit(PipelineEvent(
                event_type="progress", phase="quill", progress=67,
                message="Learning plan complete…",
            ))
            return r

        cv_result_raw, cl_result_raw, roadmap = await asyncio.gather(
            _run_cv(), _run_cl(), _run_roadmap(),
            return_exceptions=True,
        )

        cv_result: PipelineResult | None = None
        cl_result: PipelineResult | None = None

        if isinstance(cv_result_raw, Exception):
            logger.error("pipeline_runtime.cv_failed", error=str(cv_result_raw))
            self._failed_modules.append({"module": "cv", "error": str(cv_result_raw)[:200]})
            cv_html = ""
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="quill",
                message="CV generation encountered an issue",
                status="warning",
                data={"agent": "quill", "source": "cv_generation"},
            ))
        else:
            cv_result = cv_result_raw
            cv_html = self._extract_pipeline_html(cv_result.content)
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="quill",
                message="Tailored CV generated with ATS optimization ✓",
                status="completed",
                data={"agent": "quill", "source": "cv_generation"},
            ))

        if isinstance(cl_result_raw, Exception):
            logger.error("pipeline_runtime.cl_failed", error=str(cl_result_raw))
            self._failed_modules.append({"module": "cover_letter", "error": str(cl_result_raw)[:200]})
            cl_html = ""
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="quill",
                message="Cover letter generation encountered an issue",
                status="warning",
                data={"agent": "quill", "source": "cover_letter"},
            ))
        else:
            cl_result = cl_result_raw
            cl_html = self._extract_pipeline_html(cl_result.content)
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="quill",
                message="Personalized cover letter crafted ✓",
                status="completed",
                data={"agent": "quill", "source": "cover_letter"},
            ))

        if isinstance(roadmap, Exception):
            logger.error("pipeline_runtime.roadmap_failed", error=str(roadmap))
            self._failed_modules.append({"module": "roadmap", "error": str(roadmap)[:200]})
            roadmap = {}
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="quill",
                message="Learning plan encountered an issue",
                status="warning",
                data={"agent": "quill", "source": "learning_plan"},
            ))
        else:
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="quill",
                message="Learning & development roadmap complete ✓",
                status="completed",
                data={"agent": "quill", "source": "learning_plan"},
            ))

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="quill", progress=70,
            message="CV, cover letter & learning plan ready ✓",
        ))

        # Per-stage critic gate (soft-fail): partial tailored docs after Quill.
        # This intentionally checks only docs available by this phase.
        try:
            quill_bundle = self._build_tailored_bundle_artifact(
                cv_html=cv_html,
                cl_html=cl_html,
                ps_html="",
                portfolio_html="",
                resume_html=resume_html,
                application_id=self.config.application_id or None,
                created_by_agent="quill",
            )
            await self._run_critic_gate(
                phase="quill",
                artifact=quill_bundle,
                review="documents",
                user_id=user_id,
                progress_pass=69,
                progress_fail=65,
                message_pass="Quill document critic gate passed.",
                message_fail="Quill document critic gate found issues; continuing.",
            )
        except Exception as quill_gate_err:
            logger.warning("pipeline_runtime.quill_gate_failed", error=str(quill_gate_err)[:200])

        for pn in ("cv_generation", "cover_letter"):
            await self.sink.emit(PipelineEvent(
                event_type="agent_status",
                pipeline_name=pn, stage="pipeline_done", status="completed",
                message=f"{pn} complete",
            ))
        self._finish_phase("quill")

        # ── Phase 4: Personal statement + Portfolio (parallel) ────────
        self._begin_phase("forge")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="forge", progress=75,
            message="Agents: building personal statement & portfolio…",
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="forge",
            message="Writing compelling personal statement…",
            status="running",
            data={"agent": "forge", "source": "personal_statement"},
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="forge",
            message="Building project portfolio showcase…",
            status="running",
            data={"agent": "forge", "source": "portfolio_build"},
        ))

        ps_pipe = personal_statement_pipeline(
            ai_client=ai, on_stage_update=stage_callback,
            db=sb, tables=tables, user_id=user_id,
        )
        pf_pipe = portfolio_pipeline(
            ai_client=ai, on_stage_update=stage_callback,
            db=sb, tables=tables, user_id=user_id,
        )

        async def _run_ps():
            r = await ps_pipe.execute(doc_context)
            await self.sink.emit(PipelineEvent(
                event_type="progress", phase="forge", progress=79,
                message="Personal statement complete…",
            ))
            return r

        async def _run_pf():
            r = await pf_pipe.execute(doc_context)
            await self.sink.emit(PipelineEvent(
                event_type="progress", phase="forge", progress=81,
                message="Portfolio complete…",
            ))
            return r

        ps_raw, pf_raw = await asyncio.gather(
            _run_ps(), _run_pf(),
            return_exceptions=True,
        )

        ps_html = ""
        portfolio_html = ""
        if isinstance(ps_raw, Exception):
            logger.error("pipeline_runtime.ps_failed", error=str(ps_raw))
            self._failed_modules.append({"module": "personal_statement", "error": str(ps_raw)[:200]})
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="forge",
                message="Personal statement encountered an issue",
                status="warning",
                data={"agent": "forge", "source": "personal_statement"},
            ))
        else:
            ps_html = self._extract_pipeline_html(ps_raw.content)
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="forge",
                message="Personal statement written ✓",
                status="completed",
                data={"agent": "forge", "source": "personal_statement"},
            ))

        if isinstance(pf_raw, Exception):
            logger.error("pipeline_runtime.portfolio_failed", error=str(pf_raw))
            self._failed_modules.append({"module": "portfolio", "error": str(pf_raw)[:200]})
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="forge",
                message="Portfolio generation encountered an issue",
                status="warning",
                data={"agent": "forge", "source": "portfolio_build"},
            ))
        else:
            portfolio_html = self._extract_pipeline_html(pf_raw.content)
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="forge",
                message="Portfolio showcase assembled ✓",
                status="completed",
                data={"agent": "forge", "source": "portfolio_build"},
            ))

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="forge", progress=82,
            message="Personal statement & portfolio ready ✓",
        ))

        # ── Phase 4b: Extra required docs via AdaptiveDocumentChain ───
        generated_docs: Dict[str, str] = {}

        if doc_pack_plan and doc_pack_plan.required:
            await self.sink.emit(PipelineEvent(
                event_type="progress", phase="forge", progress=84,
                message=f"Generating {len(doc_pack_plan.required)} extra required documents…",
            ))

            adaptive = AdaptiveDocumentChain(ai)
            # Build intel summary for context
            intel_summary = self._build_intel_summary(company_intel)

            extra_context = {
                "profile": user_profile,
                "jd_text": jd_text,
                "job_title": job_title,
                "company": company,
                "industry": doc_pack_plan.industry,
                "tone": doc_pack_plan.tone,
                "key_themes": doc_pack_plan.key_themes,
                "gaps_summary": ", ".join(
                    g.get("skill", "") for g in gap_analysis.get("skill_gaps", [])[:8]
                    if isinstance(g, dict)
                ) or "None identified",
                "strengths_summary": ", ".join(
                    s.get("area", "") for s in gap_analysis.get("strengths", [])[:8]
                    if isinstance(s, dict)
                ) or "None identified",
                "benchmark_keywords": ", ".join(keywords[:15]),
                "company_intel": intel_summary,
            }

            # Generate in batches of 2 for parallelism without overwhelming API
            for i in range(0, len(doc_pack_plan.required), 2):
                batch = doc_pack_plan.required[i:i + 2]
                tasks = []
                for d in batch:
                    tasks.append(adaptive.generate(
                        doc_type=d["key"],
                        doc_label=d.get("label", d["key"]),
                        context=extra_context,
                        mode="user",
                    ))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                for d, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.error(f"pipeline_runtime.extra_doc_{d['key']}_failed",
                                     error=str(result)[:200])
                        self._failed_modules.append({"module": d["key"], "error": str(result)[:200]})
                    elif isinstance(result, str) and result.strip():
                        generated_docs[d["key"]] = result

            # Benchmark versions for required docs (best-effort)
            for i in range(0, len(doc_pack_plan.required), 2):
                batch = doc_pack_plan.required[i:i + 2]
                bench_tasks = []
                for d in batch:
                    bench_tasks.append(adaptive.generate(
                        doc_type=d["key"],
                        doc_label=d.get("label", d["key"]),
                        context=extra_context,
                        mode="benchmark",
                    ))

                bench_results = await asyncio.gather(*bench_tasks, return_exceptions=True)
                for d, result in zip(batch, bench_results):
                    if isinstance(result, str) and result.strip():
                        benchmark_documents[d["key"]] = result

            logger.info("pipeline_runtime.extra_docs_done",
                        generated=len(generated_docs),
                        benchmarks=len(benchmark_documents))

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="forge", progress=88,
            message="All documents ready ✓",
        ))
        n_extra = len(generated_docs)
        if n_extra > 0:
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="forge",
                message=f"{n_extra} supplementary document{'s' if n_extra != 1 else ''} generated ✓",
                status="completed",
                data={"agent": "forge", "source": "extra_docs"},
            ))

        # Per-stage critic gate (soft-fail): full tailored docs after Forge.
        try:
            forge_bundle = self._build_tailored_bundle_artifact(
                cv_html=cv_html,
                cl_html=cl_html,
                ps_html=ps_html,
                portfolio_html=portfolio_html,
                resume_html=resume_html,
                application_id=self.config.application_id or None,
                created_by_agent="forge",
            )
            required_mods = [
                m for m in (self.config.requested_modules or [])
                if m in {"cv", "resume", "cover_letter", "personal_statement", "portfolio"}
            ]
            await self._run_critic_gate(
                phase="forge",
                artifact=forge_bundle,
                review="documents",
                user_id=user_id,
                required_modules=required_mods or None,
                progress_pass=87,
                progress_fail=83,
                message_pass="Forge document critic gate passed.",
                message_fail="Forge document critic gate found issues; continuing.",
            )
        except Exception as forge_gate_err:
            logger.warning("pipeline_runtime.forge_gate_failed", error=str(forge_gate_err)[:200])

        for pn in ("personal_statement", "portfolio"):
            await self.sink.emit(PipelineEvent(
                event_type="agent_status",
                pipeline_name=pn, stage="pipeline_done", status="completed",
                message=f"{pn} complete",
            ))
        self._finish_phase("forge")

        # ── Phase 5: Validation ───────────────────────────────────────
        self._begin_phase("sentinel")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="sentinel", progress=92,
            message="Validating documents…",
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="sentinel",
            message="Running quality checks on all generated documents…",
            status="running",
            data={"agent": "sentinel", "source": "quality_check"},
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="sentinel",
            message="Checking ATS compatibility & keyword coverage…",
            status="running",
            data={"agent": "sentinel", "source": "ats_check"},
        ))

        cv_quality = cv_result.quality_scores if cv_result else {}
        cl_quality = cl_result.quality_scores if cl_result else {}
        cv_fact_check = cv_result.fact_check_report if cv_result else {}

        # ── Deterministic per-doc quality scoring (W2) ────────────────
        # Cheap, offline floor that catches obvious failure modes (empty
        # docs, ATS-hostile structure, missing JD keywords). Augments —
        # never replaces — the LLM-driven critique scores above.
        try:
            from app.services.quality_scorer import score_bundle  # local import to avoid cold-start cost
            from app.core.metrics import MetricsCollector

            docs_to_score: Dict[str, str] = {}
            if cv_html: docs_to_score["cv"] = cv_html
            if cl_html: docs_to_score["cover_letter"] = cl_html
            if ps_html: docs_to_score["personal_statement"] = ps_html
            if portfolio_html: docs_to_score["portfolio"] = portfolio_html
            effective_resume = resume_html or benchmark_resume_html
            if effective_resume: docs_to_score["resume"] = effective_resume
            for k, v in (generated_docs or {}).items():
                if isinstance(v, str) and v.strip() and k not in docs_to_score:
                    docs_to_score[k] = v

            per_doc_quality = score_bundle(docs_to_score, jd_keywords=keywords)
            self._per_doc_quality = per_doc_quality  # exposed for callers/tests

            # Record into MetricsCollector so /metrics can surface it.
            try:
                mc = MetricsCollector.get()
                for doc_type, breakdown in per_doc_quality.items():
                    mc.record_doc_quality(doc_type, int(breakdown.get("score", 0)))
            except Exception:
                pass

            # Surface low-quality docs to the user as warnings (non-fatal).
            for doc_type, breakdown in per_doc_quality.items():
                if breakdown.get("score", 0) < 60 and breakdown.get("issues"):
                    await self.sink.emit(PipelineEvent(
                        event_type="warning", phase="sentinel",
                        message=f"{doc_type}: quality {breakdown['score']}/100 — {breakdown['issues'][0]}",
                        data={"agent": "sentinel", "doc_type": doc_type,
                              "score": breakdown["score"], "issues": breakdown["issues"][:5]},
                    ))
        except Exception as q_err:
            logger.warning("pipeline_runtime.quality_scorer_failed", error=str(q_err)[:200])
            per_doc_quality = {}

        validation: Dict[str, Any] = {
            "cv": {
                "valid": bool(cv_html),
                "qualityScore": self._quality_score(cv_quality),
                "agent_powered": True,
            }
        }
        # Attach deterministic per-doc breakdowns under canonical keys so
        # the frontend can show issue lists per document.
        for _doc, _bd in per_doc_quality.items():
            target_key = {
                "cover_letter": "coverLetter",
                "personal_statement": "personalStatement",
            }.get(_doc, _doc)
            validation.setdefault(target_key, {})
            validation[target_key]["deterministicScore"] = int(_bd.get("score", 0))
            validation[target_key]["issues"] = list(_bd.get("issues", []))[:5]

        quality_score = self._quality_score(cv_quality)
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="sentinel",
            message=f"Quality score: {quality_score}/100 — document validation complete ✓",
            status="completed",
            data={"agent": "sentinel", "source": "quality_check"},
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="sentinel",
            message="ATS keyword optimization verified ✓",
            status="completed",
            data={"agent": "sentinel", "source": "ats_check"},
        ))
        if cv_fact_check:
            await self.sink.emit(PipelineEvent(
                event_type="detail", phase="sentinel",
                message="Fact-check report generated ✓",
                status="completed",
                data={"agent": "sentinel", "source": "fact_check"},
            ))

        # Per-stage critic gate (soft-fail): canonical validation outcome for
        # downstream status finalisation. This is what jobs.py consumes.
        try:
            sentinel_bundle = self._build_tailored_bundle_artifact(
                cv_html=cv_html,
                cl_html=cl_html,
                ps_html=ps_html,
                portfolio_html=portfolio_html,
                resume_html=resume_html or benchmark_resume_html,
                application_id=self.config.application_id or None,
                created_by_agent="sentinel",
            )
            required_mods = [
                m for m in (self.config.requested_modules or [])
                if m in {"cv", "resume", "cover_letter", "personal_statement", "portfolio"}
            ]
            sentinel_validation = await self._run_critic_gate(
                phase="sentinel",
                artifact=sentinel_bundle,
                review="documents",
                user_id=user_id,
                required_modules=required_mods or None,
                progress_pass=95,
                progress_fail=90,
                message_pass="Validation critic gate passed.",
                message_fail="Validation critic gate failed; continuing with warnings.",
            )
        except Exception as sentinel_gate_err:
            logger.warning("pipeline_runtime.sentinel_gate_failed", error=str(sentinel_gate_err)[:200])

        self._finish_phase("sentinel")

        # ── Phase 6: Format response ─────────────────────────────────
        self._begin_phase("nova")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="nova", progress=98,
            message="Packaging your application…",
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="nova",
            message="Assembling all documents into final package…",
            status="running",
            data={"agent": "nova", "source": "assembly"},
        ))

        from app.core.sanitize import sanitize_html

        # ── ISOLATED ASSEMBLY: failures from here on must NEVER discard
        # successful Quill/Forge work. Each block has its own try/except so a
        # bug in formatting does not nuke persistence and vice versa.

        # Resolve effective resume HTML once (tailored if available, else benchmark).
        effective_resume_html = resume_html or benchmark_resume_html or ""

        response: Dict[str, Any] = {}
        try:
            response = self._format_response(
                benchmark_data=benchmark_data,
                gap_analysis=gap_analysis,
                roadmap=roadmap if isinstance(roadmap, dict) else {},
                cv_html=sanitize_html(cv_html) if cv_html else "",
                cl_html=sanitize_html(cl_html) if cl_html else "",
                ps_html=sanitize_html(ps_html) if ps_html else "",
                portfolio_html=sanitize_html(portfolio_html) if portfolio_html else "",
                validation=validation,
                keywords=keywords,
                job_title=job_title,
                benchmark_cv_html=sanitize_html(benchmark_cv_html) if benchmark_cv_html else "",
                resume_html=sanitize_html(effective_resume_html) if effective_resume_html else "",
            )
            if sentinel_validation is not None:
                response["validation"] = sentinel_validation
        except Exception as fmt_err:
            logger.exception("pipeline_runtime.format_response_failed", error=str(fmt_err)[:300])
            self._failed_modules.append({"module": "format_response", "error": str(fmt_err)[:200]})
            # Build a minimal safe response so downstream callers still get the work that succeeded.
            response = {
                "benchmark": benchmark_data,
                "gapAnalysis": gap_analysis,
                "documents": {
                    "cv": sanitize_html(cv_html) if cv_html else "",
                    "coverLetter": sanitize_html(cl_html) if cl_html else "",
                    "personalStatement": sanitize_html(ps_html) if ps_html else "",
                    "portfolio": sanitize_html(portfolio_html) if portfolio_html else "",
                    "resume": sanitize_html(effective_resume_html) if effective_resume_html else "",
                },
                "validation": sentinel_validation if sentinel_validation is not None else validation,
                "_recovered_from_format_error": True,
            }

        # ── Attach dynamic doc-pack fields (each isolated) ────────────
        try:
            response["discoveredDocuments"] = discovered_documents
            response["generatedDocuments"] = {
                k: sanitize_html(v) for k, v in generated_docs.items() if v
            }
            bench_dict: Dict[str, Any] = {
                k: (sanitize_html(v) if isinstance(v, str) else v)
                for k, v in benchmark_documents.items()
            }
            if benchmark_cv_html:
                bench_dict["cv"] = sanitize_html(benchmark_cv_html)
            if benchmark_resume_html:
                bench_dict["resume"] = sanitize_html(benchmark_resume_html)
            response["benchmarkDocuments"] = bench_dict

            response["documentStrategy"] = (
                doc_pack_plan.strategy if doc_pack_plan else ""
            )
            response["docPackPlan"] = (
                doc_pack_plan.to_dict() if doc_pack_plan else None
            )
            if company_intel:
                response["companyIntel"] = company_intel
        except Exception as augment_err:
            logger.warning("pipeline_runtime.response_augment_failed", error=str(augment_err)[:200])
            self._failed_modules.append({"module": "response_augment", "error": str(augment_err)[:200]})

        # Agent metadata (isolated)
        try:
            response["meta"] = {
                "quality_scores": {"cv": cv_quality, "cover_letter": cl_quality},
                "fact_check": cv_fact_check,
                "agent_powered": True,
                "final_analysis": cv_result.final_analysis_report if cv_result else None,
                "validation_report": cv_result.validation_report if cv_result else None,
                "citations": cv_result.citations if cv_result else None,
                "evidence_summary": self._build_evidence_summary(cv_result),
                "workflow_state": cv_result.workflow_state if cv_result else None,
            }
        except Exception as meta_err:
            logger.warning("pipeline_runtime.meta_augment_failed", error=str(meta_err)[:200])

        # ── Persist to document_library table (isolated) ──────────────
        self._begin_phase("persist")
        try:
            await self._persist_to_document_library(
                sb=sb, tables=tables, user_id=user_id,
                cv_html=sanitize_html(cv_html) if cv_html else "",
                cl_html=sanitize_html(cl_html) if cl_html else "",
                ps_html=sanitize_html(ps_html) if ps_html else "",
                portfolio_html=sanitize_html(portfolio_html) if portfolio_html else "",
                benchmark_cv_html=sanitize_html(benchmark_cv_html) if benchmark_cv_html else "",
                resume_html=sanitize_html(effective_resume_html) if effective_resume_html else "",
                benchmark_resume_html=sanitize_html(benchmark_resume_html) if benchmark_resume_html else "",
                generated_docs={k: sanitize_html(v) for k, v in generated_docs.items() if v},
                benchmark_docs={
                    k: (sanitize_html(v) if isinstance(v, str) else v)
                    for k, v in benchmark_documents.items()
                },
            )
        except Exception as persist_err:
            logger.exception("pipeline_runtime.persist_failed", error=str(persist_err)[:300])
            self._failed_modules.append({"module": "persist_document_library", "error": str(persist_err)[:200]})
        self._finish_phase("persist")

        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="nova",
            message="Documents formatted & persisted ✓",
            status="completed",
            data={"agent": "nova", "source": "assembly"},
        ))
        await self.sink.emit(PipelineEvent(
            event_type="detail", phase="nova",
            message="Application package ready for delivery ✓",
            status="completed",
            data={"agent": "nova", "source": "packaging"},
        ))

        # Per-stage critic gate (soft-fail): final assembled pack sanity check.
        try:
            final_pack = self._build_final_pack_artifact(
                benchmark_data=benchmark_data,
                gap_analysis=gap_analysis,
                company=company,
                company_intel=company_intel,
                cv_html=cv_html,
                cl_html=cl_html,
                ps_html=ps_html,
                portfolio_html=portfolio_html,
                resume_html=effective_resume_html,
                sentinel_validation=sentinel_validation,
                elapsed_seconds=0.0,
            )
            await self._run_critic_gate(
                phase="nova",
                artifact=final_pack,
                review="final_pack",
                user_id=user_id,
                progress_pass=99,
                progress_fail=97,
                message_pass="Final-pack critic gate passed.",
                message_fail="Final-pack critic gate found issues; continuing.",
            )
        except Exception as nova_gate_err:
            logger.warning("pipeline_runtime.nova_gate_failed", error=str(nova_gate_err)[:200])

        self._finish_phase("nova")

        return response

    # ── Legacy (chain-only) fallback ──────────────────────────────────

    async def _run_legacy_pipeline(
        self,
        ai: Any,
        job_title: str,
        company: str,
        jd_text: str,
        resume_text: str,
    ) -> Dict[str, Any]:
        """Fallback path using direct chain calls (no agent orchestration)."""
        from ai_engine.chains.role_profiler import RoleProfilerChain
        from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
        from ai_engine.chains.gap_analyzer import GapAnalyzerChain
        from ai_engine.chains.document_generator import DocumentGeneratorChain
        from ai_engine.chains.career_consultant import CareerConsultantChain
        from ai_engine.chains.validator import ValidatorChain
        from app.core.sanitize import sanitize_html

        profiler = RoleProfilerChain(ai)
        benchmark_chain = BenchmarkBuilderChain(ai)

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=10,
            message="Parsing resume & building benchmark…",
        ))

        # Phase 1: Parse + benchmark
        user_profile = {}
        benchmark_data = {}
        try:
            if resume_text.strip():
                user_profile, benchmark_data = await asyncio.gather(
                    profiler.parse_resume(resume_text),
                    benchmark_chain.create_ideal_profile(job_title, company, jd_text),
                )
            else:
                benchmark_data = await benchmark_chain.create_ideal_profile(job_title, company, jd_text)
        except Exception as phase1_err:
            logger.warning("pipeline_runtime.legacy_phase1_failed", error=str(phase1_err)[:200])
            self._failed_modules.append({"module": "benchmark", "error": str(phase1_err)[:200]})

        ideal_skills = benchmark_data.get("ideal_skills", [])
        keywords = [s.get("name", "") for s in ideal_skills if isinstance(s, dict) and s.get("name")]
        if not keywords:
            keywords = self._extract_keywords_from_jd(jd_text)

        benchmark_cv_html = ""
        benchmark_resume_html = ""
        resume_html = ""  # tailored resume — prevents late-stage NameError in _format_response
        try:
            benchmark_cv_html = await benchmark_chain.create_benchmark_cv_html(
                user_profile=user_profile, benchmark_data=benchmark_data,
                job_title=job_title, company=company, jd_text=jd_text,
            )
        except Exception:
            pass
        try:
            benchmark_resume_html = await benchmark_chain.create_resume_html(
                user_profile=user_profile, benchmark_data=benchmark_data,
                job_title=job_title, company=company, jd_text=jd_text,
            )
        except Exception:
            pass

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=25,
            message="Resume parsed & benchmark built ✓",
        ))

        # Phase 2: Gap analysis
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=30,
            message="Analyzing skill gaps…",
        ))

        gap_chain = GapAnalyzerChain(ai)
        gap_analysis = {}
        try:
            gap_analysis = await gap_chain.analyze_gaps(user_profile, benchmark_data, job_title, company)
        except Exception as gap_err:
            logger.warning("pipeline_runtime.legacy_gap_failed", error=str(gap_err)[:200])
            self._failed_modules.append({"module": "gap_analysis", "error": str(gap_err)[:200]})

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=45,
            message="Gap analysis complete ✓",
        ))

        # Phase 3: Documents (parallel)
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="quill", progress=50,
            message="Generating documents…",
        ))

        doc_chain = DocumentGeneratorChain(ai)
        consultant = CareerConsultantChain(ai)

        cv_html, cl_html, roadmap = await asyncio.gather(
            doc_chain.generate_tailored_cv(
                user_profile=user_profile, job_title=job_title,
                company=company, jd_text=jd_text,
                gap_analysis=gap_analysis, resume_text=resume_text,
            ),
            doc_chain.generate_tailored_cover_letter(
                user_profile=user_profile, job_title=job_title,
                company=company, jd_text=jd_text, gap_analysis=gap_analysis,
            ),
            consultant.generate_roadmap(gap_analysis, user_profile, job_title, company),
            return_exceptions=True,
        )

        if isinstance(cv_html, Exception):
            self._failed_modules.append({"module": "cv", "error": str(cv_html)[:200]})
            cv_html = ""
        if isinstance(cl_html, Exception):
            self._failed_modules.append({"module": "cover_letter", "error": str(cl_html)[:200]})
            cl_html = ""
        if isinstance(roadmap, Exception):
            self._failed_modules.append({"module": "roadmap", "error": str(roadmap)[:200]})
            roadmap = {}

        # PS + Portfolio
        ps_html, portfolio_html = "", ""
        try:
            ps_result, portfolio_result = await asyncio.gather(
                doc_chain.generate_tailored_personal_statement(
                    user_profile=user_profile, job_title=job_title,
                    company=company, jd_text=jd_text,
                    gap_analysis=gap_analysis, resume_text=resume_text,
                ),
                doc_chain.generate_tailored_portfolio(
                    user_profile=user_profile, job_title=job_title,
                    company=company, jd_text=jd_text,
                    gap_analysis=gap_analysis, resume_text=resume_text,
                ),
                return_exceptions=True,
            )
            if isinstance(ps_result, Exception):
                self._failed_modules.append({"module": "personal_statement", "error": str(ps_result)[:200]})
            else:
                ps_html = ps_result if isinstance(ps_result, str) else ""
            if isinstance(portfolio_result, Exception):
                self._failed_modules.append({"module": "portfolio", "error": str(portfolio_result)[:200]})
            else:
                portfolio_html = portfolio_result if isinstance(portfolio_result, str) else ""
        except Exception as p4_err:
            self._failed_modules.append({"module": "phase4_docs", "error": str(p4_err)[:200]})

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="quill", progress=85,
            message="All documents generated ✓",
        ))

        # Phase 4: Validation
        validation = {}
        try:
            validator = ValidatorChain(ai)
            if cv_html:
                cv_valid, cv_validation = await validator.validate_document(
                    document_type="Tailored CV",
                    content=cv_html[:3000],
                    profile_data=user_profile,
                )
                validation["cv"] = {
                    "valid": cv_valid,
                    "qualityScore": cv_validation.get("quality_score", 0),
                    "issues": len(cv_validation.get("issues", [])),
                }
        except Exception:
            pass

        response = self._format_response(
            benchmark_data=benchmark_data,
            gap_analysis=gap_analysis,
            roadmap=roadmap if isinstance(roadmap, dict) else {},
            cv_html=sanitize_html(cv_html) if cv_html else "",
            cl_html=sanitize_html(cl_html) if cl_html else "",
            ps_html=sanitize_html(ps_html) if ps_html else "",
            portfolio_html=sanitize_html(portfolio_html) if portfolio_html else "",
            validation=validation,
            keywords=keywords,
            job_title=job_title,
            benchmark_cv_html=sanitize_html(benchmark_cv_html) if benchmark_cv_html else "",
            resume_html=sanitize_html(resume_html) if resume_html else (sanitize_html(benchmark_resume_html) if benchmark_resume_html else ""),
        )

        # ── v4 critic gate (best-effort): build a typed TailoredDocumentBundle
        # from what we just generated, run it through ValidationCritic, persist
        # the ValidationReport artifact, and emit validation_passed/failed.
        try:
            from ai_engine.agents.artifact_contracts import (
                DocumentRecord,
                EvidenceTier,
                TailoredDocumentBundle,
            )
            from ai_engine.agents.validation_critic import (
                ValidationCritic,
                report_passed,
            )

            doc_records: Dict[str, "DocumentRecord"] = {}
            for key, html in (
                ("cv", cv_html),
                ("cover_letter", cl_html),
                ("personal_statement", ps_html),
                ("portfolio", portfolio_html),
                ("resume", resume_html or benchmark_resume_html),
            ):
                html_clean = (html or "").strip()
                if html_clean:
                    doc_records[key] = DocumentRecord(
                        doc_type=key, label=key.replace("_", " ").title(),
                        html_content=html_clean,
                        word_count=len(html_clean.split()),
                    )

            tailored_bundle = TailoredDocumentBundle(
                application_id=self.config.application_id or None,
                created_by_agent="quill",
                confidence=0.7,
                evidence_tier=EvidenceTier.DERIVED,
                documents=doc_records,
            )

            critic = ValidationCritic()
            report = critic.review_documents(
                tailored_bundle,
                required_modules=self.config.requested_modules or None,
            )
            passed = report_passed(report)

            # ── ENFORCE the gate by stamping the response.
            # The job runner reads response["validation"] and downgrades the
            # job status to "succeeded_with_warnings" when passed=False, so
            # the UI can surface the failure without losing already-generated
            # documents. This is the contract the audit demanded: a failure
            # signal that actually flips persisted job state.
            error_findings = [
                f for f in report.findings
                if getattr(f.severity, "value", str(f.severity)) == "error"
            ]
            warning_findings = [
                f for f in report.findings
                if getattr(f.severity, "value", str(f.severity)) == "warning"
            ]
            response["validation"] = {
                "passed": bool(passed),
                "overall_score": float(report.overall_score),
                "docs_passed": list(report.docs_passed),
                "docs_failed": list(report.docs_failed),
                "error_count": len(error_findings),
                "warning_count": len(warning_findings),
                "finding_count": len(report.findings),
                "findings_summary": [
                    {
                        "code": f.rule,
                        "severity": getattr(f.severity, "value", str(f.severity)),
                        "message": f.message,
                        "doc_type": getattr(f, "target_doc_type", None),
                    }
                    for f in report.findings[:20]
                ],
            }

            if getattr(self, "_artifact_store", None) is not None:
                try:
                    await self._artifact_store.put(
                        report, user_id=user_id,
                        agent_name="validation_critic",
                        artifact_type="ValidationReport",
                    )
                except Exception:
                    pass

            await self.sink.emit(PipelineEvent(
                event_type="validation_passed" if passed else "validation_failed",
                phase="sentinel",
                progress=95 if passed else 90,
                message=(
                    f"Validation {'passed' if passed else 'failed'} "
                    f"(score {report.overall_score:.0f}/100, "
                    f"{len(report.findings)} findings)"
                ),
                status="completed" if passed else "warning",
                data={
                    "overall_score": report.overall_score,
                    "docs_passed": report.docs_passed,
                    "docs_failed": report.docs_failed,
                    "finding_count": len(report.findings),
                },
            ))
            # Publish through the typed bus so the bridge round-trips this too.
            try:
                from ai_engine.agents.orchestration import (
                    EventLevel as _EL,
                    OrchestrationEvent as _OE,
                )
                bus = getattr(self, "_orchestration_bus", None)
                if bus is not None:
                    await bus.publish(_OE(
                        event_name=(
                            "orchestration.validation_passed"
                            if passed else "orchestration.validation_failed"
                        ),
                        application_id=self.config.application_id or None,
                        agent_name="validation_critic",
                        level=_EL.INFO if passed else _EL.WARNING,
                        message=(
                            f"Validation {'passed' if passed else 'failed'} "
                            f"(score {report.overall_score:.0f}/100)"
                        ),
                        data={
                            "phase": "sentinel",
                            "progress": 95 if passed else 90,
                            "overall_score": report.overall_score,
                            "docs_passed": report.docs_passed,
                            "docs_failed": report.docs_failed,
                            "finding_count": len(report.findings),
                        },
                    ))
            except Exception:
                pass
        except Exception as critic_err:
            logger.warning("pipeline_runtime.critic_skipped",
                           error=str(critic_err)[:200])

        return response

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_benchmark_profile_artifact(
        *,
        job_title: str,
        company: str,
        benchmark_data: Dict[str, Any],
    ) -> Any:
        from ai_engine.agents.artifact_contracts import (
            BenchmarkProfile,
            BenchmarkSkill,
            EvidenceTier,
        )

        ideal_skills = benchmark_data.get("ideal_skills")
        skills: List[BenchmarkSkill] = []
        if isinstance(ideal_skills, list):
            for raw in ideal_skills:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "").strip()
                if not name:
                    continue
                level = str(raw.get("level") or "intermediate").lower()
                if level not in {"expert", "advanced", "intermediate", "beginner"}:
                    level = "intermediate"
                importance = str(raw.get("importance") or "important").lower()
                if importance not in {"critical", "important", "preferred"}:
                    importance = "important"
                years = raw.get("years")
                if not isinstance(years, int):
                    years = 0
                category = str(raw.get("category") or "technical").lower()
                if category not in {"technical", "soft", "domain"}:
                    category = "technical"
                skills.append(BenchmarkSkill(
                    name=name,
                    level=level,
                    years=years,
                    category=category,
                    importance=importance,
                ))

        ideal_profile = benchmark_data.get("ideal_profile") if isinstance(benchmark_data.get("ideal_profile"), dict) else {}
        summary = str(ideal_profile.get("summary") or "").strip()
        years_exp = ideal_profile.get("years_experience")
        if not isinstance(years_exp, int):
            years_exp = 0

        return BenchmarkProfile(
            application_id=None,
            created_by_agent="atlas",
            confidence=0.7,
            evidence_tier=EvidenceTier.DERIVED,
            job_title=job_title,
            company=company,
            summary=summary,
            years_experience=years_exp,
            skills=skills,
            certifications=benchmark_data.get("certifications", []) if isinstance(benchmark_data.get("certifications"), list) else [],
            education=benchmark_data.get("education", []) if isinstance(benchmark_data.get("education"), list) else [],
            experience=benchmark_data.get("ideal_experience", []) if isinstance(benchmark_data.get("ideal_experience"), list) else [],
            scoring_weights=benchmark_data.get("scoring_weights", {}) if isinstance(benchmark_data.get("scoring_weights"), dict) else {},
        )

    @staticmethod
    def _build_skill_gap_map_artifact(*, gap_analysis: Dict[str, Any]) -> Any:
        from ai_engine.agents.artifact_contracts import (
            EvidenceTier,
            SkillGap,
            SkillGapMap,
            SkillStrength,
        )

        raw_score = gap_analysis.get("compatibility_score", 0.0)
        try:
            score = float(raw_score)
        except Exception:
            score = 0.0
        if score > 1.0:
            score = score / 100.0
        score = max(0.0, min(1.0, score))

        gaps: List[SkillGap] = []
        for g in gap_analysis.get("skill_gaps", []) if isinstance(gap_analysis.get("skill_gaps"), list) else []:
            if not isinstance(g, dict):
                continue
            skill = str(g.get("skill") or "").strip()
            if not skill:
                continue
            user_level = str(g.get("current_level") or "none").lower()
            if user_level not in {"expert", "advanced", "intermediate", "beginner", "none"}:
                user_level = "none"
            target_level = str(g.get("required_level") or "intermediate").lower()
            if target_level not in {"expert", "advanced", "intermediate", "beginner"}:
                target_level = "intermediate"
            severity = str(g.get("gap_severity") or "medium").lower()
            severity_map = {
                "critical": "critical",
                "high": "high",
                "significant": "high",
                "moderate": "medium",
                "medium": "medium",
                "minor": "low",
                "low": "low",
            }
            severity = severity_map.get(severity, "medium")
            gaps.append(SkillGap(
                skill=skill,
                user_level=user_level,
                target_level=target_level,
                severity=severity,
                closing_strategy=str(g.get("recommendation") or "").strip() or None,
            ))

        strengths: List[SkillStrength] = []
        for s in gap_analysis.get("strengths", []) if isinstance(gap_analysis.get("strengths"), list) else []:
            if isinstance(s, dict):
                area = str(s.get("area") or "").strip()
                if not area:
                    continue
                strengths.append(SkillStrength(area=area, evidence=str(s.get("description") or "").strip()))

        transferable = gap_analysis.get("transferable_skills", []) if isinstance(gap_analysis.get("transferable_skills"), list) else []
        risk_areas = gap_analysis.get("risk_areas", []) if isinstance(gap_analysis.get("risk_areas"), list) else []

        return SkillGapMap(
            application_id=None,
            created_by_agent="cipher",
            confidence=0.7,
            evidence_tier=EvidenceTier.DERIVED,
            overall_alignment=score,
            gaps=gaps,
            strengths=strengths,
            transferable_skills=[str(x) for x in transferable if str(x).strip()],
            risk_areas=[str(x) for x in risk_areas if str(x).strip()],
        )

    @staticmethod
    def _build_tailored_bundle_artifact(
        *,
        cv_html: str,
        cl_html: str,
        ps_html: str,
        portfolio_html: str,
        resume_html: str,
        application_id: Optional[str],
        created_by_agent: str,
    ) -> Any:
        from ai_engine.agents.artifact_contracts import (
            DocumentRecord,
            EvidenceTier,
            TailoredDocumentBundle,
        )

        docs: Dict[str, str] = {
            "cv": cv_html,
            "cover_letter": cl_html,
            "personal_statement": ps_html,
            "portfolio": portfolio_html,
            "resume": resume_html,
        }

        records: Dict[str, DocumentRecord] = {}
        for key, html in docs.items():
            html_clean = (html or "").strip()
            if not html_clean:
                continue
            records[key] = DocumentRecord(
                doc_type=key,
                label=key.replace("_", " ").title(),
                html_content=html_clean,
                word_count=len(html_clean.split()),
            )

        return TailoredDocumentBundle(
            application_id=application_id,
            created_by_agent=created_by_agent,
            confidence=0.7,
            evidence_tier=EvidenceTier.DERIVED,
            documents=records,
        )

    @staticmethod
    def _build_final_pack_artifact(
        *,
        benchmark_data: Dict[str, Any],
        gap_analysis: Dict[str, Any],
        company: str,
        company_intel: Dict[str, Any],
        cv_html: str,
        cl_html: str,
        ps_html: str,
        portfolio_html: str,
        resume_html: str,
        sentinel_validation: Optional[Dict[str, Any]],
        elapsed_seconds: float,
    ) -> Any:
        from ai_engine.agents.artifact_contracts import (
            CompanyIntelReport,
            EvidenceTier,
            FinalApplicationPack,
            ValidationReport,
            ValidationFinding,
        )

        benchmark_artifact = PipelineRuntime._build_benchmark_profile_artifact(
            job_title=str(benchmark_data.get("job_title") or ""),
            company=str(benchmark_data.get("company") or company or ""),
            benchmark_data=benchmark_data,
        )
        gap_artifact = PipelineRuntime._build_skill_gap_map_artifact(gap_analysis=gap_analysis)
        tailored_bundle = PipelineRuntime._build_tailored_bundle_artifact(
            cv_html=cv_html,
            cl_html=cl_html,
            ps_html=ps_html,
            portfolio_html=portfolio_html,
            resume_html=resume_html,
            application_id=None,
            created_by_agent="nova",
        )

        intel_summary = ""
        if isinstance(company_intel, dict):
            intel_summary = str(company_intel.get("summary") or company_intel.get("company_summary") or "")
        intel_artifact = CompanyIntelReport(
            application_id=None,
            created_by_agent="recon",
            confidence=0.7,
            evidence_tier=EvidenceTier.DERIVED,
            company=company,
            summary=intel_summary,
            raw=company_intel if isinstance(company_intel, dict) else {},
        )

        validation_artifact = None
        if sentinel_validation:
            findings: List[ValidationFinding] = []
            for f in sentinel_validation.get("findings_summary", []) if isinstance(sentinel_validation.get("findings_summary"), list) else []:
                if not isinstance(f, dict):
                    continue
                sev = str(f.get("severity") or "warning")
                if sev not in {"error", "warning", "info"}:
                    sev = "warning"
                findings.append(ValidationFinding(
                    severity=sev,
                    rule=str(f.get("code") or "runtime.critic"),
                    message=str(f.get("message") or ""),
                    target_doc_type=str(f.get("doc_type") or ""),
                ))
            validation_artifact = ValidationReport(
                application_id=None,
                created_by_agent="validation_critic",
                confidence=1.0,
                evidence_tier=EvidenceTier.DERIVED,
                overall_score=float(sentinel_validation.get("overall_score", 0.0) or 0.0),
                findings=findings,
                docs_passed=[str(x) for x in (sentinel_validation.get("docs_passed") or [])],
                docs_failed=[str(x) for x in (sentinel_validation.get("docs_failed") or [])],
            )

        return FinalApplicationPack(
            application_id=None,
            created_by_agent="nova",
            confidence=0.7,
            evidence_tier=EvidenceTier.DERIVED,
            benchmark=benchmark_artifact,
            company_intel=intel_artifact,
            gap_map=gap_artifact,
            tailored_docs=tailored_bundle,
            validation=validation_artifact,
            elapsed_seconds=max(0.0, float(elapsed_seconds or 0.0)),
        )

    async def _run_critic_gate(
        self,
        *,
        phase: str,
        artifact: Any,
        review: str,
        user_id: str,
        required_modules: Optional[List[str]] = None,
        progress_pass: int,
        progress_fail: int,
        message_pass: str,
        message_fail: str,
    ) -> Optional[Dict[str, Any]]:
        """Run ValidationCritic as a soft gate and emit a phase-scoped signal.

        This never raises. On any failure we log and return None so pipeline
        progress is not blocked.
        """
        try:
            from ai_engine.agents.validation_critic import ValidationCritic, report_passed

            critic = ValidationCritic()
            if review == "benchmark":
                report = critic.review_benchmark(artifact)
            elif review == "gap_map":
                report = critic.review_gap_map(artifact)
            elif review == "documents":
                report = critic.review_documents(artifact, required_modules=required_modules)
            elif review == "final_pack":
                report = critic.review_final_pack(artifact)
            elif review == "plan":
                report = critic.review_plan(artifact)
            else:
                logger.warning("pipeline_runtime.critic_unknown_review", phase=phase, review=review)
                return None

            passed = bool(report_passed(report))
            error_findings = [f for f in report.findings if getattr(f, "severity", "") == "error"]
            warning_findings = [f for f in report.findings if getattr(f, "severity", "") == "warning"]

            summary = {
                "passed": passed,
                "overall_score": float(report.overall_score),
                "docs_passed": list(report.docs_passed),
                "docs_failed": list(report.docs_failed),
                "error_count": len(error_findings),
                "warning_count": len(warning_findings),
                "finding_count": len(report.findings),
                "findings_summary": [
                    {
                        "code": getattr(f, "rule", "runtime.critic"),
                        "severity": getattr(f, "severity", "warning"),
                        "message": getattr(f, "message", ""),
                        "doc_type": getattr(f, "target_doc_type", None),
                    }
                    for f in report.findings[:20]
                ],
            }

            if getattr(self, "_artifact_store", None) is not None:
                try:
                    await self._artifact_store.put(
                        report,
                        user_id=user_id,
                        agent_name="validation_critic",
                        artifact_type="ValidationReport",
                    )
                except Exception as artifact_err:
                    logger.warning(
                        "pipeline_runtime.critic_artifact_persist_failed",
                        phase=phase,
                        error=str(artifact_err)[:200],
                    )

            await self.sink.emit(PipelineEvent(
                event_type="validation_passed" if passed else "validation_failed",
                phase=phase,
                progress=progress_pass if passed else progress_fail,
                message=message_pass if passed else message_fail,
                status="completed" if passed else "warning",
                data={
                    "overall_score": summary["overall_score"],
                    "docs_passed": summary["docs_passed"],
                    "docs_failed": summary["docs_failed"],
                    "error_count": summary["error_count"],
                    "warning_count": summary["warning_count"],
                    "finding_count": summary["finding_count"],
                },
            ))

            try:
                from ai_engine.agents.orchestration import (
                    EventLevel as _EL,
                    OrchestrationEvent as _OE,
                )

                bus = getattr(self, "_orchestration_bus", None)
                if bus is not None:
                    await bus.publish(_OE(
                        event_name=(
                            "orchestration.validation_passed"
                            if passed else "orchestration.validation_failed"
                        ),
                        application_id=self.config.application_id or None,
                        agent_name="validation_critic",
                        level=_EL.INFO if passed else _EL.WARNING,
                        message=(message_pass if passed else message_fail),
                        data={
                            "phase": phase,
                            "progress": progress_pass if passed else progress_fail,
                            **summary,
                        },
                    ))
            except Exception:
                pass

            return summary
        except Exception as critic_err:
            logger.warning("pipeline_runtime.critic_gate_skipped", phase=phase, error=str(critic_err)[:200])
            return None

    async def _persist_to_document_library(
        self,
        sb: Any,
        tables: Dict[str, str],
        user_id: str,
        cv_html: str,
        cl_html: str,
        ps_html: str,
        portfolio_html: str,
        benchmark_cv_html: str,
        generated_docs: Dict[str, str],
        benchmark_docs: Dict[str, str],
        resume_html: str = "",
        benchmark_resume_html: str = "",
    ) -> None:
        """Persist all generated documents to the document_library table."""
        if "document_library" not in tables:
            logger.warning("pipeline_runtime.persist_skipped", reason="document_library table not in TABLES config")
            return
        application_id = self.config.application_id
        if not application_id:
            logger.warning("pipeline_runtime.persist_skipped", reason="no application_id in pipeline config")
            return

        try:
            from app.services.document_library import DocumentLibraryService
            service = DocumentLibraryService(sb, tables)

            # Build all upsert coroutines for concurrent execution.
            # We use upsert_application_document so that any planned rows seeded
            # at Atlas startup are UPDATED in-place rather than duplicated.
            coros = []

            # Tailored core documents (CV + Resume now both first-class)
            tailored_count = 0
            for doc_spec in [
                {"doc_type": "cv",                 "label": "Tailored CV",                 "html": cv_html},
                {"doc_type": "resume",              "label": "Tailored Résumé",              "html": resume_html},
                {"doc_type": "cover_letter",        "label": "Tailored Cover Letter",        "html": cl_html},
                {"doc_type": "personal_statement",  "label": "Tailored Personal Statement",  "html": ps_html},
                {"doc_type": "portfolio",           "label": "Tailored Portfolio",           "html": portfolio_html},
            ]:
                if doc_spec["html"]:
                    tailored_count += 1
                    coros.append(service.upsert_application_document(
                        user_id=user_id,
                        application_id=application_id,
                        doc_category="tailored",
                        doc_type=doc_spec["doc_type"],
                        label=doc_spec["label"],
                        html_content=doc_spec["html"],
                        status="ready",
                        source="planner",
                    ))

            # Extra generated documents (tailored)
            for key, html in generated_docs.items():
                if html:
                    tailored_count += 1
                    coros.append(service.upsert_application_document(
                        user_id=user_id,
                        application_id=application_id,
                        doc_category="tailored",
                        doc_type=key,
                        label=key.replace("_", " ").title(),
                        html_content=html,
                        status="ready",
                        source="planner",
                    ))

            # Benchmark documents (CV + Resume now both first-class)
            benchmark_count = 0
            if benchmark_cv_html:
                benchmark_count += 1
                coros.append(service.upsert_application_document(
                    user_id=user_id,
                    application_id=application_id,
                    doc_category="benchmark",
                    doc_type="cv",
                    label="Benchmark CV",
                    html_content=benchmark_cv_html,
                    status="ready",
                    source="planner",
                ))
            if benchmark_resume_html:
                benchmark_count += 1
                coros.append(service.upsert_application_document(
                    user_id=user_id,
                    application_id=application_id,
                    doc_category="benchmark",
                    doc_type="resume",
                    label="Benchmark Résumé",
                    html_content=benchmark_resume_html,
                    status="ready",
                    source="planner",
                ))
            for key, html in benchmark_docs.items():
                if html and isinstance(html, str):
                    benchmark_count += 1
                    coros.append(service.upsert_application_document(
                        user_id=user_id,
                        application_id=application_id,
                        doc_category="benchmark",
                        doc_type=key,
                        label=f"Benchmark {key.replace('_', ' ').title()}",
                        html_content=html,
                        status="ready",
                        source="planner",
                    ))

            # Fan-out: all upserts run concurrently
            results = await asyncio.gather(*coros, return_exceptions=True)
            failures = sum(1 for r in results if isinstance(r, Exception))
            if failures:
                logger.warning(
                    "pipeline_runtime.document_library_partial_failure",
                    total=len(coros),
                    failures=failures,
                )

            # ── Mark missing canonical docs as "error" so the UI can show
            # a retry chip rather than a stale "planned" badge. We compare
            # what was supposed to be in the canonical set vs. what we
            # actually persisted as ready content.
            try:
                error_coros = []
                # Tailored canonical
                if not (cv_html or "").strip():
                    error_coros.append(service.upsert_application_document(
                        user_id=user_id, application_id=application_id,
                        doc_category="tailored", doc_type="cv",
                        label="Tailored CV", status="error",
                        error_message="Generation failed — tap retry to try again.",
                    ))
                if not (resume_html or "").strip():
                    error_coros.append(service.upsert_application_document(
                        user_id=user_id, application_id=application_id,
                        doc_category="tailored", doc_type="resume",
                        label="Tailored Résumé", status="error",
                        error_message="Generation failed — tap retry to try again.",
                    ))
                if not (cl_html or "").strip():
                    error_coros.append(service.upsert_application_document(
                        user_id=user_id, application_id=application_id,
                        doc_category="tailored", doc_type="cover_letter",
                        label="Tailored Cover Letter", status="error",
                        error_message="Generation failed — tap retry to try again.",
                    ))
                if not (ps_html or "").strip():
                    error_coros.append(service.upsert_application_document(
                        user_id=user_id, application_id=application_id,
                        doc_category="tailored", doc_type="personal_statement",
                        label="Tailored Personal Statement", status="error",
                        error_message="Generation failed — tap retry to try again.",
                    ))
                if not (portfolio_html or "").strip():
                    error_coros.append(service.upsert_application_document(
                        user_id=user_id, application_id=application_id,
                        doc_category="tailored", doc_type="portfolio",
                        label="Tailored Portfolio", status="error",
                        error_message="Generation failed — tap retry to try again.",
                    ))
                # Benchmark canonical (6 docs)
                if not (benchmark_cv_html or "").strip():
                    error_coros.append(service.upsert_application_document(
                        user_id=user_id, application_id=application_id,
                        doc_category="benchmark", doc_type="cv",
                        label="Benchmark CV", status="error",
                        error_message="Generation failed — tap retry to try again.",
                    ))
                if not (benchmark_resume_html or "").strip():
                    error_coros.append(service.upsert_application_document(
                        user_id=user_id, application_id=application_id,
                        doc_category="benchmark", doc_type="resume",
                        label="Benchmark Résumé", status="error",
                        error_message="Generation failed — tap retry to try again.",
                    ))
                _BENCH_REM = [
                    ("cover_letter", "Benchmark Cover Letter"),
                    ("personal_statement", "Benchmark Personal Statement"),
                    ("portfolio", "Benchmark Portfolio"),
                    ("learning_plan", "Benchmark Learning Plan"),
                ]
                for _key, _label in _BENCH_REM:
                    if not (benchmark_docs.get(_key) or "").strip():
                        error_coros.append(service.upsert_application_document(
                            user_id=user_id, application_id=application_id,
                            doc_category="benchmark", doc_type=_key,
                            label=_label, status="error",
                            error_message="Generation failed — tap retry to try again.",
                        ))
                if error_coros:
                    await asyncio.gather(*error_coros, return_exceptions=True)
            except Exception as err_mark_err:
                logger.warning("pipeline_runtime.error_mark_failed", error=str(err_mark_err)[:200])

            logger.info("pipeline_runtime.document_library_persisted",
                        tailored=tailored_count,
                        benchmarks=benchmark_count,
                        total=len(coros),
                        failures=failures)
        except Exception as e:
            logger.warning("pipeline_runtime.document_library_persist_failed", error=str(e)[:200])

    @staticmethod
    def _agents_available() -> bool:
        try:
            from ai_engine.agents.pipelines import resume_parse_pipeline  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _extract_pipeline_html(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if not isinstance(payload, dict):
            return ""
        html = payload.get("html")
        if isinstance(html, str):
            return html
        nested = payload.get("content")
        if isinstance(nested, str):
            return nested
        if isinstance(nested, dict):
            nested_html = nested.get("html")
            if isinstance(nested_html, str):
                return nested_html
        return ""

    @staticmethod
    def _quality_score(scores: Any) -> float:
        if not isinstance(scores, dict) or not scores:
            return 0.0
        overall = scores.get("overall")
        if isinstance(overall, (int, float)):
            return float(overall)
        numeric = [float(v) for v in scores.values() if isinstance(v, (int, float))]
        return round(sum(numeric) / len(numeric), 1) if numeric else 0.0

    @staticmethod
    def _extract_keywords_from_jd(jd_text: str) -> list[str]:
        """Extract keywords from JD text as fallback."""
        import re as _re
        words = _re.findall(r'\b[A-Z][a-zA-Z+#]{2,}\b', jd_text)
        seen: set[str] = set()
        result: list[str] = []
        for w in words:
            low = w.lower()
            if low not in seen:
                seen.add(low)
                result.append(w)
        return result[:20]

    @staticmethod
    def _build_intel_summary(company_intel: Dict[str, Any]) -> str:
        """Build a rich company intel summary string for document context.

        This feeds into CV, cover letter, personal statement, portfolio,
        and adaptive document generation — every section that references
        company-specific intelligence.  The more context here, the more
        tailored and impressive the generated documents will be.
        """
        if not company_intel:
            return ""

        parts: list[str] = []

        # ── Company overview ──────────────────────────────────
        overview = company_intel.get("company_overview", {})
        if isinstance(overview, dict):
            desc = overview.get("description") or overview.get("elevator_pitch") or ""
            if desc:
                parts.append(f"COMPANY: {desc}")
            info_bits: list[str] = []
            if overview.get("industry"):
                info_bits.append(f"Industry: {overview['industry']}")
            if overview.get("size"):
                info_bits.append(f"Size: {overview['size']}")
            if overview.get("stage"):
                info_bits.append(f"Stage: {overview['stage']}")
            if overview.get("headquarters"):
                info_bits.append(f"HQ: {overview['headquarters']}")
            if info_bits:
                parts.append(" | ".join(info_bits))

        # ── Culture & values ──────────────────────────────────
        culture = company_intel.get("culture_and_values", {})
        if isinstance(culture, dict):
            if culture.get("core_values"):
                vals = culture["core_values"]
                parts.append(f"VALUES: {', '.join(vals[:8]) if isinstance(vals, list) else str(vals)}")
            if culture.get("mission_statement"):
                parts.append(f"MISSION: {culture['mission_statement']}")
            if culture.get("work_style"):
                parts.append(f"WORK STYLE: {culture['work_style']}")
            if culture.get("what_kind_of_person_thrives"):
                parts.append(f"IDEAL CANDIDATE PROFILE: {culture['what_kind_of_person_thrives']}")
            if culture.get("red_flags"):
                flags = culture["red_flags"]
                if isinstance(flags, list) and flags:
                    parts.append(f"RED FLAGS TO NOTE: {'; '.join(str(f) for f in flags[:4])}")

        # ── Tech & engineering ────────────────────────────────
        tech = company_intel.get("tech_and_engineering", {})
        if isinstance(tech, dict):
            stack = tech.get("tech_stack") or tech.get("jd_tech_stack") or []
            if isinstance(stack, list) and stack:
                parts.append(f"TECH STACK: {', '.join(str(s) for s in stack[:15])}")
            if tech.get("engineering_culture"):
                parts.append(f"ENGINEERING CULTURE: {tech['engineering_culture']}")
            if tech.get("engineering_values"):
                ev = tech["engineering_values"]
                if isinstance(ev, list) and ev:
                    parts.append(f"ENGINEERING VALUES: {', '.join(str(v) for v in ev[:6])}")
            gh = tech.get("github_stats", {})
            if isinstance(gh, dict) and gh.get("org_name"):
                gh_bits = [f"GitHub: {gh['org_name']}"]
                if gh.get("public_repos"):
                    gh_bits.append(f"{gh['public_repos']} repos")
                if gh.get("total_stars"):
                    gh_bits.append(f"{gh['total_stars']} stars")
                if gh.get("top_languages"):
                    gh_bits.append(f"langs: {', '.join(gh['top_languages'][:5])}")
                parts.append(" | ".join(gh_bits))

        # ── Products & market ─────────────────────────────────
        products = company_intel.get("products_and_services", {})
        if isinstance(products, dict):
            prods = products.get("main_products", [])
            if isinstance(prods, list) and prods:
                parts.append(f"PRODUCTS: {', '.join(str(p) for p in prods[:6])}")
            if products.get("competitive_advantage"):
                parts.append(f"COMPETITIVE EDGE: {products['competitive_advantage']}")

        market = company_intel.get("market_position", {})
        if isinstance(market, dict):
            comps = market.get("competitors", [])
            if isinstance(comps, list) and comps:
                parts.append(f"COMPETITORS: {', '.join(str(c) for c in comps[:6])}")
            if market.get("growth_trajectory"):
                parts.append(f"GROWTH: {market['growth_trajectory']}")

        # ── Recent developments ───────────────────────────────
        recent = company_intel.get("recent_developments", {})
        if isinstance(recent, dict):
            news = recent.get("news_highlights", [])
            if isinstance(news, list) and news:
                parts.append(f"RECENT NEWS: {'; '.join(str(n) for n in news[:4])}")
            leaders = recent.get("leadership", [])
            if isinstance(leaders, list) and leaders:
                parts.append(f"LEADERSHIP: {'; '.join(str(ldr) for ldr in leaders[:5])}")

        # ── Hiring intelligence ───────────────────────────────
        hiring = company_intel.get("hiring_intelligence", {})
        if isinstance(hiring, dict):
            must = hiring.get("must_have_skills", [])
            if isinstance(must, list) and must:
                parts.append(f"MUST-HAVE SKILLS: {', '.join(str(s) for s in must[:10])}")
            nice = hiring.get("nice_to_have_skills", [])
            if isinstance(nice, list) and nice:
                parts.append(f"NICE-TO-HAVE: {', '.join(str(s) for s in nice[:8])}")
            if hiring.get("seniority_signals"):
                parts.append(f"SENIORITY: {hiring['seniority_signals']}")
            if hiring.get("salary_range"):
                parts.append(f"SALARY RANGE: {hiring['salary_range']}")
            if hiring.get("what_impresses_interviewers"):
                parts.append(f"WHAT IMPRESSES: {hiring['what_impresses_interviewers']}")
            hidden = hiring.get("hidden_requirements", [])
            if isinstance(hidden, list) and hidden:
                parts.append(f"HIDDEN REQUIREMENTS: {'; '.join(str(h) for h in hidden[:4])}")

        # ATS platform from careers intel
        ats = company_intel.get("ats_platform") or (
            company_intel.get("careers_intel", {}).get("ats_platform")
            if isinstance(company_intel.get("careers_intel"), dict) else None
        )
        if ats:
            parts.append(f"ATS PLATFORM: {ats}")

        # ── Application strategy ──────────────────────────────
        strategy = company_intel.get("application_strategy", {})
        if isinstance(strategy, dict):
            if strategy.get("tone"):
                parts.append(f"RECOMMENDED TONE: {strategy['tone']}")
            if strategy.get("tone_reasoning"):
                parts.append(f"TONE REASONING: {strategy['tone_reasoning']}")
            kw = strategy.get("keywords_to_use", [])
            if isinstance(kw, list) and kw:
                parts.append(f"STRATEGIC KEYWORDS: {', '.join(str(k) for k in kw[:12])}")
            vals = strategy.get("values_to_emphasize", [])
            if isinstance(vals, list) and vals:
                parts.append(f"VALUES TO EMPHASIZE: {', '.join(str(v) for v in vals[:6])}")
            mention = strategy.get("things_to_mention", [])
            if isinstance(mention, list) and mention:
                parts.append(f"THINGS TO MENTION: {'; '.join(str(m) for m in mention[:5])}")
            avoid = strategy.get("things_to_avoid", [])
            if isinstance(avoid, list) and avoid:
                parts.append(f"THINGS TO AVOID: {'; '.join(str(a) for a in avoid[:4])}")
            diff = strategy.get("differentiator_opportunities", [])
            if isinstance(diff, list) and diff:
                parts.append(f"DIFFERENTIATORS: {'; '.join(str(d) for d in diff[:4])}")
            hooks = strategy.get("cover_letter_hooks", [])
            if isinstance(hooks, list) and hooks:
                hook_texts = []
                for h in hooks[:4]:
                    if isinstance(h, dict):
                        hook_texts.append(h.get("hook", str(h)))
                    else:
                        hook_texts.append(str(h))
                parts.append(f"COVER LETTER HOOKS: {'; '.join(hook_texts)}")
            prep = strategy.get("interview_prep_topics", [])
            if isinstance(prep, list) and prep:
                prep_texts = []
                for p in prep[:5]:
                    if isinstance(p, dict):
                        prep_texts.append(p.get("topic", str(p)))
                    else:
                        prep_texts.append(str(p))
                parts.append(f"INTERVIEW PREP TOPICS: {', '.join(prep_texts)}")
            qs = strategy.get("questions_to_ask", [])
            if isinstance(qs, list) and qs:
                q_texts = []
                for q in qs[:4]:
                    if isinstance(q, dict):
                        q_texts.append(q.get("question", str(q)))
                    else:
                        q_texts.append(str(q))
                parts.append(f"QUESTIONS TO ASK: {'; '.join(q_texts)}")
            if strategy.get("ats_tips"):
                tips = strategy["ats_tips"]
                if isinstance(tips, list) and tips:
                    parts.append(f"ATS TIPS: {'; '.join(str(t) for t in tips[:4])}")

        return "\n".join(parts)

    @staticmethod
    def _build_evidence_summary(pipeline_result: Any) -> Optional[Dict[str, Any]]:
        if not pipeline_result:
            return None
        ledger = getattr(pipeline_result, "evidence_ledger", None)
        citations = getattr(pipeline_result, "citations", None) or []
        if not ledger and not citations:
            return None

        tier_dist: Dict[str, int] = {}
        total_items = 0
        if isinstance(ledger, dict):
            items = ledger.get("items", [])
            total_items = len(items) if isinstance(items, list) else ledger.get("count", 0)
            for item in (items if isinstance(items, list) else []):
                tier = item.get("tier", "unknown") if isinstance(item, dict) else "unknown"
                tier_dist[tier] = tier_dist.get(tier, 0) + 1

        fabricated = sum(
            1 for c in citations
            if isinstance(c, dict) and c.get("classification") in ("fabricated", "unsupported")
        )
        unlinked = sum(
            1 for c in citations
            if isinstance(c, dict) and not c.get("evidence_ids")
        )

        return {
            "evidence_count": total_items,
            "tier_distribution": tier_dist,
            "citation_count": len(citations),
            "fabricated_count": fabricated,
            "unlinked_count": unlinked,
        }

    @staticmethod
    def _format_response(
        benchmark_data: Dict[str, Any],
        gap_analysis: Dict[str, Any],
        roadmap: Dict[str, Any],
        cv_html: str,
        cl_html: str,
        ps_html: str,
        portfolio_html: str,
        validation: Dict[str, Any],
        keywords: List[str],
        job_title: str,
        benchmark_cv_html: str = "",
        resume_html: str = "",
    ) -> Dict[str, Any]:
        """Transform pipeline outputs into the frontend response shape."""
        # Benchmark
        ideal_profile = benchmark_data.get("ideal_profile", {})
        ideal_skills = benchmark_data.get("ideal_skills", [])
        ideal_experience = benchmark_data.get("ideal_experience", [])

        summary_text = ""
        if isinstance(ideal_profile, dict):
            summary_text = ideal_profile.get("summary", "")
        if not summary_text:
            summary_text = f"AI-generated benchmark for {job_title}"

        rubric: list[str] = []
        for skill in ideal_skills[:10]:
            if isinstance(skill, dict):
                name = skill.get("name", "Unknown")
                level = skill.get("level", "required")
                importance = skill.get("importance", "important")
                rubric.append(f"{name} — {level} level ({importance})")

        benchmark = {
            "summary": summary_text,
            "keywords": keywords,
            "rubric": rubric,
            "idealProfile": ideal_profile if isinstance(ideal_profile, dict) else {},
            "idealSkills": ideal_skills,
            "idealExperience": ideal_experience,
            "scoringWeights": benchmark_data.get("scoring_weights", {}),
            "benchmarkCvHtml": benchmark_cv_html,
            "createdAt": None,
        }

        # Gaps
        compatibility = gap_analysis.get("compatibility_score", 50)
        skill_gaps = gap_analysis.get("skill_gaps", [])
        strengths_raw = gap_analysis.get("strengths", [])
        recommendations_raw = gap_analysis.get("recommendations", [])

        missing_kw = [g.get("skill", "") for g in skill_gaps if isinstance(g, dict) and g.get("skill")]
        strength_labels = [
            s.get("area", s.get("description", ""))
            for s in strengths_raw if isinstance(s, dict)
        ]
        rec_labels = [
            r.get("title", r.get("description", ""))
            for r in recommendations_raw if isinstance(r, dict)
        ]

        def _map_severity(s: str) -> str:
            return {"critical": "high", "significant": "high", "moderate": "medium",
                    "minor": "low"}.get(s, "medium")

        gaps = {
            "missingKeywords": missing_kw,
            "strengths": strength_labels,
            "recommendations": rec_labels,
            "gaps": [
                {
                    "dimension": g.get("skill", ""),
                    "gap": f"{g.get('current_level', '?')} → {g.get('required_level', 'required')}",
                    "severity": _map_severity(g.get("gap_severity", "moderate")),
                    "suggestion": g.get("recommendation", ""),
                }
                for g in skill_gaps if isinstance(g, dict)
            ],
            "summary": gap_analysis.get("executive_summary", ""),
            "compatibility": compatibility,
            "categoryScores": gap_analysis.get("category_scores", {}),
            "quickWins": gap_analysis.get("quick_wins", []),
            "interviewReadiness": gap_analysis.get("interview_readiness", {}),
        }

        # Scores
        score = compatibility if isinstance(compatibility, (int, float)) else 50
        cv_qual = validation.get("cv", {}).get("qualityScore", 0)
        match_score = min(100, max(0, int(score)))

        scores = {
            "overall": match_score,
            "compatibility": match_score,
            "match": match_score,
            "atsReadiness": min(100, match_score + 15),
            "recruiterScan": min(100, match_score + 10),
            "evidenceStrength": 0,
            "ats": min(100, max(0, int(cv_qual))) if cv_qual else 60,
            "cv": min(100, match_score + 20),
            "coverLetter": min(100, match_score + 15),
            "gaps": max(0, 100 - len(missing_kw) * 8),
            "benchmark": match_score,
        }

        scorecard = {
            "overall": scores["overall"],
            "dimensions": [
                {"name": "Match", "score": scores["match"], "feedback": f"{scores['match']}% keyword alignment"},
                {"name": "ATS Readiness", "score": scores["atsReadiness"], "feedback": f"{scores['atsReadiness']}% ATS-optimized"},
                {"name": "Recruiter Scan", "score": scores["recruiterScan"], "feedback": f"{scores['recruiterScan']}% scan-friendly"},
                {"name": "Evidence Strength", "score": scores["evidenceStrength"], "feedback": "Add evidence to boost this score"},
            ],
            "match": scores["match"],
            "atsReadiness": scores["atsReadiness"],
            "recruiterScan": scores["recruiterScan"],
            "evidenceStrength": scores["evidenceStrength"],
            "updatedAt": None,
        }

        # Documents — nested dict for backward compat (streaming SSE)
        documents = {
            "cv": cv_html,
            "coverLetter": cl_html,
            "personalStatement": ps_html,
            "portfolio": portfolio_html,
            "resume": resume_html,
        }

        return {
            "benchmark": benchmark,
            "gaps": gaps,
            "scores": scores,
            "scorecard": scorecard,
            "documents": documents,
            # Flat HTML keys — needed by _persist_generation_result_to_application
            "cvHtml": cv_html,
            "coverLetterHtml": cl_html,
            "personalStatementHtml": ps_html,
            "portfolioHtml": portfolio_html,
            "resumeHtml": resume_html,
            "validation": validation,
            "learningPlan": roadmap,
        }
