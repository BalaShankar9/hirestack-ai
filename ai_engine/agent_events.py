"""
Agent event emitter — context-scoped enriched event bus.

Phase A of the Agent World-Class Plan.  The deployed hot path
(`backend/app/api/routes/generate/jobs.py`) emits a shallow event
taxonomy: `progress | detail | agent_status | error`.  That makes the
LiveAgentActivityDock feel like a status spinner instead of a window
into the agent's reasoning.

This module exposes a thin **emit-anywhere** API powered by a
ContextVar so chains, tools, and the evidence ledger can publish
enriched events without taking a publisher object as a parameter
through every layer of the call stack.

Usage at the top of a job:

    from ai_engine.agent_events import set_event_emitter

    async def emit(event_name: str, payload: dict) -> None: ...
    token = set_event_emitter(emit)
    try:
        # ... run the job; inner code can call emit_tool_call, etc. ...
    finally:
        reset_event_emitter(token)

Usage from inside a chain or tool:

    from ai_engine.agent_events import emit_tool_call, emit_tool_result

    await emit_tool_call("github.search", {"query": "..."}, agent="recon")
    ...
    await emit_tool_result("github.search", {"items": 12}, latency_ms=830,
                           cache_hit=False, agent="recon")

Every helper degrades silently when no emitter is set, so chains
remain importable / unit-testable in isolation.
"""
from __future__ import annotations

import asyncio
import contextvars
import time
from contextlib import contextmanager
from typing import Any, Awaitable, Callable, Dict, Iterator, Optional

# An emitter is `async def emit(event_name: str, payload: dict) -> None`.
EventEmitter = Callable[[str, Dict[str, Any]], Awaitable[None]]

_current_emitter: contextvars.ContextVar[Optional[EventEmitter]] = contextvars.ContextVar(
    "agent_event_emitter", default=None
)

# Per-chain attribution: when a chain enters its main work, it sets this
# so any nested AI / tool / cache call automatically inherits the agent
# label without parameter drilling.
_current_chain_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agent_event_chain_agent", default=None
)
_current_chain_stage: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agent_event_chain_stage", default=None
)


# ─── Lifecycle ──────────────────────────────────────────────────────


def set_event_emitter(emitter: Optional[EventEmitter]) -> contextvars.Token:
    """Bind an emitter to the current context.  Returns a token for reset."""
    return _current_emitter.set(emitter)


def reset_event_emitter(token: contextvars.Token) -> None:
    """Unbind the emitter (call in a `finally`)."""
    _current_emitter.reset(token)


def get_event_emitter() -> Optional[EventEmitter]:
    """Return the currently bound emitter, or None."""
    return _current_emitter.get()


@contextmanager
def event_emitter_scope(emitter: Optional[EventEmitter]) -> Iterator[None]:
    """Context-manager form of set/reset.

    Useful for tests and synchronous setup paths.
    """
    token = set_event_emitter(emitter)
    try:
        yield
    finally:
        reset_event_emitter(token)


# ─── Chain attribution ──────────────────────────────────────────────


def get_current_chain_agent() -> Optional[str]:
    return _current_chain_agent.get()


def get_current_chain_stage() -> Optional[str]:
    return _current_chain_stage.get()


@contextmanager
def chain_agent_scope(
    agent: Optional[str], *, stage: Optional[str] = None
) -> Iterator[None]:
    """Mark the active code as belonging to a named agent / stage.

    Anything emitted from within this block (including AI client calls,
    cache lookups, evidence inserts) will be attributed to ``agent`` /
    ``stage`` automatically when the helper does not receive an
    explicit override.

    Nested scopes inherit / override naturally because each call sets
    its own ContextVar token.
    """
    a_token = _current_chain_agent.set(agent)
    s_token = _current_chain_stage.set(stage) if stage is not None else None
    try:
        yield
    finally:
        _current_chain_agent.reset(a_token)
        if s_token is not None:
            _current_chain_stage.reset(s_token)


def set_chain_agent(agent: Optional[str], *, stage: Optional[str] = None) -> None:
    """Non-block-scoped chain attribution.

    Convenient inside long sequential functions (e.g. the generation
    job runner) that walk through fixed phases.  Each call simply
    overwrites the previous ContextVar value.  No reset required —
    the outer ``event_emitter_scope`` (or job exit) tears the whole
    context down.
    """
    _current_chain_agent.set(agent)
    _current_chain_stage.set(stage)


# ─── Internal: best-effort fire-and-forget ─────────────────────────


def _fire(event_name: str, payload: Dict[str, Any]) -> None:
    """Schedule the emitter as a background task.  Never raises."""
    emitter = _current_emitter.get()
    if emitter is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g., sync test path) — drop silently.
        return
    try:
        loop.create_task(_safe_emit(emitter, event_name, payload))
    except Exception:
        # Best-effort only.  We never want telemetry to crash the agent.
        pass


async def _safe_emit(emitter: EventEmitter, event_name: str, payload: Dict[str, Any]) -> None:
    try:
        await emitter(event_name, payload)
    except Exception:
        # Swallow.  The emitter's own logging is responsible for surfacing
        # persistence failures.
        pass


def _truncate(value: Any, limit: int = 240) -> Any:
    """Keep payload sizes reasonable for the realtime channel."""
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def _summarize(payload: Optional[Dict[str, Any]], *, limit: int = 6) -> Dict[str, Any]:
    """Return a small, JSON-safe summary of an arbitrary dict."""
    if not isinstance(payload, dict):
        return {}
    summary: Dict[str, Any] = {}
    for i, (k, v) in enumerate(payload.items()):
        if i >= limit:
            summary["__truncated__"] = True
            break
        if isinstance(v, (dict, list)):
            summary[k] = f"<{type(v).__name__} len={len(v)}>"
        else:
            summary[k] = _truncate(v)
    return summary


# ─── Public emit helpers ────────────────────────────────────────────


def emit_tool_call(
    tool: str,
    arguments: Optional[Dict[str, Any]] = None,
    *,
    agent: Optional[str] = None,
    stage: Optional[str] = None,
) -> None:
    """A tool/function call is starting.  Use with `time.monotonic()` to
    pair with `emit_tool_result`."""
    agent = agent or _current_chain_agent.get() or "pipeline"
    stage = stage or _current_chain_stage.get()
    _fire(
        "tool_call",
        {
            "agent": agent,
            "stage": stage,
            "status": "running",
            "tool": tool,
            "arguments_preview": _summarize(arguments),
            "message": f"Calling tool: {tool}",
        },
    )


def emit_tool_result(
    tool: str,
    result_summary: Optional[Dict[str, Any]] = None,
    *,
    agent: Optional[str] = None,
    stage: Optional[str] = None,
    latency_ms: Optional[int] = None,
    cache_hit: bool = False,
    success: bool = True,
    error: Optional[str] = None,
) -> None:
    """A tool returned (or errored)."""
    agent = agent or _current_chain_agent.get() or "pipeline"
    stage = stage or _current_chain_stage.get()
    payload: Dict[str, Any] = {
        "agent": agent,
        "stage": stage,
        "status": "completed" if success else "failed",
        "tool": tool,
        "cache_hit": cache_hit,
        "result_preview": _summarize(result_summary),
        "message": (
            f"{tool} {'served from cache' if cache_hit else 'completed'}"
            if success
            else f"{tool} failed: {_truncate(error or '', 120)}"
        ),
    }
    if latency_ms is not None:
        payload["latency_ms"] = int(latency_ms)
    if error:
        payload["error"] = _truncate(error, 240)
    _fire("tool_result", payload)


def emit_cache_hit(
    cache_name: str,
    *,
    agent: Optional[str] = None,
    saved_ms: Optional[int] = None,
    key_preview: Optional[str] = None,
) -> None:
    """A cache lookup paid off — note for transparency + cost dashboard."""
    agent = agent or _current_chain_agent.get() or "pipeline"
    _fire(
        "cache_hit",
        {
            "agent": agent,
            "status": "info",
            "cache": cache_name,
            "saved_ms": saved_ms,
            "key_preview": _truncate(key_preview or "", 80) if key_preview else None,
            "message": (
                f"Cache hit on {cache_name}"
                + (f" (saved ~{saved_ms}ms)" if saved_ms else "")
            ),
        },
    )


def emit_evidence_added(
    *,
    tier: str,
    source: str,
    text: str,
    confidence: Optional[float] = None,
    sub_agent: Optional[str] = None,
    cross_confirmed: bool = False,
) -> None:
    """A new evidence item entered the ledger (or was cross-confirmed)."""
    agent = sub_agent or _current_chain_agent.get() or "pipeline"
    _fire(
        "evidence_added",
        {
            "agent": agent,
            "status": "info",
            "tier": tier,
            "source": source,
            "confidence": confidence,
            "cross_confirmed": cross_confirmed,
            "snippet": _truncate(text, 160),
            "message": (
                f"Evidence cross-confirmed by {sub_agent}"
                if cross_confirmed
                else f"Evidence added · tier={tier} · source={source}"
            ),
        },
    )


def emit_policy_decision(
    decision: str,
    *,
    reason: str,
    agent: Optional[str] = None,
    stage: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Any branch / retry / skip taken by orchestration policy."""
    agent = agent or _current_chain_agent.get() or "pipeline"
    stage = stage or _current_chain_stage.get()
    payload: Dict[str, Any] = {
        "agent": agent,
        "stage": stage,
        "status": "info",
        "decision": decision,
        "reason": _truncate(reason, 240),
        "message": f"Policy: {decision} — {_truncate(reason, 120)}",
    }
    if metadata:
        payload["metadata"] = _summarize(metadata)
    _fire("policy_decision", payload)


# ─── Helpers for callers that want to time their own tool calls ────


class TimedTool:
    """Sugar: `with TimedTool('github.search', agent='recon') as t: ...`

    Emits `tool_call` on enter, `tool_result` on exit (including latency
    and exception status).  No-op when no emitter is bound.
    """

    def __init__(
        self,
        tool: str,
        *,
        agent: Optional[str] = None,
        stage: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.tool = tool
        self.agent = agent
        self.stage = stage
        self.arguments = arguments
        self._t0 = 0.0
        self.result_summary: Optional[Dict[str, Any]] = None
        self.cache_hit: bool = False

    def __enter__(self) -> "TimedTool":
        self._t0 = time.monotonic()
        emit_tool_call(self.tool, self.arguments, agent=self.agent, stage=self.stage)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        latency_ms = int((time.monotonic() - self._t0) * 1000)
        emit_tool_result(
            self.tool,
            self.result_summary,
            agent=self.agent,
            stage=self.stage,
            latency_ms=latency_ms,
            cache_hit=self.cache_hit,
            success=exc is None,
            error=str(exc) if exc else None,
        )
        # Do not suppress.

    async def __aenter__(self) -> "TimedTool":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.__exit__(exc_type, exc, tb)
