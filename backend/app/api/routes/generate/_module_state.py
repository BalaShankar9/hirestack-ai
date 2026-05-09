"""Pure helpers for generation-job route module (m12-pr19, TD-1 first cut).

Extracted from `app.api.routes.generate.jobs` to bring that module under
2 kLOC. These are pure utilities for module-key normalisation, default
module state shapes, preferred-style lock resolution, and the bootstrap
task shim. They have no DB dependencies; the only side-effecting helper
(``_track_bootstrap``) is a thin shim over ``bootstrap_registry``.

All names remain importable via the original ``app.api.routes.generate.jobs``
namespace through a re-export block — existing ``mock.patch("app...jobs._foo")``
call sites continue to resolve unchanged.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.task_registry import bootstrap_registry as _bootstrap_registry


def _track_bootstrap(coro, *, name: str) -> asyncio.Task:
    """Create + register a fire-and-forget bootstrap task. See ADR-0041.

    Thin shim over ``bootstrap_registry.spawn`` — kept as a named function
    so call sites stay readable and the failure-hook → metrics integration
    is exercised through the registry rather than re-implemented here."""
    return _bootstrap_registry.spawn(coro, name=name)


def _get_model_health_summary() -> Dict[str, Any]:
    """Best-effort model health for job status responses."""
    try:
        from ai_engine.api import get_model_health
        return get_model_health()
    except Exception:
        return {}


_DEFAULT_REQUESTED_MODULES = [
    "benchmark",
    "gaps",
    "learningPlan",
    "cv",
    "resume",
    "coverLetter",
    "personalStatement",
    "portfolio",
    "scorecard",
]

# Bidirectional key mapping: snake_case ↔ camelCase
_SNAKE_TO_CAMEL = {
    "cover_letter": "coverLetter",
    "personal_statement": "personalStatement",
    "learning_plan": "learningPlan",
    "gap_analysis": "gaps",
}
_CAMEL_TO_SNAKE = {v: k for k, v in _SNAKE_TO_CAMEL.items()}
# Keys that are identical in both formats
_IDENTITY_KEYS = {"benchmark", "cv", "resume", "portfolio", "scorecard", "gaps"}


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _apply_preferred_lock(
    variants: List[Dict[str, Any]],
    scores: Optional[Dict[str, Any]],
    document: str,
) -> str:
    """Phase D.5: re-lock the variant whose style has the highest
    learned outcome score, then return its content for canonical use.

    Returns the (possibly unchanged) canonical content.  No-op when
    scores are missing, when the preferred variant is already locked,
    or when the preferred variant isn't present in the list.
    """
    if not variants:
        return ""
    try:
        from ai_engine.agents.style_outcome_scorer import preferred_style
    except Exception:
        return next(
            (v.get("content", "") for v in variants if v.get("locked")),
            variants[0].get("content", ""),
        )
    target = preferred_style(scores, document, fallback="")
    if not target:
        return next(
            (v.get("content", "") for v in variants if v.get("locked")),
            variants[0].get("content", ""),
        )
    has_target = any(
        isinstance(v, dict) and v.get("variant") == target and (v.get("content") or "").strip()
        for v in variants
    )
    if not has_target:
        return next(
            (v.get("content", "") for v in variants if v.get("locked")),
            variants[0].get("content", ""),
        )
    new_canonical = ""
    for v in variants:
        if not isinstance(v, dict):
            continue
        is_target = v.get("variant") == target
        v["locked"] = bool(is_target)
        if is_target:
            new_canonical = v.get("content", "") or ""
    return new_canonical


def _default_module_states() -> Dict[str, Dict[str, Any]]:
    return {
        "benchmark": {"state": "idle"},
        "gaps": {"state": "idle"},
        "learningPlan": {"state": "idle"},
        "cv": {"state": "idle"},
        "resume": {"state": "idle"},
        "coverLetter": {"state": "idle"},
        "personalStatement": {"state": "idle"},
        "portfolio": {"state": "idle"},
        "scorecard": {"state": "idle"},
    }


def _merge_module_states(existing_modules: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    modules: Dict[str, Any] = _default_module_states()
    if isinstance(existing_modules, dict):
        modules.update(existing_modules)
    return modules


def _normalize_requested_modules(requested_modules: Optional[List[str]]) -> List[str]:
    """Normalize module keys to camelCase (internal canonical form).
    Accepts both snake_case (from /jobs endpoint) and camelCase (from frontend).
    """
    if not requested_modules:
        return list(_DEFAULT_REQUESTED_MODULES)

    normalized = []
    seen = set()
    for mod in requested_modules:
        # Convert snake_case → camelCase if needed
        key = _SNAKE_TO_CAMEL.get(mod, mod)
        if key in seen:
            continue
        # Accept if it's a known default module
        if key in _DEFAULT_REQUESTED_MODULES:
            normalized.append(key)
            seen.add(key)

    return normalized or list(_DEFAULT_REQUESTED_MODULES)


def _module_has_content(application_row: Dict[str, Any], module_key: str) -> bool:
    if module_key == "benchmark":
        return bool(application_row.get("benchmark"))
    if module_key == "gaps":
        return bool(application_row.get("gaps"))
    if module_key == "learningPlan":
        return bool(application_row.get("learning_plan"))
    if module_key == "cv":
        return bool(str(application_row.get("cv_html") or "").strip())
    if module_key == "resume":
        return bool(str(application_row.get("resume_html") or "").strip())
    if module_key == "coverLetter":
        return bool(str(application_row.get("cover_letter_html") or "").strip())
    if module_key == "personalStatement":
        return bool(str(application_row.get("personal_statement_html") or "").strip())
    if module_key == "portfolio":
        return bool(str(application_row.get("portfolio_html") or "").strip())
    if module_key == "scorecard":
        return bool(application_row.get("scorecard") or application_row.get("scores"))
    return False


__all__ = [
    "_track_bootstrap",
    "_get_model_health_summary",
    "_DEFAULT_REQUESTED_MODULES",
    "_SNAKE_TO_CAMEL",
    "_CAMEL_TO_SNAKE",
    "_IDENTITY_KEYS",
    "_now_ms",
    "_apply_preferred_lock",
    "_default_module_states",
    "_merge_module_states",
    "_normalize_requested_modules",
    "_module_has_content",
    "_bootstrap_registry",
]
