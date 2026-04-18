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

        events_queue: list[PipelineEvent] = []

        async def stage_callback(event: dict) -> None:
            pe = PipelineEvent(
                event_type="agent_status",
                pipeline_name=event.get("pipeline_name", ""),
                stage=event.get("stage", ""),
                status=event.get("status", ""),
                latency_ms=event.get("latency_ms", 0),
                message=event.get("message", ""),
            )
            events_queue.append(pe)

        async def flush_events() -> None:
            for ev in events_queue:
                await self.sink.emit(ev)
            events_queue.clear()

        # ── Phase 0: Company Intelligence (best-effort, parallel-ready) ─
        self._begin_phase("recon")
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
        try:
            from ai_engine.chains.company_intel import CompanyIntelChain
            intel_chain = CompanyIntelChain(ai)
            intel_coro = intel_chain.gather_intel(
                company=company,
                job_title=job_title,
                jd_text=jd_text,
                on_event=_on_recon_event,
            )
            intel_task = asyncio.create_task(intel_coro)
            company_intel = await asyncio.wait_for(
                asyncio.shield(intel_task),
                timeout=30,
            )
            logger.info("pipeline_runtime.intel_done",
                        confidence=company_intel.get("confidence", "unknown"))
        except asyncio.TimeoutError:
            # Cancel cleanly to avoid leaked coroutines
            if intel_task and not intel_task.done():
                intel_task.cancel()
                try:
                    await intel_task
                except (asyncio.CancelledError, Exception):
                    pass
            logger.warning("pipeline_runtime.intel_timeout")
            await self.sink.emit(PipelineEvent(
                event_type="detail",
                phase="recon",
                message="Recon timed out after 30s; continuing with JD-based intel.",
                status="warning",
                data={"agent": "recon", "source": "analysis"},
            ))
            self._failed_modules.append({"module": "company_intel", "error": "intel_timeout"})
        except Exception as intel_err:
            logger.warning("pipeline_runtime.intel_skipped", error=str(intel_err)[:200])
            await self.sink.emit(PipelineEvent(
                event_type="detail",
                phase="recon",
                message="Recon external intel failed; continuing with available inputs.",
                status="warning",
                data={"agent": "recon", "source": "analysis", "metadata": {"error": str(intel_err)[:200]}},
            ))
            self._failed_modules.append({"module": "company_intel", "error": str(intel_err)[:200]})
        finally:
            self._finish_phase("recon")

        # ── Phase 1: Resume parse ─────────────────────────────────────
        self._begin_phase("atlas")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=8,
            message="Agent: parsing resume…",
        ))

        user_profile: dict = {}
        if resume_text.strip():
            try:
                pipe = resume_parse_pipeline(
                    ai_client=ai, on_stage_update=stage_callback,
                    db=sb, tables=tables, user_id=user_id,
                )
                parse_result: PipelineResult = await pipe.execute({"user_id": user_id, "resume_text": resume_text})
                await flush_events()
                user_profile = parse_result.content if isinstance(parse_result.content, dict) else {}
            except Exception as rp_err:
                logger.warning("pipeline_runtime.resume_parse_failed", error=str(rp_err)[:200])
                self._failed_modules.append({"module": "resume_parse", "error": str(rp_err)[:200]})

        # ── Phase 1b: Benchmark ───────────────────────────────────────
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="atlas", progress=15,
            message="Agent: building candidate benchmark…",
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
            await flush_events()
            benchmark_data = bench_result.content if isinstance(bench_result.content, dict) else {}
        except Exception as bench_err:
            logger.warning("pipeline_runtime.benchmark_failed", error=str(bench_err)[:200])
            self._failed_modules.append({"module": "benchmark", "error": str(bench_err)[:200]})
            await flush_events()

        ideal_skills = benchmark_data.get("ideal_skills", [])
        keywords = [s.get("name", "") for s in ideal_skills if isinstance(s, dict) and s.get("name")]
        if not keywords:
            keywords = self._extract_keywords_from_jd(jd_text)

        # Start independent benchmark artifacts early so they overlap with gap analysis.
        benchmark_cv_html = ""
        benchmark_cv_task: Optional[asyncio.Task[str]] = None
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
        except Exception as bcv_err:
            logger.warning("pipeline_runtime.benchmark_cv_task_failed", error=str(bcv_err)[:200])

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
        self._finish_phase("atlas")

        # ── Phase 2: Gap analysis ─────────────────────────────────────
        self._begin_phase("cipher")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=30,
            message="Agent: analyzing skill gaps…",
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
            await flush_events()
            gap_analysis = gap_result.content if isinstance(gap_result.content, dict) else {}
        except Exception as gap_err:
            logger.warning("pipeline_runtime.gap_analysis_failed", error=str(gap_err)[:200])
            self._failed_modules.append({"module": "gap_analysis", "error": str(gap_err)[:200]})
            await flush_events()

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=45,
            message="Gap analysis complete ✓",
        ))

        # ── Evidence graph canonicalization + plan artifact ───────────
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

        # ── Phase 2b: Document Pack Planning ──────────────────────────
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="cipher", progress=48,
            message="Planning optimal document pack…",
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

        self._finish_phase("cipher")

        # ── Phase 3: Core docs + Roadmap (parallel) ──────────────────
        self._begin_phase("quill")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="quill", progress=50,
            message="Agents: generating CV, cover letter & learning plan…",
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

        cv_result_raw, cl_result_raw, roadmap = await asyncio.gather(
            cv_pipe.execute(doc_context),
            cl_pipe.execute(doc_context),
            consultant.generate_roadmap(gap_analysis, user_profile, job_title, company),
            return_exceptions=True,
        )
        await flush_events()

        cv_result: PipelineResult | None = None
        cl_result: PipelineResult | None = None

        if isinstance(cv_result_raw, Exception):
            logger.error("pipeline_runtime.cv_failed", error=str(cv_result_raw))
            self._failed_modules.append({"module": "cv", "error": str(cv_result_raw)[:200]})
            cv_html = ""
        else:
            cv_result = cv_result_raw
            cv_html = self._extract_pipeline_html(cv_result.content)

        if isinstance(cl_result_raw, Exception):
            logger.error("pipeline_runtime.cl_failed", error=str(cl_result_raw))
            self._failed_modules.append({"module": "cover_letter", "error": str(cl_result_raw)[:200]})
            cl_html = ""
        else:
            cl_result = cl_result_raw
            cl_html = self._extract_pipeline_html(cl_result.content)

        if isinstance(roadmap, Exception):
            logger.error("pipeline_runtime.roadmap_failed", error=str(roadmap))
            self._failed_modules.append({"module": "roadmap", "error": str(roadmap)[:200]})
            roadmap = {}

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="quill", progress=70,
            message="CV, cover letter & learning plan ready ✓",
        ))
        self._finish_phase("quill")

        # ── Phase 4: Personal statement + Portfolio (parallel) ────────
        self._begin_phase("forge")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="forge", progress=75,
            message="Agents: building personal statement & portfolio…",
        ))

        ps_pipe = personal_statement_pipeline(
            ai_client=ai, on_stage_update=stage_callback,
            db=sb, tables=tables, user_id=user_id,
        )
        pf_pipe = portfolio_pipeline(
            ai_client=ai, on_stage_update=stage_callback,
            db=sb, tables=tables, user_id=user_id,
        )

        ps_raw, pf_raw = await asyncio.gather(
            ps_pipe.execute(doc_context),
            pf_pipe.execute(doc_context),
            return_exceptions=True,
        )
        await flush_events()

        ps_html = ""
        portfolio_html = ""
        if isinstance(ps_raw, Exception):
            logger.error("pipeline_runtime.ps_failed", error=str(ps_raw))
            self._failed_modules.append({"module": "personal_statement", "error": str(ps_raw)[:200]})
        else:
            ps_html = self._extract_pipeline_html(ps_raw.content)

        if isinstance(pf_raw, Exception):
            logger.error("pipeline_runtime.portfolio_failed", error=str(pf_raw))
            self._failed_modules.append({"module": "portfolio", "error": str(pf_raw)[:200]})
        else:
            portfolio_html = self._extract_pipeline_html(pf_raw.content)

        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="forge", progress=82,
            message="Personal statement & portfolio ready ✓",
        ))

        # ── Phase 4b: Extra required docs via AdaptiveDocumentChain ───
        generated_docs: Dict[str, str] = {}
        benchmark_documents: Dict[str, str] = {}

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
        self._finish_phase("forge")

        # ── Phase 5: Validation ───────────────────────────────────────
        self._begin_phase("sentinel")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="sentinel", progress=92,
            message="Validating documents…",
        ))

        cv_quality = cv_result.quality_scores if cv_result else {}
        cl_quality = cl_result.quality_scores if cl_result else {}
        cv_fact_check = cv_result.fact_check_report if cv_result else {}

        validation = {
            "cv": {
                "valid": bool(cv_html),
                "qualityScore": self._quality_score(cv_quality),
                "agent_powered": True,
            }
        }
        self._finish_phase("sentinel")

        # ── Phase 6: Format response ─────────────────────────────────
        self._begin_phase("nova")
        await self.sink.emit(PipelineEvent(
            event_type="progress", phase="nova", progress=98,
            message="Packaging your application…",
        ))

        from app.core.sanitize import sanitize_html

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
        )

        # ── Attach dynamic doc-pack fields ────────────────────────────
        response["discoveredDocuments"] = discovered_documents
        response["generatedDocuments"] = {
            k: sanitize_html(v) for k, v in generated_docs.items() if v
        }
        response["benchmarkDocuments"] = {
            k: (sanitize_html(v) if isinstance(v, str) else v)
            for k, v in benchmark_documents.items()
        }
        # Also add core benchmark CV to benchmark docs
        if benchmark_cv_html:
            response["benchmarkDocuments"]["cv"] = sanitize_html(benchmark_cv_html)

        response["documentStrategy"] = (
            doc_pack_plan.strategy if doc_pack_plan else ""
        )
        response["docPackPlan"] = (
            doc_pack_plan.to_dict() if doc_pack_plan else None
        )
        if company_intel:
            response["companyIntel"] = company_intel

        # Agent metadata
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

        # ── Persist to document_library table ─────────────────────────
        self._begin_phase("persist")
        await self._persist_to_document_library(
            sb=sb, tables=tables, user_id=user_id,
            cv_html=sanitize_html(cv_html) if cv_html else "",
            cl_html=sanitize_html(cl_html) if cl_html else "",
            ps_html=sanitize_html(ps_html) if ps_html else "",
            portfolio_html=sanitize_html(portfolio_html) if portfolio_html else "",
            benchmark_cv_html=sanitize_html(benchmark_cv_html) if benchmark_cv_html else "",
            generated_docs={k: sanitize_html(v) for k, v in generated_docs.items() if v},
            benchmark_docs={
                k: (sanitize_html(v) if isinstance(v, str) else v)
                for k, v in benchmark_documents.items()
            },
        )
        self._finish_phase("persist")

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
        try:
            benchmark_cv_html = await benchmark_chain.create_benchmark_cv_html(
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
        )
        return response

    # ── Helpers ────────────────────────────────────────────────────────

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

            # Build all create_document coroutines for concurrent execution
            coros = []

            # Tailored core documents
            tailored_count = 0
            for doc_spec in [
                {"doc_type": "cv",                 "label": "Tailored CV",                 "html": cv_html},
                {"doc_type": "cover_letter",        "label": "Tailored Cover Letter",        "html": cl_html},
                {"doc_type": "personal_statement",  "label": "Tailored Personal Statement",  "html": ps_html},
                {"doc_type": "portfolio",           "label": "Tailored Portfolio",           "html": portfolio_html},
            ]:
                if doc_spec["html"]:
                    tailored_count += 1
                    coros.append(service.create_document(
                        user_id=user_id,
                        doc_type=doc_spec["doc_type"],
                        doc_category="tailored",
                        label=doc_spec["label"],
                        application_id=application_id,
                        html_content=doc_spec["html"],
                        status="ready",
                        source="planner",
                    ))

            # Extra generated documents (tailored)
            for key, html in generated_docs.items():
                if html:
                    tailored_count += 1
                    coros.append(service.create_document(
                        user_id=user_id,
                        doc_type=key,
                        doc_category="tailored",
                        label=key.replace("_", " ").title(),
                        application_id=application_id,
                        html_content=html,
                        status="ready",
                        source="planner",
                    ))

            # Benchmark documents
            benchmark_count = 0
            if benchmark_cv_html:
                benchmark_count += 1
                coros.append(service.create_document(
                    user_id=user_id,
                    doc_type="cv",
                    doc_category="benchmark",
                    label="Benchmark CV",
                    application_id=application_id,
                    html_content=benchmark_cv_html,
                    status="ready",
                    source="planner",
                ))
            for key, html in benchmark_docs.items():
                if html and isinstance(html, str):
                    benchmark_count += 1
                    coros.append(service.create_document(
                        user_id=user_id,
                        doc_type=key,
                        doc_category="benchmark",
                        label=f"Benchmark {key.replace('_', ' ').title()}",
                        application_id=application_id,
                        html_content=html,
                        status="ready",
                        source="planner",
                    ))

            # Fan-out: all inserts run concurrently
            results = await asyncio.gather(*coros, return_exceptions=True)
            failures = sum(1 for r in results if isinstance(r, Exception))
            if failures:
                logger.warning(
                    "pipeline_runtime.document_library_partial_failure",
                    total=len(coros),
                    failures=failures,
                )

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
                parts.append(f"LEADERSHIP: {'; '.join(str(l) for l in leaders[:5])}")

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
            "validation": validation,
            "learningPlan": roadmap,
        }
