"""
Multi-Model Routing
Routes AI tasks to the optimal model based on task type.
Supports Gemini model variants and can be overridden via env var.
"""
from typing import Optional
import os
import json
import logging

logger = logging.getLogger("hirestack.model_router")

# Default model routes — can be overridden via MODEL_ROUTES env var (JSON)
# Uses Gemini model variants by default since Gemini is the active provider.
_DEFAULT_ROUTES = {
    # Analysis / structured reasoning tasks — higher-capability model
    "reasoning":          "gemini-2.5-pro",
    "research":           "gemini-2.5-pro",
    "fact_checking":      "gemini-2.5-pro",
    # Structured output / classification
    "structured_output":  "gemini-2.5-pro",
    "validation":         "gemini-2.5-pro",
    "optimization":       "gemini-2.5-pro",
    # Creative generation
    "creative":           "gemini-2.5-pro",
    "drafting":           "gemini-2.5-pro",
    "critique":           "gemini-2.5-pro",
    # General / fallback
    "general":            "gemini-2.5-pro",
}

_routes: Optional[dict] = None


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


def resolve_model(task_type: Optional[str], default: str) -> str:
    """Resolve the optimal model for a given task type."""
    if not task_type:
        return default
    routes = _load_routes()
    return routes.get(task_type, default)


def available_task_types() -> list:
    """List all configured task types."""
    return list(_load_routes().keys())
