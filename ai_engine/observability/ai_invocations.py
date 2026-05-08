"""ADR-0034 / PR m7-pr30 — `ai_invocations` flight recorder.

One row per terminal LLM call (success **or** failure) — forward-only,
single flat table at launch (see ADR-0034 §4 for partition deferral).

Design rules:

* **Best-effort writer.** The LLM call path must NEVER fail because the
  flight recorder did. All write failures log ``ai_invocations_write_failed``
  and are swallowed.
* **Prompt body is never stored.** Only sha256-hex of ``system + prompt``.
* **Flag-gated.** When ``ff_ai_invocations_recorder`` is OFF, ``record()``
  is a no-op (returns immediately). The flag ships OFF and is flipped per
  environment after smoke.
* **Provider derived from model.** ``claude-*`` → anthropic, ``gemini*`` →
  gemini, anything else → ``unknown`` (so dashboards never lose rows).

Wired from :class:`ai_engine.client.AIClient` cascade attempt loops in
``complete()``, ``complete_json()`` (non-streaming + streaming fast-path),
and ``chat()``. Streaming paths are intentionally out-of-scope for v1 —
token counts are not finalised until the stream terminates and the call
contract is fundamentally different.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Outcomes accepted by the migration's CHECK constraint. Keep in sync with
# supabase/migrations/20260508020000_ai_invocations.sql.
_VALID_OUTCOMES = {"success", "failure", "breaker_open", "cascade_failover"}
_VALID_PROVIDERS = {"gemini", "anthropic", "unknown"}

_ERROR_MSG_MAX_LEN = 500


def _provider_for(model: Optional[str]) -> str:
    """Map a model name to one of the migration's allowed provider labels."""
    if not model:
        return "unknown"
    name = model.lower()
    if name.startswith("claude-"):
        return "anthropic"
    if name.startswith("gemini") or name.startswith("text-bison") or "vertex" in name:
        return "gemini"
    return "unknown"


def _hash_prompt(text: str) -> str:
    """sha256-hex of the prompt text. Full 64 chars so it joins cross-row."""
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()


def _flag_enabled() -> bool:
    """Read ``ff_ai_invocations_recorder`` settings-first, env-fallback."""
    try:
        from app.core.config import settings  # type: ignore
        return bool(getattr(settings, "ff_ai_invocations_recorder", False))
    except Exception:
        try:
            import os
            return os.environ.get("FF_AI_INVOCATIONS_RECORDER", "").lower() in {"1", "true", "yes"}
        except Exception:
            return False


def _anthropic_flag_enabled() -> bool:
    """Read ``ff_anthropic_provider`` for the row's ``flag_anthropic_enabled`` field."""
    try:
        from app.core.config import settings  # type: ignore
        return bool(getattr(settings, "ff_anthropic_provider", False))
    except Exception:
        try:
            import os
            return os.environ.get("FF_ANTHROPIC_PROVIDER", "").lower() in {"1", "true", "yes"}
        except Exception:
            return False


class AIInvocationsRecorder:
    """Best-effort writer for ``public.ai_invocations``.

    Singleton; instantiate via :func:`get_recorder`. The supabase client
    handle is acquired lazily on first ``record()`` so test harnesses can
    monkey-patch ``app.core.database.get_supabase`` without import-time
    side-effects.
    """

    def __init__(self) -> None:
        self._table = "ai_invocations"

    def _get_supabase(self) -> Optional[Any]:
        """Acquire a supabase service-role client. Returns ``None`` on failure."""
        try:
            from app.core.database import get_supabase  # type: ignore
            return get_supabase()
        except Exception as exc:
            logger.debug("ai_invocations_supabase_unavailable: %s", exc)
            return None

    async def record(
        self,
        *,
        model: str,
        prompt_text: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        outcome: str,
        task_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
        retry_count: int = 0,
        cascade_position: int = 0,
        error: Optional[BaseException] = None,
    ) -> None:
        """Write one flight-recorder row. Never raises.

        Parameters mirror the table columns. ``error`` is optional; when
        provided, ``error_class`` is its qualified type and ``error_message``
        is its ``str()`` truncated to 500 chars (per ADR-0034 §2).
        """
        # Flag-OFF short-circuit. Cheaper than the rest of the function.
        if not _flag_enabled():
            return

        # Validate outcome at the boundary; bad outcome would violate the
        # migration's CHECK constraint and surface as an insert error
        # downstream — better to log+drop here.
        if outcome not in _VALID_OUTCOMES:
            logger.warning("ai_invocations_invalid_outcome: outcome=%s", outcome)
            return

        provider = _provider_for(model)
        if provider not in _VALID_PROVIDERS:
            provider = "unknown"

        row = {
            "tenant_id": tenant_id,
            "task_type": task_type,
            "model": model or "",
            "provider": provider,
            "prompt_hash": _hash_prompt(prompt_text),
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "total_tokens": int((prompt_tokens or 0) + (completion_tokens or 0)),
            "latency_ms": int(max(0, latency_ms or 0)),
            "outcome": outcome,
            "retry_count": int(max(0, retry_count or 0)),
            "cascade_position": int(max(0, cascade_position or 0)),
            "flag_anthropic_enabled": _anthropic_flag_enabled(),
        }
        if error is not None:
            row["error_class"] = f"{type(error).__module__}.{type(error).__name__}"
            row["error_message"] = (str(error) or "")[:_ERROR_MSG_MAX_LEN]

        sb = self._get_supabase()
        if sb is None:
            # Already logged in _get_supabase.
            return

        try:
            sb.table(self._table).insert(row).execute()
        except Exception as exc:
            # SWALLOW. The LLM call must never fail because of telemetry.
            logger.warning(
                "ai_invocations_write_failed: outcome=%s model=%s err=%s",
                outcome, model, str(exc)[:200],
            )


_RECORDER: Optional[AIInvocationsRecorder] = None


def get_recorder() -> AIInvocationsRecorder:
    """Return the process-wide singleton recorder."""
    global _RECORDER
    if _RECORDER is None:
        _RECORDER = AIInvocationsRecorder()
    return _RECORDER


def reset_recorder_for_tests() -> None:
    """Test helper: drop the singleton so the next ``get_recorder()`` re-builds."""
    global _RECORDER
    _RECORDER = None
