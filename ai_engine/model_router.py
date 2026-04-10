"""
Multi-Model Routing for Ollama
Routes AI tasks to the optimal model based on task type.
"""
from typing import Optional
import os
import json
import logging

logger = logging.getLogger("hirestack.model_router")

# Default model routes — can be overridden via OLLAMA_MODEL_ROUTES env var (JSON)
_DEFAULT_ROUTES = {
    "reasoning": "deepseek-v3.1:671b-cloud",
    "code_analysis": "qwen3-coder:480b-cloud",
    "structured_output": "minimax-m2:cloud",
    "creative": "minimax-m2:cloud",
    "general": "qwen3:4b",
}

_routes: Optional[dict] = None


def _load_routes() -> dict:
    global _routes
    if _routes is not None:
        return _routes
    _routes = dict(_DEFAULT_ROUTES)
    override = os.getenv("OLLAMA_MODEL_ROUTES", "").strip()
    if override:
        try:
            custom = json.loads(override)
            if isinstance(custom, dict):
                _routes.update(custom)
                logger.info("model_routes_overridden: %s", list(custom.keys()))
        except json.JSONDecodeError:
            logger.warning("invalid_OLLAMA_MODEL_ROUTES env var — using defaults")
    return _routes


def resolve_model(task_type: Optional[str], default: str) -> str:
    """Resolve the optimal Ollama model for a given task type."""
    if not task_type:
        return default
    routes = _load_routes()
    return routes.get(task_type, default)


def available_task_types() -> list:
    """List all configured task types."""
    return list(_load_routes().keys())
