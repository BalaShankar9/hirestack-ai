"""Langfuse client wrapper.

PR m4-pr12: thin singleton + ``trace_llm`` async context manager.
PR m6-pr23: trace_id contextvar + structured input/output capture.

The wrapper is intentionally degraded — if the env vars are missing OR the
``langfuse`` package is not installed, ``trace_llm`` becomes a no-op so the
LLM call still runs. This keeps Langfuse opt-in and avoids coupling the hot
path to a network dependency.

Activation: ``LANGFUSE_PUBLIC_KEY`` + ``LANGFUSE_SECRET_KEY`` set.
Optional: ``LANGFUSE_HOST`` (default https://cloud.langfuse.com).
Rollback: unset the keys.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)

_client: Optional[Any] = None
_init_attempted = False

# PR m6-pr23: in-flight LLM trace id, set by ``trace_llm`` while a
# tracked call is active. Downstream code (orchestrator → AgentResult,
# pipeline → SSE event metadata) can read this to correlate user-facing
# events with the Langfuse trace dashboard.
_current_trace_id: ContextVar[Optional[str]] = ContextVar(
    "hirestack_langfuse_trace_id", default=None,
)


def get_current_trace_id() -> Optional[str]:
    """Return the Langfuse trace id of the in-flight LLM call, or None."""
    return _current_trace_id.get()


def is_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def get_langfuse() -> Optional[Any]:
    """Return a memoised Langfuse client, or None if disabled/missing."""
    global _client, _init_attempted
    if _client is not None or _init_attempted:
        return _client
    _init_attempted = True
    if not is_enabled():
        return None
    try:
        from langfuse import Langfuse  # type: ignore
    except ImportError as exc:
        logger.warning("langfuse package missing (%s); tracing disabled", exc)
        return None
    try:
        _client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com",
        )
        logger.info("langfuse: client initialised")
    except Exception as exc:  # pragma: no cover
        logger.warning("langfuse: init failed: %s", exc)
        _client = None
    return _client


@asynccontextmanager
async def trace_llm(
    *,
    model: str,
    name: str = "gemini.generate_content",
    metadata: Optional[dict] = None,
    input: Any = None,
) -> AsyncIterator[Optional[Any]]:
    """Wrap an LLM call so Langfuse records latency, model, and outcome.

    Yields the underlying span (or ``None`` if disabled). Always re-raises
    exceptions so caller error handling is unchanged.

    PR m6-pr23: also accepts an ``input`` payload (truncated by Langfuse
    on the server) and publishes the span's trace id to the
    ``_current_trace_id`` contextvar for downstream correlation.
    """
    client = get_langfuse()
    if client is None:
        yield None
        return
    span = None
    try:
        span_kwargs: dict[str, Any] = {
            "name": name,
            "metadata": {"model": model, **(metadata or {})},
        }
        if input is not None:
            span_kwargs["input"] = input
        span = client.span(**span_kwargs)
    except Exception as exc:  # pragma: no cover
        logger.debug("langfuse span() failed: %s", exc)
        yield None
        return
    # Publish trace id so callers can stamp it onto AgentResult / SSE.
    trace_token = None
    try:
        trace_id = getattr(span, "trace_id", None) or getattr(span, "id", None)
        if trace_id:
            trace_token = _current_trace_id.set(str(trace_id))
    except Exception:  # pragma: no cover
        trace_token = None
    try:
        yield span
        try:
            span.update(level="DEFAULT")
            span.end()
        except Exception:  # pragma: no cover
            pass
    except Exception as exc:
        try:
            span.update(level="ERROR", status_message=str(exc)[:500])
            span.end()
        except Exception:  # pragma: no cover
            pass
        raise
    finally:
        if trace_token is not None:
            try:
                _current_trace_id.reset(trace_token)
            except Exception:  # pragma: no cover
                pass
