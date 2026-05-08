"""ai_engine.api — single import surface for downstream services (PR m4-pr11).

This module exists so that `backend/` (and any other consumer) can rely on
a stable, narrow API instead of reaching into deep `ai_engine.*` paths.
That keeps refactor blast-radius bounded and lets us replace internals
(e.g. swap model router, rewrite chains) without touching call sites.

The published surface is intentionally small. Add to it deliberately —
each new export is a new public contract.

Names mirror the contract laid out in BUILD_PLAN_M1_M6.md PR-11. Some
spec'd names (run_aim_pipeline, plan, critique, GenerationRequest,
GenerationResult) are not yet implemented in `ai_engine/` — they will
land in later PRs and slot in here without changing the import surface
for callers. Today we expose what exists.
"""
from __future__ import annotations

# --- Model routing --------------------------------------------------------

from ai_engine.model_router import (
    available_task_types,
    get_model_health,
    hydrate_quality_observations,
    record_model_failure,
    record_model_success,
    record_quality_observation,
    resolve_cascade,
    resolve_model,
)

# Stable alias — spec calls this `route_model`. Keep `resolve_model` as the
# implementation name; downstream code should import `route_model` from here.
route_model = resolve_model

# --- Event emission -------------------------------------------------------

from ai_engine.agent_events import (
    EventEmitter,
    emit_cache_hit,
    emit_evidence_added,
    emit_phase,
    emit_policy_decision,
    emit_tool_call,
    emit_tool_result,
    reset_event_emitter,
    set_event_emitter,
)

# `emit` per spec — generic dispatcher, currently surfaced as emit_phase
# (the most general lifecycle event helper).
emit = emit_phase

# --- AI client (legacy direct-import surface; will narrow further later) --

from ai_engine.client import AIClient, get_ai_client

# --- Cache surface (m11-pr39 — replaces direct ai_engine.cache imports) ---
#
# Lets backend callers use the JD-analysis cache without reaching into
# ai_engine.cache directly. Removes one import-linter carve-out.

from ai_engine.cache import JDAnalysisCache, get_jd_cache

__all__ = [
    # model routing
    "available_task_types",
    "get_model_health",
    "hydrate_quality_observations",
    "record_model_failure",
    "record_model_success",
    "record_quality_observation",
    "resolve_cascade",
    "resolve_model",
    "route_model",
    # event emission
    "EventEmitter",
    "emit",
    "emit_cache_hit",
    "emit_evidence_added",
    "emit_phase",
    "emit_policy_decision",
    "emit_tool_call",
    "emit_tool_result",
    "reset_event_emitter",
    "set_event_emitter",
    # client
    "AIClient",
    "get_ai_client",
    # cache (m11-pr39)
    "JDAnalysisCache",
    "get_jd_cache",
]
