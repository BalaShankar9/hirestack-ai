"""
World-Class Agentic Streaming Protocol — HireStack AI
=========================================================
Complete event taxonomy, QoS guarantees, and streaming primitives
for industry-leading agent transparency and user experience.

This module defines the foundation for:
  • Real-time token streaming (sub-100ms latency)
  • Agent thought process visibility
  • Live document assembly
  • Swarm coordination visualization
  • Interactive checkpoints
  • Bulletproof resilience with reconnect/replay

Version: 2.0.0
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Union,
)
from uuid import uuid4


# ═══════════════════════════════════════════════════════════
#  Priority System (QoS)
# ═══════════════════════════════════════════════════════════

class StreamPriority(IntEnum):
    """Event priority for backpressure-aware scheduling."""

    CRITICAL = 0  # Pipeline state changes, errors, checkpoints
    HIGH = 1  # Content generation, tool results, token streams
    NORMAL = 2  # Progress updates, agent status, heartbeats
    LOW = 3  # Telemetry, metrics, cache efficiency reports


# ═══════════════════════════════════════════════════════════
#  Event Type Taxonomy (40+ granular types)
# ═══════════════════════════════════════════════════════════

class EventType(str, Enum):
    """Hierarchical event classification."""

    # ── Lifecycle ───────────────────────────────────────────
    PIPELINE_INITIATED = "pipeline_initiated"
    AGENT_SPAWNED = "agent_spawned"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    AGENT_RETRYING = "agent_retrying"
    PIPELINE_COMPLETED = "pipeline_completed"

    # ── Thought Process ─────────────────────────────────────
    REASONING_STARTED = "reasoning_started"
    REASONING_IN_PROGRESS = "reasoning_in_progress"
    REASONING_CHECKPOINT = "reasoning_checkpoint"
    TOOL_SELECTION_DEBATE = "tool_selection_debate"
    CONFIDENCE_ASSESSMENT = "confidence_assessment"
    REASONING_COMPLETED = "reasoning_completed"

    # ── Tool Execution ──────────────────────────────────────
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_PARAMETERS = "tool_call_parameters"
    TOOL_CALL_PROGRESS = "tool_call_progress"
    TOOL_CALL_STREAMING = "tool_call_streaming"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_CACHED = "tool_call_cached"
    TOOL_CALL_FAILED = "tool_call_failed"

    # ── Content Generation ──────────────────────────────────
    GENERATION_STARTED = "generation_started"
    TOKEN_STREAM = "token_stream"
    PARAGRAPH_COMPLETED = "paragraph_completed"
    SECTION_COMPLETED = "section_completed"
    CITATION_ADDED = "citation_added"
    EVIDENCE_LINKED = "evidence_linked"
    GENERATION_COMPLETED = "generation_completed"
    GENERATION_QUALITY_SIGNAL = "generation_quality_signal"

    # ── Review & Refinement ─────────────────────────────────
    CRITIQUE_STARTED = "critique_started"
    CRITIQUE_ISSUE_FOUND = "critique_issue_found"
    CRITIQUE_COMPARISON = "critique_comparison"
    OPTIMIZATION_APPLIED = "optimization_applied"
    FACT_CHECK_CLAIM = "fact_check_claim"
    REFINEMENT_ITERATION = "refinement_iteration"

    # ── Swarm Coordination ──────────────────────────────────
    SWARM_INITIATED = "swarm_initiated"
    AGENT_ASSIGNED_TASK = "agent_assigned_task"
    AGENT_REPORTING_PROGRESS = "agent_reporting_progress"
    SWARM_CONSENSUS_FORMING = "swarm_consensus_forming"
    SWARM_CONFLICT_DETECTED = "swarm_conflict_detected"
    SWARM_RESOLUTION_APPLIED = "swarm_resolution_applied"
    SWARM_COMPLETED = "swarm_completed"

    # ── Checkpoint & Control ────────────────────────────────
    CHECKPOINT_REACHED = "checkpoint_reached"
    AWAITING_USER_APPROVAL = "awaiting_user_approval"
    USER_APPROVAL_RECEIVED = "user_approval_received"
    USER_REDIRECT_REQUESTED = "user_redirect_requested"
    PAUSE_REQUESTED = "pause_requested"
    RESUMED_FROM_CHECKPOINT = "resumed_from_checkpoint"
    CANCELLED_AT_CHECKPOINT = "cancelled_at_checkpoint"

    # ── Performance & Telemetry ───────────────────────────────
    HEARTBEAT = "heartbeat"
    LATENCY_METRIC = "latency_metric"
    TOKEN_USAGE_UPDATE = "token_usage_update"
    COST_UPDATE = "cost_update"
    CACHE_EFFICIENCY_REPORT = "cache_efficiency_report"
    QUALITY_SCORE_UPDATE = "quality_score_update"

    # ── System ──────────────────────────────────────────────
    STREAM_CONNECTED = "stream_connected"
    STREAM_RECONNECTED = "stream_reconnected"
    STREAM_BACKPRESSURE_DETECTED = "stream_backpressure_detected"
    EVENT_DROPPED_WARNING = "event_dropped_warning"
    STREAM_GRACEFUL_SHUTDOWN = "stream_graceful_shutdown"

    # ── Legacy Pipeline Compatibility (for interop with existing taxonomy) ──
    PROGRESS = "progress"
    DETAIL = "detail"
    COMPLETE = "complete"
    ERROR = "error"
    WARNING = "warning"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"


ALL_EVENT_TYPES: Set[str] = {e.value for e in EventType}


def is_valid_event_type(event_type: str) -> bool:
    """Validate event type against canonical taxonomy."""
    return event_type in ALL_EVENT_TYPES


# ═══════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class StreamingConfig:
    """Immutable configuration for world-class streaming behavior."""

    # Performance
    max_event_queue_size: int = 1_000
    event_flush_interval_ms: float = 50.0  # Max delay before flush
    heartbeat_interval_sec: float = 5.0

    # Backpressure
    enable_backpressure: bool = True
    backpressure_threshold: int = 100  # Queue size before slowing
    slow_producer_factor: float = 0.5  # Reduce generation speed

    # Resilience
    enable_event_persistence: bool = True
    event_retention_sec: int = 3_600  # For replay/resume
    max_reconnect_attempts: int = 3
    reconnect_backoff_ms: int = 1_000

    # Quality features
    enable_token_streaming: bool = True
    enable_thought_streaming: bool = True
    enable_live_citations: bool = True

    # Interactivity
    enable_checkpoints: bool = True
    default_checkpoint_stages: List[str] = field(
        default_factory=lambda: ["research", "draft", "critique", "optimization"]
    )
    approval_timeout_sec: int = 300

    @classmethod
    def production(cls) -> StreamingConfig:
        """Production-optimized defaults."""
        return cls(
            max_event_queue_size=5_000,
            event_flush_interval_ms=25.0,
            heartbeat_interval_sec=5.0,
            enable_backpressure=True,
            backpressure_threshold=200,
            enable_event_persistence=True,
            event_retention_sec=3_600,
            enable_token_streaming=True,
            enable_thought_streaming=True,
            enable_live_citations=True,
            enable_checkpoints=True,
            approval_timeout_sec=300,
        )

    @classmethod
    def development(cls) -> StreamingConfig:
        """Development defaults (verbose, no backpressure)."""
        return cls(
            max_event_queue_size=10_000,
            event_flush_interval_ms=10.0,
            heartbeat_interval_sec=3.0,
            enable_backpressure=False,
            enable_event_persistence=True,
            event_retention_sec=600,
            enable_token_streaming=True,
            enable_thought_streaming=True,
            enable_live_citations=True,
            enable_checkpoints=True,
            approval_timeout_sec=600,
        )


# ═══════════════════════════════════════════════════════════
#  Data Structures
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AgentContext:
    """Agent identification for every event."""

    id: str
    name: str
    type: str  # researcher | drafter | critic | optimizer | fact_checker | validator | sub_agent | orchestrator | system
    parent_id: Optional[str] = None
    swarm_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "parent_id": self.parent_id,
            "swarm_id": self.swarm_id,
        }


@dataclass(frozen=True)
class StageContext:
    """Execution stage metadata."""

    name: str
    iteration: int = 1
    depth: int = 0
    parallel_group: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "iteration": self.iteration,
            "depth": self.depth,
            "parallel_group": self.parallel_group,
        }


@dataclass(frozen=True)
class EventMetadata:
    """Per-event performance & cost tracking."""

    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latency_ms": round(self.latency_ms, 3),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "cache_hit": self.cache_hit,
            "retry_count": self.retry_count,
        }


# ═══════════════════════════════════════════════════════════
#  Sink Protocol (dependency injection)
# ═══════════════════════════════════════════════════════════

class EventSink(Protocol):
    """Protocol for any output channel (SSE, WebSocket, queue, log)."""

    async def send(self, event: Dict[str, Any]) -> None:
        """Deliver an event to the sink. Must not raise."""
        ...

    async def flush(self) -> None:
        """Force-flush any buffered events."""
        ...

    async def close(self) -> None:
        """Graceful shutdown."""
        ...


# ═══════════════════════════════════════════════════════════
#  Helper: timer context
# ═══════════════════════════════════════════════════════════

class StageTimer:
    """Nanosecond-precision context timer for metadata collection."""

    __slots__ = ("_start", "_end")

    def __init__(self) -> None:
        self._start: Optional[int] = None
        self._end: Optional[int] = None

    async def __aenter__(self) -> StageTimer:
        self._start = time.perf_counter_ns()
        return self

    async def __aexit__(self, *args: Any) -> None:
        self._end = time.perf_counter_ns()

    @property
    def elapsed_ms(self) -> float:
        if self._start is None:
            return 0.0
        end = self._end or time.perf_counter_ns()
        return (end - self._start) / 1_000_000.0


# ═══════════════════════════════════════════════════════════
#  JSON Serialization Helper
# ═══════════════════════════════════════════════════════════

class AgenticJSONEncoder(json.JSONEncoder):
    """Handles dataclasses, enums, and sets."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        return super().default(obj)


def dumps_event(event: Dict[str, Any]) -> str:
    """Compact JSON with custom encoder."""
    return json.dumps(event, cls=AgenticJSONEncoder, separators=(",", ":"), ensure_ascii=False)
