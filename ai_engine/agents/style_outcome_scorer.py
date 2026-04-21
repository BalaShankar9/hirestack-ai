"""Phase C.3 — outcome → style score feedback loop.

When a user records an application outcome (callback / offer), we want
the system to LEARN which CV/PS variant style converts best for them.
The user already locked one variant in via the D.2/D.3 lock endpoints,
so the locked variant is the one that actually went out the door.

This module:
1. Reads `cv_versions` and `ps_versions` from the application row
2. Finds the locked variant for each
3. Updates per-user, per-document style scores in `agent_memory`
4. Higher scores = preferred style for future runs

Score weights (additive):
    callback  → +1.0
    offer     → +3.0
    rejected  → -0.5
    ghosted   →  0.0   (no signal)

Memory shape (stored under key=`style_outcome_scores`):
    {
        "cv":  {"concise": 4.0, "narrative": 1.0, "_runs": 7},
        "ps":  {"concise": 1.0, "narrative": 3.0, "_runs": 4},
        "updated_at": "2026-04-21T..."
    }

Cold-start safe: if no locked variant exists, no scores are written.
Idempotent: repeated feedback on the same outcome stacks (intentional —
the user explicitly re-confirmed the result).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.style_outcome_scorer")

OUTCOME_WEIGHTS: Dict[str, float] = {
    "callback": 1.0,
    "offer": 3.0,
    "rejected": -0.5,
    "ghosted": 0.0,
}

MEMORY_AGENT_TYPE: str = "style_outcomes"
MEMORY_KEY: str = "style_outcome_scores"


def _find_locked_variant(variants: Any) -> Optional[str]:
    """Return the variant key of the locked entry, or None."""
    if not isinstance(variants, list):
        return None
    for v in variants:
        if isinstance(v, dict) and v.get("locked") is True:
            key = v.get("variant")
            if isinstance(key, str) and key:
                return key
    return None


async def apply_outcome_to_style_scores(
    *,
    memory: Any,  # AgentMemory
    sb: Any,  # supabase client
    tables: Dict[str, str],
    user_id: str,
    application_id: str,
    outcome: str,
) -> Optional[Dict[str, Any]]:
    """Bump style scores for the locked CV/PS variants of an application.

    Returns the updated scores dict on success, None on no-op (no locked
    variants, unknown outcome, or memory write failure).  Never raises —
    feedback flows shouldn't be brittle to scoring layer failures.
    """
    weight = OUTCOME_WEIGHTS.get(outcome)
    if weight is None or weight == 0.0:
        # No signal worth recording.
        return None
    if not memory or not user_id or user_id == "unknown":
        return None

    # Fetch the application's variant arrays.
    try:
        app_resp = await asyncio.to_thread(
            lambda: sb.table(tables["applications"])
            .select("cv_variants,ps_variants")
            .eq("id", application_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.debug("style_outcome.fetch_failed", error=str(exc)[:160])
        return None
    if not app_resp or not app_resp.data:
        return None

    cv_locked = _find_locked_variant(app_resp.data.get("cv_variants"))
    ps_locked = _find_locked_variant(app_resp.data.get("ps_variants"))
    if not cv_locked and not ps_locked:
        return None

    # Recall existing scores.
    existing: Dict[str, Any] = {}
    try:
        rows = await memory.arecall(user_id, MEMORY_AGENT_TYPE, limit=5)
        for r in rows or []:
            if r.get("memory_key") == MEMORY_KEY:
                val = r.get("memory_value")
                if isinstance(val, dict):
                    existing = val
                    break
    except Exception as exc:
        logger.debug("style_outcome.recall_failed", error=str(exc)[:160])
        existing = {}

    cv_scores: Dict[str, float] = dict(existing.get("cv") or {})
    ps_scores: Dict[str, float] = dict(existing.get("ps") or {})

    if cv_locked:
        cv_scores[cv_locked] = round(float(cv_scores.get(cv_locked, 0.0)) + weight, 2)
        cv_scores["_runs"] = int(cv_scores.get("_runs", 0)) + 1
    if ps_locked:
        ps_scores[ps_locked] = round(float(ps_scores.get(ps_locked, 0.0)) + weight, 2)
        ps_scores["_runs"] = int(ps_scores.get("_runs", 0)) + 1

    new_value: Dict[str, Any] = {
        "cv": cv_scores,
        "ps": ps_scores,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_outcome": outcome,
    }

    try:
        await memory.astore(user_id, MEMORY_AGENT_TYPE, MEMORY_KEY, new_value)
    except Exception as exc:
        logger.warning("style_outcome.store_failed", error=str(exc)[:200])
        return None

    logger.info(
        "style_outcome.scored",
        user_id=user_id,
        application_id=application_id,
        outcome=outcome,
        weight=weight,
        cv_locked=cv_locked,
        ps_locked=ps_locked,
    )
    return new_value


def preferred_style(
    scores: Optional[Dict[str, Any]],
    document: str,
    *,
    fallback: str = "concise",
) -> str:
    """Return the highest-scoring variant for ``document`` (``cv`` or ``ps``).

    Used by the planner/jobs.py to pick the canonical variant.  Falls
    back to ``fallback`` when no scores exist or all scores are zero.
    """
    if not isinstance(scores, dict):
        return fallback
    bucket = scores.get(document) or {}
    if not isinstance(bucket, dict):
        return fallback
    candidates = {
        k: float(v)
        for k, v in bucket.items()
        if not k.startswith("_") and isinstance(v, (int, float))
    }
    if not candidates or max(candidates.values()) <= 0.0:
        return fallback
    return max(candidates.items(), key=lambda kv: kv[1])[0]
