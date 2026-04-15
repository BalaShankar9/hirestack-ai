"""   
Multi-Model Routing with Cascade Failover

Routes AI tasks to the optimal model based on task type.
Supports tiered failover: if the primary model fails or is quota-exhausted,
the router provides fallback models in priority order.

Override via MODEL_ROUTES env var (JSON) or MODEL_CASCADE env var (JSON).
"""
from __future__ import annotations

from typing import Optional, List
import os
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger("hirestack.model_router")

# ═══════════════════════════════════════════════════════════════════════
#  Default routes — primary model per task type
# ═══════════════════════════════════════════════════════════════════════

_DEFAULT_ROUTES = {
    # Analysis / structured reasoning — higher-capability model
    "reasoning":          "gemini-2.5-pro",
    "research":           "gemini-2.5-pro",
    "fact_checking":      "gemini-2.5-pro",
    # Structured output / classification
    "structured_output":  "gemini-2.5-pro",
    "validation":         "gemini-2.5-flash",
    "optimization":       "gemini-2.5-pro",
    # Creative generation — lighter model saves cost
    "creative":           "gemini-2.5-pro",
    "drafting":           "gemini-2.5-pro",
    "critique":           "gemini-2.5-flash",
    # General / fallback
    "general":            "gemini-2.5-pro",
    # ── Tiered document generation (H3 cost reduction) ──────────────
    # "quality_doc" = Pro; used for CV, Cover Letter, Personal Statement, Portfolio, 30-60-90
    "quality_doc":        "gemini-2.5-pro",
    # "fast_doc" = Flash; used for short/formulaic docs and administrative tasks
    "fast_doc":           "gemini-2.0-flash",
}

# ═══════════════════════════════════════════════════════════════════════
#  Cascade failover — ordered fallback list per task type
#  If the primary model fails, try the next one in the list.
# ═══════════════════════════════════════════════════════════════════════

_DEFAULT_CASCADE = {
    "reasoning":          ["gemini-2.5-pro", "gemini-2.5-flash"],
    "research":           ["gemini-2.5-pro", "gemini-2.5-flash"],
    "fact_checking":      ["gemini-2.5-pro", "gemini-2.5-flash"],
    "structured_output":  ["gemini-2.5-pro", "gemini-2.5-flash"],
    "validation":         ["gemini-2.5-flash", "gemini-2.5-pro"],
    "optimization":       ["gemini-2.5-pro", "gemini-2.5-flash"],
    "creative":           ["gemini-2.5-pro", "gemini-2.5-flash"],
    "drafting":           ["gemini-2.5-pro", "gemini-2.5-flash"],
    "critique":           ["gemini-2.5-flash", "gemini-2.5-pro"],
    "general":            ["gemini-2.5-pro", "gemini-2.5-flash"],
    # Tiered doc generation (H3)
    "quality_doc":        ["gemini-2.5-pro", "gemini-2.5-flash"],
    "fast_doc":           ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
}

# ═══════════════════════════════════════════════════════════════════════
#  Model health tracker — tracks failures to auto-skip degraded models
# ═══════════════════════════════════════════════════════════════════════

class _ModelHealth:
    """Lightweight per-model failure tracker with auto-recovery."""

    # After this many consecutive failures, mark unhealthy
    FAILURE_THRESHOLD = 3
    # Seconds before retrying an unhealthy model
    RECOVERY_TIMEOUT = 120.0

    def __init__(self) -> None:
        self._failures: dict[str, int] = defaultdict(int)
        self._last_failure: dict[str, float] = {}

    def record_success(self, model: str) -> None:
        self._failures[model] = 0

    def record_failure(self, model: str) -> None:
        self._failures[model] += 1
        self._last_failure[model] = time.monotonic()

    def is_healthy(self, model: str) -> bool:
        if self._failures.get(model, 0) < self.FAILURE_THRESHOLD:
            return True
        # Check if recovery timeout has elapsed
        last = self._last_failure.get(model, 0.0)
        if time.monotonic() - last >= self.RECOVERY_TIMEOUT:
            # Allow a probe attempt
            return True
        return False

    def get_status(self) -> dict:
        return {
            model: {
                "failures": count,
                "healthy": self.is_healthy(model),
            }
            for model, count in self._failures.items()
            if count > 0
        }


_model_health = _ModelHealth()

# ═══════════════════════════════════════════════════════════════════════
#  Loading & resolution
# ═══════════════════════════════════════════════════════════════════════

_routes: Optional[dict] = None
_cascade: Optional[dict] = None


def _load_routes() -> dict:
    global _routes
    if _routes is not None:
        return _routes
    _routes = dict(_DEFAULT_ROUTES)
    override = os.getenv("MODEL_ROUTES", "").strip()
    if override:
        try:
            custom = json.loads(override)
            if isinstance(custom, dict):
                _routes.update(custom)
                logger.info("model_routes_overridden: %s", list(custom.keys()))
        except json.JSONDecodeError:
            logger.warning("invalid MODEL_ROUTES env var — using defaults")
    return _routes


def _load_cascade() -> dict:
    global _cascade
    if _cascade is not None:
        return _cascade
    _cascade = dict(_DEFAULT_CASCADE)
    override = os.getenv("MODEL_CASCADE", "").strip()
    if override:
        try:
            custom = json.loads(override)
            if isinstance(custom, dict):
                _cascade.update(custom)
                logger.info("model_cascade_overridden: %s", list(custom.keys()))
        except json.JSONDecodeError:
            logger.warning("invalid MODEL_CASCADE env var — using defaults")
    return _cascade


def resolve_model(task_type: Optional[str], default: str) -> str:
    """Resolve the primary model for a given task type."""
    if not task_type:
        return default
    routes = _load_routes()
    return routes.get(task_type, default)


def resolve_cascade(task_type: Optional[str], default: str) -> List[str]:
    """Return ordered list of models to try for a task type.

    Filters out models that are currently unhealthy (unless all
    models are unhealthy, in which case return all for last-resort).
    """
    cascade = _load_cascade()
    models = list(cascade.get(task_type or "general", [default]))

    # Ensure the default is included as a final fallback
    if default not in models:
        models.append(default)

    # Prefer healthy models first
    healthy = [m for m in models if _model_health.is_healthy(m)]
    if healthy:
        return healthy
    # All unhealthy — return full list so we at least try
    logger.warning(
        "all_models_unhealthy: task_type=%s models=%s — trying all",
        task_type, models,
    )
    return models


def record_model_success(model: str) -> None:
    """Record a successful call to a model."""
    _model_health.record_success(model)


def record_model_failure(model: str) -> None:
    """Record a failed call to a model."""
    _model_health.record_failure(model)
    logger.warning("model_failure_recorded: model=%s failures=%d",
                   model, _model_health._failures.get(model, 0))


def get_model_health() -> dict:
    """Return health status for all tracked models."""
    return _model_health.get_status()


def available_task_types() -> list:
    """List all configured task types."""
    return list(_load_routes().keys())


# ═══════════════════════════════════════════════════════════════════════
#  Smart Cost Optimizer — auto-route to cheaper model when quality holds
# ═══════════════════════════════════════════════════════════════════════

# In-memory cache of quality observations per (task_type, model) pair.
# Populated by record_quality_observation() after each pipeline run.
# format: {(task_type, model): [quality_scores...]}
_quality_observations: dict[tuple[str, str], list[float]] = defaultdict(list)
_MAX_OBSERVATIONS = 50  # Rolling window per key


def record_quality_observation(
    task_type: str, model: str, quality_score: float,
) -> None:
    """Record an observed quality score for a (task_type, model) pair.

    Called after pipeline runs to build the data the cost optimizer needs.
    Also persists to DB for cross-restart durability.
    """
    key = (task_type, model)
    _quality_observations[key].append(quality_score)
    # Keep only the most recent observations
    if len(_quality_observations[key]) > _MAX_OBSERVATIONS:
        _quality_observations[key] = _quality_observations[key][-_MAX_OBSERVATIONS:]
    # Persist to DB (fire-and-forget, non-blocking)
    _persist_quality_observation(task_type, model, quality_score)


def _persist_quality_observation(
    task_type: str, model: str, quality_score: float,
) -> None:
    """Best-effort persist a quality observation to the DB."""
    try:
        from backend.app.core.database import get_supabase
        sb = get_supabase()
        sb.table("quality_observations").insert({
            "task_type": task_type,
            "model": model,
            "quality_score": quality_score,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        # Also try the direct import path (when running inside backend)
        try:
            from app.core.database import get_supabase
            sb = get_supabase()
            sb.table("quality_observations").insert({
                "task_type": task_type,
                "model": model,
                "quality_score": quality_score,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.debug("quality_observation_persist_failed: %s", e)


def hydrate_quality_observations() -> int:
    """Load recent quality observations from DB into memory.

    Call during app startup to warm the cost optimizer cache.
    Returns the number of observations loaded.
    """
    loaded = 0
    try:
        try:
            from backend.app.core.database import get_supabase
        except ImportError:
            from app.core.database import get_supabase
        sb = get_supabase()
        resp = sb.table("quality_observations") \
            .select("task_type,model,quality_score") \
            .order("observed_at", desc=True) \
            .limit(_MAX_OBSERVATIONS * 10) \
            .execute()
        if resp.data:
            for row in reversed(resp.data):  # oldest first
                key = (row["task_type"], row["model"])
                _quality_observations[key].append(row["quality_score"])
                if len(_quality_observations[key]) > _MAX_OBSERVATIONS:
                    _quality_observations[key] = _quality_observations[key][-_MAX_OBSERVATIONS:]
                loaded += 1
            logger.info("quality_observations_hydrated: %d rows loaded", loaded)
    except Exception as e:
        logger.warning("quality_observations_hydrate_failed: %s", e)
    return loaded


def resolve_cost_optimized(
    task_type: str,
    min_quality: float = 70.0,
    default: str = "gemini-2.5-pro",
) -> str:
    """Return the cheapest model that meets the minimum quality threshold.

    If we have enough data showing the cheaper model (Flash) consistently
    meets the quality bar for this task type, route there to save cost.
    Otherwise, fall back to the standard resolution.

    This is the core of the smart cost optimization loop:
    1. Pipeline runs → record_quality_observation()
    2. Next run → resolve_cost_optimized() checks if Flash is safe
    3. If Flash avg quality >= min_quality with 5+ data points → use Flash
    4. Otherwise → use Pro (safer default)

    Returns the model name to use.
    """
    # Cost ordering: Flash is cheaper than Pro
    cost_order = ["gemini-2.5-flash", "gemini-2.5-pro"]

    for model in cost_order:
        key = (task_type, model)
        scores = _quality_observations.get(key, [])
        if len(scores) < 5:
            continue  # Not enough data to be confident
        avg = sum(scores) / len(scores)
        if avg >= min_quality:
            # Ensure model is healthy before recommending
            if _model_health.is_healthy(model):
                logger.info(
                    "cost_optimizer_routing: task_type=%s model=%s avg_quality=%.1f (threshold=%.1f, n=%d)",
                    task_type, model, avg, min_quality, len(scores),
                )
                return model

    # Not enough data or no model meets threshold → use standard resolution
    return resolve_model(task_type, default)


def get_cost_optimizer_stats() -> dict:
    """Return current quality observations for operational visibility."""
    stats = {}
    for (task_type, model), scores in _quality_observations.items():
        key = f"{task_type}:{model}"
        stats[key] = {
            "observations": len(scores),
            "avg_quality": round(sum(scores) / len(scores), 1) if scores else 0,
            "min_quality": round(min(scores), 1) if scores else 0,
            "max_quality": round(max(scores), 1) if scores else 0,
        }
    return stats


def reload_routes() -> None:
    """Force reload of routes and cascade from env vars."""
    global _routes, _cascade
    _routes = None
    _cascade = None
