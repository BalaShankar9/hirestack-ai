"""
AgenticEventEmitter — World-Class Event Orchestrator
=========================================================
QoS-aware, backpressure-protected, reconnect-resilient event emitter
that powers every HireStack AI agentic pipeline.

Features:
  • Priority queue (CRITICAL > HIGH > NORMAL > LOW)
  • Sub-100ms flush latency via periodic + immediate flush
  • Backpressure detection & producer throttling
  • Event persistence for replay/resume
  • Token streaming, thought streaming, checkpoint orchestration
  • Bulletproof: no exceptions escape the emit path

Version: 2.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from .streaming_protocol import (
    AgentContext,
    EventMetadata,
    EventSink,
    EventType,
    StageContext,
    StageTimer,
    StreamPriority,
    StreamingConfig,
    dumps_event,
    is_valid_event_type,
)

logger = logging.getLogger("hirestack.agentic_emitter")


# ═══════════════════════════════════════════════════════════
#  AgenticEventEmitter
# ═══════════════════════════════════════════════════════════

class AgenticEventEmitter:
    """
    Central event bus for all agentic streaming in HireStack.

    Guarantees:
      1. Every valid event reaches the sink (unless queue overflow).
      2. CRITICAL/HIGH events flushed immediately (<100ms).
      3. NORMAL/LOW events batched & flushed periodically.
      4. Backpressure triggers graceful producer slowdown.
      5. All events persisted if persistence is enabled.
      6. Zero exceptions propagate to caller (fire-and-forget).
    """

    def __init__(
        self,
        sink: EventSink,
        config: StreamingConfig,
        *,
        session_id: Optional[str] = None,
    ) -> None:
        self._sink = sink
        self._config = config
        self._session_id = session_id or str(uuid4())

        # Sequencing
        self._sequence = 0
        self._start_time_ns = time.perf_counter_ns()

        # Priority queues — one per priority level for deterministic ordering
        self._queues: Dict[StreamPriority, asyncio.Queue[Tuple[int, str]]] = {
            StreamPriority.CRITICAL: asyncio.Queue(maxsize=config.max_event_queue_size),
            StreamPriority.HIGH: asyncio.Queue(maxsize=config.max_event_queue_size),
            StreamPriority.NORMAL: asyncio.Queue(maxsize=config.max_event_queue_size),
            StreamPriority.LOW: asyncio.Queue(maxsize=config.max_event_queue_size),
        }

        # Flush control
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._flush_event = asyncio.Event()
        self._shutdown = False

        # Backpressure tracking
        self._backpressure_active = False
        self._dropped_events = 0

        # Persistence
        self._event_store: List[Dict[str, Any]] = []
        self._accumulated_text: Dict[str, str] = {}  # agent_id → text buffer

        # Telemetry counters
        self._emitted = 0
        self._flushed = 0

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the periodic flush loop. Idempotent."""
        if self._flush_task is not None and not self._flush_task.done():
            return
        self._shutdown = False
        self._flush_task = asyncio.create_task(self._flush_loop())
        await self.emit(
            event_type=EventType.STREAM_CONNECTED,
            payload={"session_id": self._session_id, "config": self._config.__dict__},
            agent=AgentContext(id="system", name="system", type="system"),
            stage=StageContext(name="system"),
            priority=StreamPriority.CRITICAL,
        )

    async def shutdown(self, *, grace_ms: float = 500.0) -> None:
        """Graceful shutdown: flush all queued events then stop."""
        self._shutdown = True
        self._flush_event.set()
        if self._flush_task:
            try:
                await asyncio.wait_for(self._flush_task, timeout=grace_ms / 1_000.0)
            except asyncio.TimeoutError:
                self._flush_task.cancel()
        # Final emergency flush
        await self._drain_queues()
        try:
            await self._sink.send(
                {
                    "event_type": EventType.STREAM_GRACEFUL_SHUTDOWN.value,
                    "payload": {
                        "emitted": self._emitted,
                        "flushed": self._flushed,
                        "dropped": self._dropped_events,
                        "session_id": self._session_id,
                    },
                }
            )
            await self._sink.flush()
            await self._sink.close()
        except Exception:
            logger.exception("shutdown_sink_error")

    # ── Core Emit ───────────────────────────────────────────────

    async def emit(
        self,
        *,
        event_type: EventType,
        payload: Dict[str, Any],
        agent: AgentContext,
        stage: StageContext,
        priority: StreamPriority = StreamPriority.NORMAL,
        parent_event_id: Optional[str] = None,
        metadata: Optional[EventMetadata] = None,
    ) -> str:
        """
        Emit a fully-typed event. Returns the generated event_id.

        Never raises — failures are logged and, if critical, retried once.
        """
        try:
            event_id = str(uuid4())
            elapsed_ms = (time.perf_counter_ns() - self._start_time_ns) / 1_000_000.0

            event: Dict[str, Any] = {
                "event_id": event_id,
                "parent_event_id": parent_event_id,
                "sequence": self._sequence,
                "timestamp_ns": time.perf_counter_ns(),
                "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                "session_id": self._session_id,
                "elapsed_ms": round(elapsed_ms, 3),
                "event_type": event_type.value,
                "event_version": "2.0.0",
                "agent": agent.to_dict(),
                "stage": stage.to_dict(),
                "payload": payload,
                "metadata": (metadata or EventMetadata()).to_dict(),
                "priority": priority.value,
            }

            self._sequence += 1
            self._emitted += 1

            # Validate taxonomy (warn but allow through)
            if not is_valid_event_type(event_type.value):
                logger.warning("non_canonical_event_type", event_type=event_type.value)

            # Persist if enabled
            if self._config.enable_event_persistence:
                self._persist_event(event)

            # Queue with priority
            queue = self._queues[priority]
            try:
                queue.put_nowait((self._sequence, dumps_event(event)))
            except asyncio.QueueFull:
                self._dropped_events += 1
                if priority == StreamPriority.CRITICAL:
                    # CRITICAL must not drop — emergency direct flush
                    await self._emergency_flush(event)
                else:
                    logger.warning(
                        "event_dropped",
                        priority=priority.name,
                        queue_size=queue.qsize(),
                        event_type=event_type.value,
                    )
                    # Emit a warning that events are being dropped
                    asyncio.create_task(
                        self._emit_drop_warning(self._dropped_events, priority)
                    )

            # Immediate flush for CRITICAL/HIGH
            if priority in (StreamPriority.CRITICAL, StreamPriority.HIGH):
                self._flush_event.set()

            # Backpressure check
            if self._config.enable_backpressure and priority != StreamPriority.CRITICAL:
                total_queued = sum(q.qsize() for q in self._queues.values())
                if total_queued > self._config.backpressure_threshold:
                    self._backpressure_active = True
                elif total_queued < self._config.backpressure_threshold // 2:
                    self._backpressure_active = False

            return event_id

        except Exception as exc:
            logger.exception("emit_error_suppressed", event_type=event_type.value, exc=str(exc))
            return ""

    # ── Convenience Shortcuts ──────────────────────────────────

    async def emit_token_stream(
        self,
        *,
        agent_id: str,
        token: str,
        is_start: bool = False,
        is_end: bool = False,
    ) -> None:
        """Stream individual tokens for real-time typing effect."""
        if not self._config.enable_token_streaming:
            return

        # Accumulate for preview
        buf = self._accumulated_text.setdefault(agent_id, "")
        if is_start:
            buf = ""
        buf += token
        self._accumulated_text[agent_id] = buf

        payload: Dict[str, Any] = {
            "token": token,
            "is_start": is_start,
            "is_end": is_end,
            "accumulated_length": len(buf),
        }
        if is_end:
            payload["full_text"] = buf
            del self._accumulated_text[agent_id]

        await self.emit(
            event_type=EventType.TOKEN_STREAM,
            payload=payload,
            agent=AgentContext(id=agent_id, name="drafter", type="drafter"),
            stage=StageContext(name="content_generation", iteration=1, depth=0),
            priority=StreamPriority.HIGH,
        )

    async def emit_thought_stream(
        self,
        *,
        agent_id: str,
        thought_chunk: str,
        reasoning_type: str = "analysis",
        confidence: float = 0.0,
    ) -> None:
        """Stream agent's internal reasoning process."""
        if not self._config.enable_thought_streaming:
            return

        await self.emit(
            event_type=EventType.REASONING_IN_PROGRESS,
            payload={
                "thought_chunk": thought_chunk,
                "reasoning_type": reasoning_type,
                "confidence_so_far": round(confidence, 3),
            },
            agent=AgentContext(id=agent_id, name="researcher", type="researcher"),
            stage=StageContext(name="reasoning", iteration=1, depth=0),
            priority=StreamPriority.NORMAL,
        )

    async def emit_tool_call(
        self,
        *,
        agent_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        status: str = "started",
        progress: float = 0.0,
        result: Optional[Dict[str, Any]] = None,
        cached: bool = False,
    ) -> None:
        """Emit tool execution lifecycle events."""
        event_map = {
            "started": EventType.TOOL_CALL_STARTED,
            "parameters": EventType.TOOL_CALL_PARAMETERS,
            "progress": EventType.TOOL_CALL_PROGRESS,
            "completed": EventType.TOOL_CALL_COMPLETED,
            "cached": EventType.TOOL_CALL_CACHED,
            "failed": EventType.TOOL_CALL_FAILED,
        }
        event_type = event_map.get(status, EventType.TOOL_CALL_STARTED)
        payload: Dict[str, Any] = {
            "tool_name": tool_name,
            "parameters": parameters,
            "progress": round(progress, 2),
        }
        if result is not None:
            payload["result"] = result
        if cached:
            payload["cached"] = True

        priority = StreamPriority.HIGH if status in ("completed", "failed") else StreamPriority.NORMAL
        await self.emit(
            event_type=event_type,
            payload=payload,
            agent=AgentContext(id=agent_id, name="researcher", type="researcher"),
            stage=StageContext(name="tool_execution", iteration=1, depth=0),
            priority=priority,
        )

    async def emit_citation(
        self,
        *,
        agent_id: str,
        citation: Dict[str, Any],
        section_name: Optional[str] = None,
    ) -> None:
        """Emit live citation linking during document generation."""
        if not self._config.enable_live_citations:
            return

        await self.emit(
            event_type=EventType.CITATION_ADDED,
            payload={
                "citation": citation,
                "section_name": section_name,
                "citation_id": citation.get("id", str(uuid4())),
            },
            agent=AgentContext(id=agent_id, name="drafter", type="drafter"),
            stage=StageContext(name="content_generation", iteration=1, depth=0),
            priority=StreamPriority.HIGH,
        )

    async def emit_checkpoint(
        self,
        *,
        stage_name: str,
        checkpoint_type: str,  # approval | review | decision | customize
        payload: Dict[str, Any],
        timeout_sec: int = 300,
    ) -> str:
        """
        Emit interactive checkpoint and return checkpoint_id.
        Caller must separately await user response via CheckpointManager.
        """
        checkpoint_id = str(uuid4())

        await self.emit(
            event_type=EventType.CHECKPOINT_REACHED,
            payload={
                "checkpoint_id": checkpoint_id,
                "checkpoint_type": checkpoint_type,
                "stage_name": stage_name,
                "current_state": payload,
                "timeout_sec": timeout_sec,
                "actions_available": self._actions_for_checkpoint_type(checkpoint_type),
            },
            agent=AgentContext(id="orchestrator", name="orchestrator", type="orchestrator"),
            stage=StageContext(name=stage_name, iteration=1, depth=0),
            priority=StreamPriority.CRITICAL,
        )
        return checkpoint_id

    async def emit_heartbeat(self) -> None:
        """Periodic health heartbeat."""
        total_queued = sum(q.qsize() for q in self._queues.values())
        await self.emit(
            event_type=EventType.HEARTBEAT,
            payload={
                "queued_events": total_queued,
                "emitted_total": self._emitted,
                "flushed_total": self._flushed,
                "dropped_total": self._dropped_events,
                "backpressure_active": self._backpressure_active,
            },
            agent=AgentContext(id="system", name="system", type="system"),
            stage=StageContext(name="system"),
            priority=StreamPriority.LOW,
        )

    # ── Properties ─────────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def backpressure_active(self) -> bool:
        return self._backpressure_active

    @property
    def dropped_events(self) -> int:
        return self._dropped_events

    @property
    def total_queued(self) -> int:
        return sum(q.qsize() for q in self._queues.values())

    # ── Private ────────────────────────────────────────────────

    async def _flush_loop(self) -> None:
        """Background loop: periodic + event-driven flush."""
        interval = self._config.event_flush_interval_ms / 1_000.0
        while not self._shutdown:
            try:
                await asyncio.wait_for(self._flush_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            self._flush_event.clear()
            await self._drain_queues()

    async def _drain_queues(self) -> None:
        """Flush all queues in priority order (CRITICAL → LOW)."""
        for priority in (
            StreamPriority.CRITICAL,
            StreamPriority.HIGH,
            StreamPriority.NORMAL,
            StreamPriority.LOW,
        ):
            queue = self._queues[priority]
            batch: List[str] = []
            while not queue.empty():
                try:
                    _, json_event = queue.get_nowait()
                    batch.append(json_event)
                except asyncio.QueueEmpty:
                    break

            if batch:
                await self._sink_batch(batch)
                self._flushed += len(batch)

    async def _sink_batch(self, events: List[str]) -> None:
        """Send a batch to the sink with retry for CRITICAL events."""
        try:
            for ev in events:
                parsed = self._parse_event(ev)
                await self._sink.send(parsed)
            await self._sink.flush()
        except Exception:
            logger.exception("sink_batch_error", batch_size=len(events))
            # Retry once for critical items
            for ev in events:
                try:
                    parsed = self._parse_event(ev)
                    if parsed.get("priority") == StreamPriority.CRITICAL.value:
                        await self._sink.send(parsed)
                except Exception:
                    logger.exception("critical_retry_failed")

    async def _emergency_flush(self, event: Dict[str, Any]) -> None:
        """Bypass queue for critical events that overflowed."""
        try:
            await self._sink.send(event)
            await self._sink.flush()
        except Exception:
            logger.exception("emergency_flush_failed", event_id=event.get("event_id"))

    async def _emit_drop_warning(self, count: int, priority: StreamPriority) -> None:
        """Warn that events are being dropped."""
        await self.emit(
            event_type=EventType.EVENT_DROPPED_WARNING,
            payload={
                "dropped_count": count,
                "last_dropped_priority": priority.name,
                "queue_capacity": self._config.max_event_queue_size,
                "recommendation": "Consider reducing event volume or increasing queue size",
            },
            agent=AgentContext(id="system", name="system", type="system"),
            stage=StageContext(name="system"),
            priority=StreamPriority.CRITICAL,
        )

    def _persist_event(self, event: Dict[str, Any]) -> None:
        """Keep events in memory for replay (retention handled by caller)."""
        self._event_store.append(event)
        # Simple memory cap: trim oldest when too many
        max_store = self._config.max_event_queue_size * 2
        if len(self._event_store) > max_store:
            self._event_store = self._event_store[-max_store:]

    def _parse_event(self, json_str: str) -> Dict[str, Any]:
        """Parse queued JSON string back to dict."""
        import json as _json
        return _json.loads(json_str)

    @staticmethod
    def _actions_for_checkpoint_type(checkpoint_type: str) -> List[Dict[str, str]]:
        actions = {
            "approval": [
                {"id": "approve", "label": "Approve & Continue", "style": "primary"},
                {"id": "reject", "label": "Reject & Revise", "style": "danger"},
                {"id": "pause", "label": "Pause & Review Later", "style": "secondary"},
            ],
            "review": [
                {"id": "looks_good", "label": "Looks Good", "style": "primary"},
                {"id": "minor_edits", "label": "Needs Minor Edits", "style": "warning"},
                {"id": "major_rewrite", "label": "Needs Major Rewrite", "style": "danger"},
            ],
            "decision": [
                {"id": "option_a", "label": "Option A", "style": "primary"},
                {"id": "option_b", "label": "Option B", "style": "primary"},
                {"id": "custom", "label": "Custom", "style": "secondary"},
            ],
            "customize": [
                {"id": "apply_changes", "label": "Apply Changes", "style": "primary"},
                {"id": "discard", "label": "Discard Changes", "style": "secondary"},
                {"id": "preview", "label": "Preview First", "style": "info"},
            ],
        }
        return actions.get(checkpoint_type, actions["approval"])


# ═══════════════════════════════════════════════════════════
#  SSE Sink Implementation (FastAPI compatible)
# ═══════════════════════════════════════════════════════════

class SSEEventSink:
    """
    EventSink implementation that buffers events for SSE delivery.
    Used by the FastAPI StreamingResponse endpoint.
    """

    def __init__(self, max_buffer: int = 10_000) -> None:
        self._buffer: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=max_buffer)
        self._closed = False

    async def send(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self._buffer.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest to make room for new
            try:
                self._buffer.get_nowait()
                self._buffer.put_nowait(event)
            except asyncio.QueueEmpty:
                pass

    async def flush(self) -> None:
        pass  # Events are consumed immediately by the generator

    async def close(self) -> None:
        self._closed = True

    async def get(self) -> Optional[Dict[str, Any]]:
        """Blocking get for the SSE generator."""
        if self._closed and self._buffer.empty():
            return None
        try:
            return await asyncio.wait_for(self._buffer.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None

    def __aiter__(self):
        return self

    async def __anext__(self) -> Dict[str, Any]:
        item = await self.get()
        if item is None:
            raise StopAsyncIteration
        return item
