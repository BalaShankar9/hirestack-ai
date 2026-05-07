"""Langfuse client wrapper.

PR m4-pr12: thin singleton + ``trace_llm`` async context manager.

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
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)

_client: Optional[Any] = None
_init_attempted = False


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
) -> AsyncIterator[Optional[Any]]:
    """Wrap an LLM call so Langfuse records latency, model, and outcome.

    Yields the underlying span (or ``None`` if disabled). Always re-raises
    exceptions so caller error handling is unchanged.
    """
    client = get_langfuse()
    if client is None:
        yield None
        return
    span = None
    try:
        span = client.span(name=name, metadata={"model": model, **(metadata or {})})
    except Exception as exc:  # pragma: no cover
        logger.debug("langfuse span() failed: %s", exc)
        yield None
        return
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
