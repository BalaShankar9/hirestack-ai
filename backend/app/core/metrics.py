"""
Pipeline metrics — lightweight observability for AI pipeline execution.

Tracks stage durations, token consumption, error rates, and circuit breaker
state. Emits metrics via structured logging (structlog JSON) so they can be
picked up by any log aggregator without adding external dependencies.

Future: expose via /metrics endpoint (Prometheus-compatible) when needed.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("hirestack.metrics")


# ═══════════════════════════════════════════════════════════════════════
#  Stage timing
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class StageMetric:
    """Timing and token data for a single pipeline stage execution."""
    pipeline_name: str
    stage_name: str
    started_at: float = 0.0
    finished_at: float = 0.0
    success: bool = True
    error_class: str = ""
    tokens_input: int = 0
    tokens_output: int = 0

    @property
    def duration_ms(self) -> int:
        if self.finished_at and self.started_at:
            return int((self.finished_at - self.started_at) * 1000)
        return 0


@dataclass
class PipelineRunMetric:
    """Aggregated metrics for a complete pipeline execution."""
    pipeline_name: str
    user_id: str = ""
    mode: str = ""               # sync, stream, job
    started_at: float = 0.0
    finished_at: float = 0.0
    success: bool = True
    error_class: str = ""
    stages: List[StageMetric] = field(default_factory=list)
    total_tokens_input: int = 0
    total_tokens_output: int = 0

    @property
    def duration_ms(self) -> int:
        if self.finished_at and self.started_at:
            return int((self.finished_at - self.started_at) * 1000)
        return 0

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_input + self.total_tokens_output


# ═══════════════════════════════════════════════════════════════════════
#  Metrics collector (process-global singleton)
# ═══════════════════════════════════════════════════════════════════════

class MetricsCollector:
    """Collects and reports pipeline execution metrics.

    Maintains a rolling window of recent runs per pipeline, computes
    percentiles, and emits structured log events for each completed run.
    """

    _instance: Optional["MetricsCollector"] = None

    def __init__(self, window_size: int = 100) -> None:
        self._window_size = window_size
        self._runs: Dict[str, List[PipelineRunMetric]] = defaultdict(list)
        self._stage_history: Dict[str, List[StageMetric]] = defaultdict(list)
        self._active_jobs: int = 0
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._breaker_transitions: List[Dict[str, Any]] = []
        self._model_failovers: int = 0
        self._model_failover_log: List[Dict[str, Any]] = []
        # Per-doc-type rolling quality scores (W2 Intelligence & quality)
        self._doc_quality_history: Dict[str, List[int]] = defaultdict(list)
        # ── W3 Observability: per-LLM-call counters ───────────────
        # Total calls + tokens per (model, task_type) since process start.
        # Cost is estimated client-side in ai_engine.client._DailyUsageTracker;
        # we only count calls and tokens here so /metrics can attribute per
        # task_type. Keeping these as counters means they monotonically
        # increase, which is what Prometheus expects.
        self._llm_calls: Dict[str, int] = defaultdict(int)         # key = "model|task_type"
        self._llm_tokens_in: Dict[str, int] = defaultdict(int)
        self._llm_tokens_out: Dict[str, int] = defaultdict(int)

    @classmethod
    def get(cls) -> "MetricsCollector":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    # ── Recording ─────────────────────────────────────────────────────

    def record_run(self, metric: PipelineRunMetric) -> None:
        """Record a completed pipeline run."""
        runs = self._runs[metric.pipeline_name]
        runs.append(metric)
        if len(runs) > self._window_size:
            self._runs[metric.pipeline_name] = runs[-self._window_size:]

        if not metric.success and metric.error_class:
            self._error_counts[metric.error_class] += 1

        # Emit structured log
        logger.info(
            "pipeline.metrics.run_complete",
            pipeline=metric.pipeline_name,
            mode=metric.mode,
            duration_ms=metric.duration_ms,
            success=metric.success,
            error_class=metric.error_class or None,
            tokens_input=metric.total_tokens_input,
            tokens_output=metric.total_tokens_output,
            stages_count=len(metric.stages),
            user_id=metric.user_id,
        )

    def record_stage(self, stage: StageMetric) -> None:
        """Record a single stage execution."""
        history = self._stage_history[stage.stage_name]
        history.append(stage)
        if len(history) > self._window_size:
            self._stage_history[stage.stage_name] = history[-self._window_size :]

        logger.info(
            "pipeline.metrics.stage_complete",
            pipeline=stage.pipeline_name,
            stage=stage.stage_name,
            duration_ms=stage.duration_ms,
            success=stage.success,
            error_class=stage.error_class or None,
            tokens_input=stage.tokens_input,
            tokens_output=stage.tokens_output,
        )

    def record_breaker_transition(self, breaker_name: str, from_state: str, to_state: str) -> None:
        """Record a circuit breaker state transition."""
        entry = {
            "breaker": breaker_name,
            "from": from_state,
            "to": to_state,
            "timestamp": time.time(),
        }
        self._breaker_transitions.append(entry)
        if len(self._breaker_transitions) > 200:
            self._breaker_transitions = self._breaker_transitions[-100:]

        logger.warning(
            "pipeline.metrics.breaker_transition",
            breaker=breaker_name,
            from_state=from_state,
            to_state=to_state,
        )

    def job_started(self) -> None:
        self._active_jobs += 1

    def job_finished(self) -> None:
        self._active_jobs = max(0, self._active_jobs - 1)

    def record_model_failover(self, failed_model: str, next_model: str, error: str) -> None:
        """Record a model cascade failover event."""
        self._model_failovers += 1
        entry = {
            "failed_model": failed_model,
            "next_model": next_model,
            "error": error[:200],
            "timestamp": time.time(),
        }
        self._model_failover_log.append(entry)
        if len(self._model_failover_log) > 100:
            self._model_failover_log = self._model_failover_log[-50:]
        logger.warning(
            "pipeline.metrics.model_failover",
            failed_model=failed_model,
            next_model=next_model,
            error=error[:200],
        )

    # ── Querying ──────────────────────────────────────────────────────

    def get_stage_stats(self) -> Dict[str, Any]:
        """Return per-stage latency percentiles from the in-process rolling window."""
        result: Dict[str, Any] = {}
        for stage_name, history in self._stage_history.items():
            if not history:
                continue
            durations = sorted(m.duration_ms for m in history)
            n = len(durations)
            success_count = sum(1 for m in history if m.success)
            result[stage_name] = {
                "count": n,
                "success_rate": round(success_count / n, 3),
                "p50_ms": durations[n // 2],
                "p95_ms": durations[int(n * 0.95)] if n >= 20 else durations[-1],
                "last_ms": history[-1].duration_ms,
            }
        return result

    def record_doc_quality(self, doc_type: str, score: int) -> None:
        """Record a deterministic quality score (0-100) for a document type.

        Maintains a rolling window of the last `window_size` scores per
        doc type so /metrics can surface mean/p50/p95.
        """
        try:
            s = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            return
        bucket = self._doc_quality_history[doc_type]
        bucket.append(s)
        if len(bucket) > self._window_size:
            self._doc_quality_history[doc_type] = bucket[-self._window_size:]

    def get_doc_quality_stats(self) -> Dict[str, Dict[str, Any]]:
        """Return per-doc-type quality stats from the rolling window."""
        out: Dict[str, Dict[str, Any]] = {}
        for doc_type, scores in self._doc_quality_history.items():
            if not scores:
                continue
            ordered = sorted(scores)
            n = len(ordered)
            out[doc_type] = {
                "count": n,
                "mean": round(sum(ordered) / n, 1),
                "p50": ordered[n // 2],
                "p95": ordered[int(n * 0.95)] if n >= 20 else ordered[-1],
                "min": ordered[0],
                "last": scores[-1],
            }
        return out

    def record_llm_call(
        self, model: str, task_type: str,
        input_tokens: int, output_tokens: int,
    ) -> None:
        """Increment per-(model, task_type) call + token counters (W3)."""
        try:
            in_t = max(0, int(input_tokens))
            out_t = max(0, int(output_tokens))
        except (TypeError, ValueError):
            return
        key = f"{model or 'unknown'}|{task_type or 'unknown'}"
        self._llm_calls[key] += 1
        self._llm_tokens_in[key] += in_t
        self._llm_tokens_out[key] += out_t

    def get_llm_call_stats(self) -> Dict[str, Dict[str, Any]]:
        """Return per-(model, task_type) call/token counters for Prometheus."""
        out: Dict[str, Dict[str, Any]] = {}
        for key, calls in self._llm_calls.items():
            model, _, task_type = key.partition("|")
            out[key] = {
                "model": model,
                "task_type": task_type or "unknown",
                "calls": calls,
                "tokens_in": self._llm_tokens_in.get(key, 0),
                "tokens_out": self._llm_tokens_out.get(key, 0),
            }
        return out

    def get_stats(self, pipeline_name: Optional[str] = None) -> Dict[str, Any]:
        """Get aggregated stats for a pipeline or all pipelines."""
        if pipeline_name:
            runs = self._runs.get(pipeline_name, [])
            return self._compute_stats(pipeline_name, runs)

        all_stats = {}
        for name, runs in self._runs.items():
            all_stats[name] = self._compute_stats(name, runs)

        return {
            "pipelines": all_stats,
            "active_jobs": self._active_jobs,
            "error_counts": dict(self._error_counts),
            "recent_breaker_transitions": self._breaker_transitions[-10:],
            "model_failovers_total": self._model_failovers,
            "recent_model_failovers": self._model_failover_log[-10:],
        }

    def _compute_stats(self, name: str, runs: List[PipelineRunMetric]) -> Dict[str, Any]:
        if not runs:
            return {"count": 0}

        durations = sorted(r.duration_ms for r in runs)
        successes = sum(1 for r in runs if r.success)
        tokens = sum(r.total_tokens for r in runs)

        return {
            "count": len(runs),
            "success_rate": round(successes / len(runs), 3),
            "duration_p50_ms": durations[len(durations) // 2],
            "duration_p95_ms": durations[int(len(durations) * 0.95)] if len(durations) >= 20 else durations[-1],
            "duration_p99_ms": durations[int(len(durations) * 0.99)] if len(durations) >= 100 else durations[-1],
            "total_tokens": tokens,
            "avg_tokens_per_run": tokens // len(runs) if runs else 0,
        }
