# HireStack AI — Full Elevation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevate HireStack AI with a 7-agent swarm framework, end-to-end feature quality polish across all 12 modules, and a Replit App Builder style UI/UX.

**Architecture:** Agent swarm wraps existing AI chains via DrafterAgent, adding Researcher→Drafter→(Critic+Optimizer+FactChecker parallel)→Validator pipeline stages. All agents use the existing AIClient facade (Ollama→Gemini→OpenAI fallback). Frontend transforms to panel-based workspace with real-time SSE agent progress, command palette, and dual-font system.

**Tech Stack:** Python 3.11+ / FastAPI / asyncio (backend agents), Next.js 14 / TypeScript / react-resizable-panels / cmdk (frontend), Supabase PostgreSQL (database), existing AIClient multi-provider facade.

**Spec:** `docs/superpowers/specs/2026-03-15-hirestack-elevation-design.md`

---

## Chunk 1: Phase 1 — Agent Framework Foundation

This chunk builds the entire agent swarm framework: base classes, all 7 agents, pipeline engine, memory, tracing, locking, prompts, database tables, and shared frontend components.

### File Structure

```
ai_engine/agents/                    # NEW directory
├── __init__.py                      # Exports all agent classes
├── base.py                          # BaseAgent, AgentResult
├── orchestrator.py                  # AgentPipeline, PipelineResult, PipelineLockManager
├── drafter.py                       # DrafterAgent (wraps existing chains)
├── critic.py                        # CriticAgent
├── optimizer.py                     # OptimizerAgent
├── fact_checker.py                  # FactCheckerAgent
├── researcher.py                    # ResearcherAgent
├── schema_validator.py              # ValidatorAgent
├── memory.py                        # AgentMemory service
├── trace.py                         # AgentTrace logging service
├── lock.py                          # PipelineLockManager
└── prompts/                         # NEW directory
    ├── critic_system.md
    ├── optimizer_system.md
    ├── fact_checker_system.md
    ├── researcher_system.md
    ├── schema_validator_system.md
    └── drafter_revision.md

ai_engine/schemas/                   # NEW directory
├── profile_schema.json
├── benchmark_schema.json
├── gap_analysis_schema.json
├── cv_schema.json
├── cover_letter_schema.json
├── ats_scan_schema.json
└── interview_schema.json

backend/tests/                       # NEW directory
├── __init__.py
├── conftest.py                      # Fixtures, mock AIClient
└── unit/
    ├── __init__.py
    └── test_agents/
        ├── __init__.py
        ├── test_base.py
        ├── test_orchestrator.py
        ├── test_memory.py
        ├── test_lock.py
        └── test_trace.py

supabase/migrations/
├── 20260315000000_agent_tables.sql  # agent_memory + agent_traces tables

frontend/src/
├── fonts/
│   └── ibm-plex-mono.ts            # IBM Plex Mono config
├── components/
│   ├── feedback/
│   │   ├── error-card.tsx
│   │   ├── loading-skeleton.tsx
│   │   └── retry-button.tsx
│   └── command-palette/
│       ├── command-palette.tsx
│       ├── command-list.tsx
│       └── use-commands.ts
```

---

### Task 1: Database Migration — Agent Tables

**Files:**

- Create: `supabase/migrations/20260315000000_agent_tables.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Agent Memory: per-user learning across pipeline runs
CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_type VARCHAR(50) NOT NULL,
    memory_key VARCHAR(255) NOT NULL,
    memory_value JSONB NOT NULL,
    relevance_score NUMERIC(3,2) DEFAULT 1.0,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, agent_type, memory_key)
);

CREATE INDEX idx_agent_memory_user ON agent_memory(user_id, agent_type);

-- Agent Traces: full pipeline observability
CREATE TABLE IF NOT EXISTS agent_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pipeline_name VARCHAR(100) NOT NULL,
    stages JSONB NOT NULL,
    total_latency_ms INTEGER NOT NULL,
    iterations_used INTEGER DEFAULT 0,
    quality_scores JSONB,
    fact_check_flags JSONB,
    status VARCHAR(20) DEFAULT 'completed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_traces_user ON agent_traces(user_id);
CREATE INDEX idx_agent_traces_pipeline ON agent_traces(pipeline_name);

-- RLS policies
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_traces ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own agent memory"
    ON agent_memory FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Users can view own agent traces"
    ON agent_traces FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert agent traces"
    ON agent_traces FOR INSERT
    WITH CHECK (true);

-- Security fix: RLS on review_comments (deferred from earlier phases)
ALTER TABLE review_comments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own review comments"
    ON review_comments FOR ALL
    USING (auth.uid() = user_id);
```

- [ ] **Step 2: Verify migration syntax**

Run: `cat supabase/migrations/20260315000000_agent_tables.sql | head -5`
Expected: First lines of migration visible

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260315000000_agent_tables.sql
git commit -m "feat: add agent_memory and agent_traces tables with RLS"
```

---

### Task 2: Agent Base Classes

**Files:**

- Create: `ai_engine/agents/__init__.py`
- Create: `ai_engine/agents/base.py`

- [ ] **Step 1: Write the test for AgentResult and BaseAgent**

```python
# backend/tests/unit/test_agents/test_base.py
import pytest
from ai_engine.agents.base import AgentResult, BaseAgent


def test_agent_result_creation():
    result = AgentResult(
        content={"text": "hello"},
        quality_scores={"impact": 85},
        flags=[],
        latency_ms=1200,
        metadata={"agent": "critic"},
    )
    assert result.content == {"text": "hello"}
    assert result.quality_scores["impact"] == 85
    assert result.latency_ms == 1200
    assert result.flags == []


def test_agent_result_needs_revision_false_by_default():
    result = AgentResult(
        content={}, quality_scores={}, flags=[], latency_ms=0, metadata={},
    )
    assert result.needs_revision is False


def test_agent_result_needs_revision_true():
    result = AgentResult(
        content={}, quality_scores={}, flags=[], latency_ms=0, metadata={},
        needs_revision=True,
        feedback={"issue": "tone mismatch"},
    )
    assert result.needs_revision is True
    assert result.feedback == {"issue": "tone mismatch"}


def test_base_agent_is_abstract():
    with pytest.raises(TypeError):
        BaseAgent(name="test", system_prompt="test", output_schema={})
```

- [ ] **Step 2: Create test infrastructure**

```python
# backend/tests/__init__.py
# (empty)
```

```python
# backend/tests/unit/__init__.py
# (empty)
```

```python
# backend/tests/unit/test_agents/__init__.py
# (empty)
```

```python
# backend/tests/conftest.py
"""Shared test fixtures for HireStack AI backend tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_ai_client():
    """Mock AIClient that returns configurable responses."""
    client = MagicMock()
    client.complete = AsyncMock(return_value="mock response")
    client.complete_json = AsyncMock(return_value={"result": "mock"})
    client.chat = AsyncMock(return_value="mock chat response")
    client.provider_name = "mock"
    client.model = "mock-model"
    client.max_tokens = 4096
    return client
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_base.py -v 2>&1 | head -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_engine.agents'`

- [ ] **Step 4: Implement AgentResult and BaseAgent**

```python
# ai_engine/agents/base.py
"""
Agent base classes for the HireStack AI agent swarm framework.

BaseAgent is the abstract parent for all specialized agents.
AgentResult is the standardized output container for every agent.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ai_engine.client import AIClient


@dataclass
class AgentResult:
    """Standardized output from any agent."""
    content: dict
    quality_scores: dict
    flags: list[str]
    latency_ms: int
    metadata: dict
    needs_revision: bool = False
    feedback: Optional[dict] = None
    suggestions: Optional[dict] = None


class BaseAgent(ABC):
    """Abstract base for all HireStack agents."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        output_schema: dict,
        ai_client: Optional[AIClient] = None,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.output_schema = output_schema
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    @abstractmethod
    async def run(self, context: dict) -> AgentResult:
        """Execute the agent's primary task."""
        ...

    async def run_with_retry(
        self, context: dict, max_retries: int = 2
    ) -> AgentResult:
        """Run with retry on transient failures."""
        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                return await self.run(context)
            except Exception as e:
                last_error = e
                if attempt >= max_retries:
                    raise
        raise last_error  # unreachable but satisfies type checker

    def _timed_result(
        self,
        start_ns: int,
        content: dict,
        quality_scores: dict | None = None,
        flags: list[str] | None = None,
        metadata: dict | None = None,
        needs_revision: bool = False,
        feedback: dict | None = None,
        suggestions: dict | None = None,
    ) -> AgentResult:
        """Helper to build AgentResult with elapsed time."""
        elapsed_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
        return AgentResult(
            content=content,
            quality_scores=quality_scores or {},
            flags=flags or [],
            latency_ms=elapsed_ms,
            metadata=metadata or {"agent": self.name},
            needs_revision=needs_revision,
            feedback=feedback,
            suggestions=suggestions,
        )
```

```python
# ai_engine/agents/__init__.py
"""HireStack AI Agent Swarm Framework."""
from ai_engine.agents.base import BaseAgent, AgentResult

__all__ = ["BaseAgent", "AgentResult"]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_base.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add ai_engine/agents/__init__.py ai_engine/agents/base.py backend/tests/
git commit -m "feat: add BaseAgent and AgentResult base classes with tests"
```

---

### Task 3: PipelineLockManager

**Files:**

- Create: `ai_engine/agents/lock.py`
- Create: `backend/tests/unit/test_agents/test_lock.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_agents/test_lock.py
import asyncio
import pytest
from ai_engine.agents.lock import PipelineLockManager


@pytest.mark.asyncio
async def test_lock_acquires_and_releases():
    mgr = PipelineLockManager()
    async with mgr.acquire("user1", "cv_gen", "pipe1"):
        pass  # should not raise


@pytest.mark.asyncio
async def test_lock_blocks_concurrent_same_user_pipeline():
    mgr = PipelineLockManager()
    order = []

    async def first():
        async with mgr.acquire("user1", "cv_gen", "pipe1"):
            order.append("first_start")
            await asyncio.sleep(0.1)
            order.append("first_end")

    async def second():
        await asyncio.sleep(0.02)  # ensure first starts first
        async with mgr.acquire("user1", "cv_gen", "pipe2"):
            order.append("second_start")

    await asyncio.gather(first(), second())
    assert order == ["first_start", "first_end", "second_start"]


@pytest.mark.asyncio
async def test_lock_allows_different_users_concurrently():
    mgr = PipelineLockManager()
    order = []

    async def user1():
        async with mgr.acquire("user1", "cv_gen", "pipe1"):
            order.append("user1")
            await asyncio.sleep(0.05)

    async def user2():
        async with mgr.acquire("user2", "cv_gen", "pipe2"):
            order.append("user2")
            await asyncio.sleep(0.05)

    await asyncio.gather(user1(), user2())
    assert "user1" in order and "user2" in order


@pytest.mark.asyncio
async def test_lock_timeout():
    mgr = PipelineLockManager(timeout_seconds=0.1)

    async with mgr.acquire("user1", "cv_gen", "pipe1"):
        with pytest.raises(asyncio.TimeoutError):
            async with mgr.acquire("user1", "cv_gen", "pipe2"):
                pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_lock.py -v 2>&1 | head -10`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement PipelineLockManager**

```python
# ai_engine/agents/lock.py
"""
Pipeline concurrency control.

Prevents concurrent pipeline runs for the same (user_id, pipeline_name).
Uses in-memory asyncio.Lock per key with configurable timeout.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator


class PipelineLockManager:
    """One active pipeline per (user_id, pipeline_name)."""

    def __init__(self, timeout_seconds: float = 300.0):
        self._locks: dict[str, asyncio.Lock] = {}
        self._timeout = timeout_seconds

    def _key(self, user_id: str, pipeline_name: str) -> str:
        return f"{user_id}:{pipeline_name}"

    @asynccontextmanager
    async def acquire(
        self, user_id: str, pipeline_name: str, pipeline_id: str
    ) -> AsyncGenerator[None, None]:
        key = self._key(user_id, pipeline_name)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        lock = self._locks[key]
        await asyncio.wait_for(lock.acquire(), timeout=self._timeout)
        try:
            yield
        finally:
            lock.release()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_lock.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ai_engine/agents/lock.py backend/tests/unit/test_agents/test_lock.py
git commit -m "feat: add PipelineLockManager for per-user pipeline concurrency control"
```

---

### Task 4: AgentTrace Logging Service

**Files:**

- Create: `ai_engine/agents/trace.py`
- Create: `backend/tests/unit/test_agents/test_trace.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_agents/test_trace.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_engine.agents.trace import AgentTracer


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.execute = AsyncMock(return_value=MagicMock(data=[{"id": "trace-1"}]))
    return db


@pytest.mark.asyncio
async def test_tracer_records_stage():
    tracer = AgentTracer(pipeline_id="pipe-1", pipeline_name="cv_gen", user_id="user-1")
    tracer.record_stage("researcher", latency_ms=1500, status="completed", output_summary={"keywords": 5})
    assert len(tracer.stages) == 1
    assert tracer.stages[0]["agent"] == "researcher"
    assert tracer.stages[0]["latency_ms"] == 1500


@pytest.mark.asyncio
async def test_tracer_builds_trace_record():
    tracer = AgentTracer(pipeline_id="pipe-1", pipeline_name="cv_gen", user_id="user-1")
    tracer.record_stage("researcher", latency_ms=1000, status="completed")
    tracer.record_stage("drafter", latency_ms=5000, status="completed")
    record = tracer.build_record(
        quality_scores={"impact": 87},
        fact_check_flags=[],
        iterations_used=0,
    )
    assert record["pipeline_id"] == "pipe-1"
    assert record["total_latency_ms"] == 6000
    assert record["status"] == "completed"
    assert len(record["stages"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_trace.py -v 2>&1 | head -10`
Expected: FAIL

- [ ] **Step 3: Implement AgentTracer**

```python
# ai_engine/agents/trace.py
"""
Agent pipeline tracing and observability.

Records each agent stage's timing, status, and output summary.
Persists to the agent_traces table for debugging and quality monitoring.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.trace")


class AgentTracer:
    """Collects trace data during a pipeline run."""

    def __init__(self, pipeline_id: str, pipeline_name: str, user_id: str):
        self.pipeline_id = pipeline_id
        self.pipeline_name = pipeline_name
        self.user_id = user_id
        self.stages: list[dict[str, Any]] = []

    def record_stage(
        self,
        agent: str,
        latency_ms: int,
        status: str = "completed",
        output_summary: dict | None = None,
        error: str | None = None,
    ) -> None:
        self.stages.append({
            "agent": agent,
            "latency_ms": latency_ms,
            "status": status,
            "output_summary": output_summary or {},
            "error": error,
        })

    def build_record(
        self,
        quality_scores: dict | None = None,
        fact_check_flags: list | None = None,
        iterations_used: int = 0,
        status: str = "completed",
    ) -> dict[str, Any]:
        total_latency = sum(s["latency_ms"] for s in self.stages)
        return {
            "pipeline_id": self.pipeline_id,
            "user_id": self.user_id,
            "pipeline_name": self.pipeline_name,
            "stages": self.stages,
            "total_latency_ms": total_latency,
            "iterations_used": iterations_used,
            "quality_scores": quality_scores or {},
            "fact_check_flags": fact_check_flags or [],
            "status": status,
        }

    async def save(self, db) -> None:
        """Persist trace to agent_traces table."""
        record = self.build_record()
        try:
            result = db.table("agent_traces").insert(record).execute()
            logger.info(
                "trace_saved",
                pipeline_id=self.pipeline_id,
                pipeline_name=self.pipeline_name,
                total_latency_ms=record["total_latency_ms"],
            )
        except Exception as e:
            logger.error("trace_save_failed", error=str(e), pipeline_id=self.pipeline_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_trace.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add ai_engine/agents/trace.py backend/tests/unit/test_agents/test_trace.py
git commit -m "feat: add AgentTracer for pipeline observability"
```

---

### Task 5: AgentMemory Service

**Files:**

- Create: `ai_engine/agents/memory.py`
- Create: `backend/tests/unit/test_agents/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_agents/test_memory.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from ai_engine.agents.memory import AgentMemory


@pytest.fixture
def mock_db():
    """Supabase client is synchronous — all .execute() calls return MagicMock."""
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.select = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.update = MagicMock(return_value=db)
    db.delete = MagicMock(return_value=db)
    db.upsert = MagicMock(return_value=db)
    db.eq = MagicMock(return_value=db)
    db.order = MagicMock(return_value=db)
    db.limit = MagicMock(return_value=db)
    db.execute = MagicMock(return_value=MagicMock(data=[]))
    return db


def test_ranking_formula():
    """rank = relevance_score * 0.7 + recency_score * 0.3"""
    mem = AgentMemory.__new__(AgentMemory)
    # Fresh memory (0 days ago) with relevance 1.0
    rank = mem._compute_rank(relevance_score=1.0, days_since_last_used=0)
    assert rank == pytest.approx(1.0)  # 1.0*0.7 + 1.0*0.3

    # Old memory (9 days ago) with relevance 1.0
    rank = mem._compute_rank(relevance_score=1.0, days_since_last_used=9)
    assert rank == pytest.approx(0.73)  # 1.0*0.7 + 0.1*0.3

    # Fresh memory with low relevance
    rank = mem._compute_rank(relevance_score=0.0, days_since_last_used=0)
    assert rank == pytest.approx(0.3)  # 0.0*0.7 + 1.0*0.3


def test_feedback_positive_caps_at_1():
    mem = AgentMemory.__new__(AgentMemory)
    new_score = mem._adjust_relevance(0.95, was_useful=True)
    assert new_score == 1.0


def test_feedback_negative_floors_at_0():
    mem = AgentMemory.__new__(AgentMemory)
    new_score = mem._adjust_relevance(0.1, was_useful=False)
    assert new_score == 0.0


def test_max_memories_constant():
    assert AgentMemory.MAX_MEMORIES_PER_USER_AGENT == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_memory.py -v 2>&1 | head -10`
Expected: FAIL

- [ ] **Step 3: Implement AgentMemory**

```python
# ai_engine/agents/memory.py
"""
Agent Memory — per-user learning across pipeline runs.

Stores learned patterns (tone preferences, keyword confirmations, length preferences)
and recalls them using a weighted ranking formula:
  rank = relevance_score * 0.7 + recency_score * 0.3
  where recency_score = 1.0 / (1 + days_since_last_used)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.memory")


class AgentMemory:
    """Per-user, per-agent memory with ranked recall and eviction."""

    MAX_MEMORIES_PER_USER_AGENT = 50

    def __init__(self, db):
        self.db = db

    def _compute_rank(self, relevance_score: float, days_since_last_used: float) -> float:
        recency_score = 1.0 / (1.0 + days_since_last_used)
        return round(relevance_score * 0.7 + recency_score * 0.3, 2)

    def _adjust_relevance(self, current: float, was_useful: bool) -> float:
        if was_useful:
            return min(1.0, round(current + 0.1, 2))
        return max(0.0, round(current - 0.15, 2))

    def store(
        self, user_id: str, agent_type: str, key: str, value: dict
    ) -> None:
        """Store a learned pattern. Upserts on (user_id, agent_type, key).
        Evicts lowest-ranked memory if limit exceeded.

        Note: Supabase Python client is synchronous. Methods are sync.
        """
        self.db.table("agent_memory").upsert({
            "user_id": user_id,
            "agent_type": agent_type,
            "memory_key": key,
            "memory_value": value,
            "relevance_score": 1.0,
            "usage_count": 1,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,agent_type,memory_key").execute()

        self._evict_if_needed(user_id, agent_type)

    def recall(
        self, user_id: str, agent_type: str, limit: int = 10
    ) -> list[dict]:
        """Retrieve relevant memories using weighted ranking formula:
        rank = relevance_score * 0.7 + recency_score * 0.3
        where recency_score = 1.0 / (1 + days_since_last_used)
        """
        # Fetch all memories for this user+agent (up to MAX), then rank in Python
        result = (
            self.db.table("agent_memory")
            .select("*")
            .eq("user_id", user_id)
            .eq("agent_type", agent_type)
            .execute()
        )
        memories = result.data or []

        # Compute rank using the weighted formula
        now = datetime.now(timezone.utc)
        for mem in memories:
            last_used = mem.get("last_used_at")
            if isinstance(last_used, str):
                try:
                    last_dt = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
                    days_ago = (now - last_dt).total_seconds() / 86400.0
                except (ValueError, TypeError):
                    days_ago = 30.0
            else:
                days_ago = 30.0
            relevance = float(mem.get("relevance_score", 0.5))
            mem["_rank"] = self._compute_rank(relevance, days_ago)

        # Sort by rank descending, take top `limit`
        memories.sort(key=lambda m: m["_rank"], reverse=True)
        top_memories = memories[:limit]

        # Update last_used_at for recalled memories
        for mem in top_memories:
            self.db.table("agent_memory").update({
                "last_used_at": now.isoformat(),
                "usage_count": (mem.get("usage_count") or 0) + 1,
            }).eq("id", mem["id"]).execute()
            mem.pop("_rank", None)  # clean up internal field

        return top_memories

    def feedback(self, memory_id: str, was_useful: bool) -> None:
        """Adjust relevance_score based on feedback."""
        result = (
            self.db.table("agent_memory")
            .select("relevance_score")
            .eq("id", memory_id)
            .execute()
        )
        if not result.data:
            return
        current = float(result.data[0].get("relevance_score", 0.5))
        new_score = self._adjust_relevance(current, was_useful)
        self.db.table("agent_memory").update({
            "relevance_score": new_score,
        }).eq("id", memory_id).execute()

    def _evict_if_needed(self, user_id: str, agent_type: str) -> None:
        """Remove lowest-ranked memories if over limit."""
        result = (
            self.db.table("agent_memory")
            .select("id, relevance_score, last_used_at")
            .eq("user_id", user_id)
            .eq("agent_type", agent_type)
            .order("relevance_score", desc=False)
            .execute()
        )
        memories = result.data or []
        if len(memories) <= self.MAX_MEMORIES_PER_USER_AGENT:
            return

        to_remove = memories[: len(memories) - self.MAX_MEMORIES_PER_USER_AGENT]
        for mem in to_remove:
            self.db.table("agent_memory").delete().eq("id", mem["id"]).execute()
            logger.info("memory_evicted", user_id=user_id, agent_type=agent_type, memory_id=mem["id"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_memory.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ai_engine/agents/memory.py backend/tests/unit/test_agents/test_memory.py
git commit -m "feat: add AgentMemory service with ranking and eviction"
```

---

### Task 6: Agent System Prompts

**Files:**

- Create: `ai_engine/agents/prompts/critic_system.md`
- Create: `ai_engine/agents/prompts/optimizer_system.md`
- Create: `ai_engine/agents/prompts/fact_checker_system.md`
- Create: `ai_engine/agents/prompts/researcher_system.md`
- Create: `ai_engine/agents/prompts/schema_validator_system.md`
- Create: `ai_engine/agents/prompts/drafter_revision.md`

- [ ] **Step 1: Write Critic system prompt**

```markdown
<!-- ai_engine/agents/prompts/critic_system.md -->
# Critic Agent — Quality Review

You are a quality review specialist for career documents. You evaluate content across four dimensions and provide structured feedback.

## Scoring Dimensions (0–100 each)

1. **Impact** — Are achievements quantified? Are action verbs strong? Does the content demonstrate measurable results?
2. **Clarity** — Is the writing clear and concise? Are sentences well-structured? Is jargon appropriate for the audience?
3. **Tone Match** — Does the tone match the target company culture? Is it appropriately formal/casual?
4. **Completeness** — Are all required sections present? Are there gaps in coverage?

## Decision Logic

- If ANY dimension scores below 70: set `needs_revision = true`
- If ALL dimensions score 80+: set `needs_revision = false`
- Between 70-79 on any dimension: use judgment based on overall quality

## Output Format (JSON)

```json
{
  "quality_scores": {
    "impact": 85,
    "clarity": 92,
    "tone_match": 78,
    "completeness": 88
  },
  "needs_revision": false,
  "feedback": {
    "strengths": ["Strong quantified achievements", "Clear structure"],
    "improvements": ["Consider more company-specific language"],
    "critical_issues": []
  },
  "overall_assessment": "Document meets quality standards with minor tone adjustments recommended."
}
```

## Context Available

You will receive:

- The draft document content
- The target job title and company
- The user's profile data
- Any agent memories about this user's preferences

Consider agent memories when evaluating tone — if the user has a documented preference for formal/casual tone, weight that in your tone_match scoring.

```

- [ ] **Step 2: Write Optimizer system prompt**

```markdown
<!-- ai_engine/agents/prompts/optimizer_system.md -->
# Optimizer Agent — ATS & Readability Optimization

You are an ATS (Applicant Tracking System) and readability optimization specialist. You analyze documents for keyword density, readability scores, quantified impacts, and section ordering.

## Analysis Areas

1. **ATS Keywords** — Extract target keywords from the job description. Check which are present in the document, which are missing, and suggest natural insertion points.
2. **Readability** — Evaluate sentence length, paragraph structure, and reading level. Target: 8th-10th grade reading level for maximum ATS compatibility.
3. **Quantified Impacts** — Count quantified achievements (numbers, percentages, dollar amounts). Suggest where vague statements can be quantified.
4. **Section Ordering** — Evaluate whether section order matches recruiter scanning patterns (summary → experience → skills → education).

## Output Format (JSON)

```json
{
  "keyword_analysis": {
    "present": ["Python", "React", "AWS"],
    "missing": ["Kubernetes", "CI/CD"],
    "insertion_suggestions": [
      {"keyword": "Kubernetes", "location": "experience section, project 2", "suggestion": "Deployed microservices on Kubernetes clusters"}
    ]
  },
  "readability_score": 78,
  "quantification": {
    "quantified_count": 8,
    "vague_statements": [
      {"text": "Improved performance significantly", "suggestion": "Improved API response time by 40% (from 500ms to 300ms)"}
    ]
  },
  "section_order_optimal": true,
  "suggestions": [
    {"type": "keyword", "priority": "high", "text": "Add 'Kubernetes' to experience section"},
    {"type": "readability", "priority": "medium", "text": "Break paragraph 3 into shorter sentences"}
  ]
}
```

```

- [ ] **Step 3: Write Fact-Checker system prompt**

```markdown
<!-- ai_engine/agents/prompts/fact_checker_system.md -->
# Fact-Checker Agent — Source Verification

You verify every claim in a generated document against the user's actual profile data.

## Classification System (Three Tiers)

| Classification | Definition | Action |
|---------------|-----------|--------|
| **Verified** | Claim directly maps to data in the user's profile (skills, titles, companies, dates) | Mark as verified |
| **Enhanced** | Claim is a strategic reframing of real experience (e.g., "Led cross-functional team" derived from "Worked with designers and backend engineers") | Mark as enhanced, keep in output |
| **Fabricated** | Claim has NO basis in any profile data (invented company, fake certification, non-existent technology) | Flag for removal |

## Important Boundary

**Enhancement IS allowed.** Reframing, quantifying, and elevating real experience is a product feature.
**Fabrication is NOT allowed.** Inventing experience, skills, or credentials with zero basis in the profile.

## Input

You receive:
- `draft`: The generated document content
- `source`: The user's profile data (skills, experience, education, certifications)

## Output Format (JSON)

```json
{
  "claims": [
    {
      "text": "Led a team of 5 engineers",
      "classification": "enhanced",
      "source_reference": "experience[0].description: 'Worked with 5 team members'",
      "confidence": 0.85
    }
  ],
  "summary": {
    "verified": 14,
    "enhanced": 8,
    "fabricated": 0
  },
  "fabricated_claims": [],
  "overall_accuracy": 1.0
}
```

```

- [ ] **Step 4: Write Researcher system prompt**

```markdown
<!-- ai_engine/agents/prompts/researcher_system.md -->
# Researcher Agent — Context Gathering

You analyze job descriptions, company context, and user profiles to extract signals that guide the drafting process.

## Research Areas

1. **Industry Signals** — What industry is this? What are the current trends? What terminology matters?
2. **Company Culture** — Startup vs enterprise? Formal or casual? Innovation-focused or stability-focused?
3. **Role Emphasis** — What does this role prioritize? Technical depth, leadership, cross-functional, individual contributor?
4. **Resume Format** — Based on the user's experience level and target role, recommend: chronological, functional, or hybrid format.
5. **Keyword Emphasis** — Which skills/technologies are mentioned most in the JD? What's the priority order?

## Output Format (JSON)

```json
{
  "industry": "fintech",
  "company_culture": "startup, innovation-focused, fast-paced",
  "role_emphasis": ["technical leadership", "system design", "mentoring"],
  "recommended_format": "chronological",
  "keyword_priority": [
    {"keyword": "Python", "mentions": 3, "priority": "critical"},
    {"keyword": "AWS", "mentions": 2, "priority": "high"}
  ],
  "tone_recommendation": "professional but approachable",
  "key_signals": [
    "Company values 'ownership' — emphasize end-to-end project ownership",
    "JD mentions 'scale' 4 times — quantify scalability achievements"
  ]
}
```

```

- [ ] **Step 5: Write Schema Validator system prompt**

```markdown
<!-- ai_engine/agents/prompts/schema_validator_system.md -->
# Schema Validator Agent — Final Validation

You perform the final validation pass on pipeline output before delivery.

## Checks

1. **Schema Compliance** — Does the output match the expected JSON schema?
2. **Format Correctness** — Is HTML valid? Are all tags closed? Is the structure well-formed?
3. **Completeness** — Are all required sections present? Are there empty fields that should have content?
4. **Length Checks** — Is the document length appropriate for its type? (CV: 1-2 pages, Cover Letter: 1 page, etc.)

## Output Format (JSON)

```json
{
  "valid": true,
  "checks": {
    "schema_compliant": true,
    "format_valid": true,
    "all_sections_present": true,
    "length_appropriate": true
  },
  "issues": [],
  "content": { "...passed through from input if valid..." }
}
```

```

- [ ] **Step 6: Write Drafter revision prompt**

```markdown
<!-- ai_engine/agents/prompts/drafter_revision.md -->
# Drafter Revision Prompt

You are revising a document based on feedback from quality review agents. Your task is to improve the document while maintaining its core structure and factual accuracy.

## Inputs

- **Original Draft**: The document to revise
- **Critic Feedback**: Quality scores and improvement suggestions
- **Optimizer Suggestions**: ATS keywords to add, readability fixes, quantification opportunities
- **Fact-Check Flags**: Any claims flagged as fabricated (must be removed or corrected)

## Rules

1. **Remove all fabricated claims** — If the fact-checker flagged a claim as fabricated, remove it entirely or replace with a verified/enhanced claim
2. **Apply optimizer suggestions naturally** — Insert missing keywords in context, don't just list them
3. **Address critic feedback** — Focus on the dimensions that scored below 80
4. **Preserve verified content** — Don't change claims that were verified as accurate
5. **Maintain document length** — Don't significantly increase or decrease length unless the critic flagged it

## Output

Return the revised document in the same format as the original (HTML for CV/CL, JSON for structured data).
```

- [ ] **Step 7: Commit**

```bash
git add ai_engine/agents/prompts/
git commit -m "feat: add agent system prompts for all 6 agent roles"
```

---

### Task 7: ResearcherAgent Implementation

**Files:**

- Create: `ai_engine/agents/researcher.py`

- [ ] **Step 1: Implement ResearcherAgent**

```python
# ai_engine/agents/researcher.py
"""
Researcher Agent — gathers context before drafting.

Analyzes job descriptions, company signals, and user profiles
to produce research context that shapes the Drafter's output.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "researcher_system.md"


class ResearcherAgent(BaseAgent):
    """Gathers context: industry signals, culture, keywords."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="researcher",
            system_prompt=system_prompt,
            output_schema={},
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()
        jd_text = context.get("jd_text", "")
        job_title = context.get("job_title", "")
        company = context.get("company", "")
        user_profile = context.get("user_profile", {})
        memories = context.get("agent_memories", [])

        prompt = (
            f"Analyze this job posting and user profile to extract research context.\n\n"
            f"Job Title: {job_title}\n"
            f"Company: {company}\n"
            f"Job Description:\n{jd_text[:3000]}\n\n"
            f"User Profile Summary:\n"
            f"- Skills: {', '.join(s.get('name', s) if isinstance(s, dict) else str(s) for s in (user_profile.get('skills') or [])[:20])}\n"
            f"- Experience: {len(user_profile.get('experience') or [])} roles\n"
            f"- Education: {len(user_profile.get('education') or [])} entries\n"
        )
        if memories:
            prompt += f"\nUser Preferences (from memory):\n{memories[:5]}\n"

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={"agent": self.name, "jd_length": len(jd_text)},
        )
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/researcher.py
git commit -m "feat: add ResearcherAgent for pre-draft context gathering"
```

---

### Task 8: CriticAgent Implementation

**Files:**

- Create: `ai_engine/agents/critic.py`

- [ ] **Step 1: Implement CriticAgent**

```python
# ai_engine/agents/critic.py
"""
Critic Agent — quality review and scoring.

Evaluates drafts on impact, clarity, tone match, and completeness.
Decides whether revision is needed based on score thresholds.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "critic_system.md"


class CriticAgent(BaseAgent):
    """Reviews drafts for quality, tone, completeness, consistency."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="critic",
            system_prompt=system_prompt,
            output_schema={},
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        # context can be an AgentResult (from drafter) or a dict
        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context.get("draft", {})

        evaluation_mode = context.get("evaluation_mode", "single") if isinstance(context, dict) else "single"

        if evaluation_mode == "comparative":
            return await self._run_comparative(start, context)

        prompt = (
            f"Evaluate this document draft for quality.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
        )

        quality_scores = result.get("quality_scores", {})
        needs_revision = result.get("needs_revision", False)
        feedback = result.get("feedback", {})

        return self._timed_result(
            start_ns=start,
            content=result,
            quality_scores=quality_scores,
            needs_revision=needs_revision,
            feedback=feedback,
        )

    async def _run_comparative(self, start: int, context: dict) -> AgentResult:
        """Compare multiple document variants (A/B Lab mode)."""
        variants = context.get("variants", [])
        variant_texts = []
        for i, v in enumerate(variants):
            content = v.content if isinstance(v, AgentResult) else v
            variant_texts.append(f"--- Variant {i+1} ---\n{json.dumps(content, indent=2)[:2000]}")

        prompt = (
            f"Compare these {len(variants)} document variants and rank them.\n\n"
            + "\n\n".join(variant_texts)
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt + "\n\nYou are in COMPARATIVE mode. Rank all variants.",
            max_tokens=3000,
            temperature=0.3,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            quality_scores=result.get("quality_scores", {}),
        )
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/critic.py
git commit -m "feat: add CriticAgent with quality scoring and comparative mode"
```

---

### Task 9: OptimizerAgent Implementation

**Files:**

- Create: `ai_engine/agents/optimizer.py`

- [ ] **Step 1: Implement OptimizerAgent**

```python
# ai_engine/agents/optimizer.py
"""
Optimizer Agent — ATS keyword density, readability, quantified impacts.

Analyzes drafts and provides concrete optimization suggestions.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "optimizer_system.md"


class OptimizerAgent(BaseAgent):
    """Optimizes for ATS, readability, structure, and quantification."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="optimizer",
            system_prompt=system_prompt,
            output_schema={},
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context.get("draft", {})

        jd_text = context.get("jd_text", "") if isinstance(context, dict) else ""

        prompt = (
            f"Optimize this document for ATS compatibility and readability.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n\n"
            f"Target Job Description:\n{jd_text[:2000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=3000,
            temperature=0.3,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            suggestions=result.get("suggestions", {}),
            metadata={"agent": self.name},
        )
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/optimizer.py
git commit -m "feat: add OptimizerAgent for ATS and readability optimization"
```

---

### Task 10: FactCheckerAgent Implementation

**Files:**

- Create: `ai_engine/agents/fact_checker.py`

- [ ] **Step 1: Implement FactCheckerAgent**

```python
# ai_engine/agents/fact_checker.py
"""
Fact-Checker Agent — source verification with three-tier classification.

Classifies every claim as verified, enhanced, or fabricated.
Enhancement (strategic reframing) is allowed; fabrication is not.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "fact_checker_system.md"


class FactCheckerAgent(BaseAgent):
    """Cross-references every claim against source profile data."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="fact_checker",
            system_prompt=system_prompt,
            output_schema={},
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        """Accepts a dict with 'draft' (the content to verify) and 'source' (the profile data).
        Also accepts an AgentResult directly (draft content extracted from .content).
        The orchestrator passes: fact_checker.run({"draft": draft, "source": original_context})
        """
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
            user_profile = {}
        else:
            draft_obj = context.get("draft")
            if isinstance(draft_obj, AgentResult):
                draft_content = draft_obj.content
            else:
                draft_content = context.get("content") or context.get("draft", {})
            source_data = context.get("source", context)
            user_profile = source_data.get("user_profile", {})

        prompt = (
            f"Verify every claim in this document against the user's profile data.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n\n"
            f"Source Profile Data:\n{json.dumps(user_profile, indent=2)[:3000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=4000,
            temperature=0.2,
        )

        summary = result.get("summary", {})
        fabricated = result.get("fabricated_claims", [])
        flags = [f"fabricated: {c.get('text', '')}" for c in fabricated]

        return self._timed_result(
            start_ns=start,
            content=result,
            flags=flags,
            metadata={
                "agent": self.name,
                "verified": summary.get("verified", 0),
                "enhanced": summary.get("enhanced", 0),
                "fabricated": summary.get("fabricated", 0),
            },
        )
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/fact_checker.py
git commit -m "feat: add FactCheckerAgent with verified/enhanced/fabricated classification"
```

---

### Task 11: ValidatorAgent (SchemaValidator) Implementation

**Files:**

- Create: `ai_engine/agents/schema_validator.py`

- [ ] **Step 1: Implement ValidatorAgent**

```python
# ai_engine/agents/schema_validator.py
"""
Schema Validator Agent — final validation pass.

Checks schema compliance, format correctness, completeness, and length.
Named schema_validator.py to avoid collision with chains/validator.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "schema_validator_system.md"


class ValidatorAgent(BaseAgent):
    """Schema compliance, format correctness, completeness, length checks."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="validator",
            system_prompt=system_prompt,
            output_schema={},
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context

        prompt = (
            f"Validate this document for schema compliance, format, and completeness.\n\n"
            f"Content:\n{json.dumps(draft_content, indent=2)[:5000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=1500,
            temperature=0.2,
        )

        valid = result.get("valid", True)
        issues = result.get("issues", [])

        # Pass through the content if valid
        if valid:
            result["content"] = draft_content

        return self._timed_result(
            start_ns=start,
            content=result,
            flags=[f"validation_issue: {i}" for i in issues],
            metadata={"agent": self.name, "valid": valid},
        )
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/schema_validator.py
git commit -m "feat: add ValidatorAgent for final schema validation"
```

---

### Task 12: DrafterAgent Implementation

**Files:**

- Create: `ai_engine/agents/drafter.py`

- [ ] **Step 1: Implement DrafterAgent**

```python
# ai_engine/agents/drafter.py
"""
Drafter Agent — wraps existing chains for first-pass generation.

The run() method delegates to the existing chain method (zero modifications).
The revise() method uses AIClient directly with a revision prompt that
includes the original draft + all agent feedback.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_REVISION_PROMPT_PATH = Path(__file__).parent / "prompts" / "drafter_revision.md"

REVISION_SYSTEM_PROMPT = (
    "You are revising a career document based on feedback from quality review agents. "
    "Maintain the document's structure and factual accuracy while addressing all feedback points. "
    "Remove any fabricated claims. Apply keyword suggestions naturally. "
    "Return the revised document in the same format as the original."
)


class DrafterAgent(BaseAgent):
    """Wraps existing chains for first-pass content generation."""

    def __init__(
        self,
        chain: Any,
        method_name: str,
        ai_client: Optional[AIClient] = None,
    ):
        super().__init__(
            name="drafter",
            system_prompt="",
            output_schema={},
            ai_client=ai_client,
        )
        self.chain = chain
        self.method_name = method_name

    async def run(self, context: dict) -> AgentResult:
        """Delegate to existing chain method — NO modifications to chain."""
        start = time.monotonic_ns()
        method = getattr(self.chain, self.method_name)

        # Build kwargs from context, matching chain method signatures
        kwargs = self._build_chain_kwargs(context)
        result = await method(**kwargs)

        # Normalize result to dict
        if isinstance(result, str):
            content = {"html": result}
        elif isinstance(result, tuple):
            content = {"valid": result[0], "details": result[1]}
        elif isinstance(result, dict):
            content = result
        else:
            content = {"result": str(result)}

        return self._timed_result(
            start_ns=start,
            content=content,
            metadata={"agent": self.name, "chain": type(self.chain).__name__, "method": self.method_name},
        )

    async def revise(self, draft: AgentResult, feedback: dict) -> AgentResult:
        """Revise using AIClient directly — does NOT modify existing chains."""
        start = time.monotonic_ns()

        revision_template = ""
        if _REVISION_PROMPT_PATH.exists():
            revision_template = _REVISION_PROMPT_PATH.read_text()

        revision_prompt = (
            f"{revision_template}\n\n"
            f"## Original Draft\n{json.dumps(draft.content, indent=2)[:5000]}\n\n"
            f"## Critic Feedback\n{json.dumps(feedback.get('critic', {}), indent=2)}\n\n"
            f"## Optimizer Suggestions\n{json.dumps(feedback.get('optimizer', {}), indent=2)}\n\n"
            f"## Fact-Check Flags\n{json.dumps(feedback.get('fact_check', []), indent=2)}\n\n"
            f"Return the revised document as JSON with the same structure as the original draft."
        )

        result = await self.ai_client.complete_json(
            system=REVISION_SYSTEM_PROMPT,
            prompt=revision_prompt,
            max_tokens=6000,
            temperature=0.4,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={"agent": self.name, "action": "revision"},
        )

    def _build_chain_kwargs(self, context: dict) -> dict:
        """Map pipeline context to chain method keyword arguments.

        Uses the first matching param name for each context key.
        Example: context["jd_text"] → kwargs["jd_text"] (first in list)
        """
        kwargs = {}
        # Maps context key → list of possible chain parameter names (use first)
        field_map = {
            "user_profile": "user_profile",
            "job_title": "job_title",
            "company": "company",
            "jd_text": "jd_text",
            "gap_analysis": "gap_analysis",
            "resume_text": "resume_text",
            "benchmark_data": "benchmark_data",
            "strengths": "strengths",
            "company_info": "company_info",
            "projects": "projects",
        }
        for ctx_key, param_name in field_map.items():
            if ctx_key in context:
                kwargs[param_name] = context[ctx_key]

        return kwargs
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/drafter.py
git commit -m "feat: add DrafterAgent wrapping existing chains with revision support"
```

---

### Task 13: AgentPipeline Orchestrator

**Files:**

- Create: `ai_engine/agents/orchestrator.py`
- Create: `backend/tests/unit/test_agents/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_agents/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_engine.agents.base import AgentResult
from ai_engine.agents.orchestrator import AgentPipeline, PipelineResult


def _mock_result(content=None, needs_revision=False, flags=None, feedback=None, suggestions=None):
    return AgentResult(
        content=content or {"text": "mock"},
        quality_scores={"impact": 85},
        flags=flags or [],
        latency_ms=1000,
        metadata={"agent": "mock"},
        needs_revision=needs_revision,
        feedback=feedback,
        suggestions=suggestions,
    )


@pytest.fixture
def mock_agents():
    researcher = AsyncMock()
    researcher.run = AsyncMock(return_value=_mock_result({"keywords": ["Python"]}))
    researcher.name = "researcher"

    drafter = AsyncMock()
    drafter.run = AsyncMock(return_value=_mock_result({"html": "<p>CV</p>"}))
    drafter.revise = AsyncMock(return_value=_mock_result({"html": "<p>Revised CV</p>"}))
    drafter.name = "drafter"

    critic = AsyncMock()
    critic.run = AsyncMock(return_value=_mock_result(needs_revision=False))
    critic.name = "critic"

    optimizer = AsyncMock()
    optimizer.run = AsyncMock(return_value=_mock_result(suggestions={"keywords": ["AWS"]}))
    optimizer.name = "optimizer"

    fact_checker = AsyncMock()
    fact_checker.run = AsyncMock(return_value=_mock_result(flags=[]))
    fact_checker.name = "fact_checker"
    # FactCheckerAgent.run() accepts a dict with "draft" and "source" keys

    validator = AsyncMock()
    validator.run = AsyncMock(return_value=_mock_result({"valid": True, "content": {"html": "<p>CV</p>"}}))
    validator.name = "validator"

    return {
        "researcher": researcher,
        "drafter": drafter,
        "critic": critic,
        "optimizer": optimizer,
        "fact_checker": fact_checker,
        "validator": validator,
    }


@pytest.mark.asyncio
async def test_pipeline_executes_all_stages(mock_agents):
    pipeline = AgentPipeline(
        name="cv_generation",
        researcher=mock_agents["researcher"],
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        optimizer=mock_agents["optimizer"],
        fact_checker=mock_agents["fact_checker"],
        validator=mock_agents["validator"],
    )
    result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    assert isinstance(result, PipelineResult)
    assert result.content is not None
    assert result.trace_id is not None
    mock_agents["researcher"].run.assert_awaited_once()
    mock_agents["drafter"].run.assert_awaited_once()
    mock_agents["critic"].run.assert_awaited_once()
    mock_agents["validator"].run.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_triggers_revision_when_critic_says_so(mock_agents):
    mock_agents["critic"].run = AsyncMock(
        return_value=_mock_result(needs_revision=True, feedback={"issue": "tone"})
    )
    pipeline = AgentPipeline(
        name="cv_generation",
        researcher=mock_agents["researcher"],
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        optimizer=mock_agents["optimizer"],
        fact_checker=mock_agents["fact_checker"],
        validator=mock_agents["validator"],
    )
    result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    mock_agents["drafter"].revise.assert_awaited_once()
    assert result.iterations_used == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_orchestrator.py -v 2>&1 | head -10`
Expected: FAIL

- [ ] **Step 3: Implement AgentPipeline and PipelineResult**

```python
# ai_engine/agents/orchestrator.py
"""
Agent Pipeline Orchestrator — manages multi-stage agent execution.

Execution model:
  Stage 1 (sequential): Researcher gathers context
  Stage 2 (uses research): Drafter generates first pass
  Stage 3 (parallel): Critic + Optimizer + Fact-Checker via asyncio.gather
  Stage 4 (if needed): Drafter revision with merged feedback
  Stage 5: Validator
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import uuid4

import structlog

from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.agents.lock import PipelineLockManager
from ai_engine.agents.trace import AgentTracer

logger = structlog.get_logger("hirestack.agents.orchestrator")


@dataclass
class PipelineResult:
    """Final output of a complete agent pipeline run."""
    content: dict
    quality_scores: dict
    optimization_report: dict
    fact_check_report: dict
    iterations_used: int
    total_latency_ms: int
    trace_id: str


def _merge_optimizations(
    draft_content: dict, optimizer_content: dict, fact_check_content: dict
) -> dict:
    """Merge optimizer suggestions and fact-check fixes into draft.

    - Attaches optimizer keyword analysis and suggestions for downstream use
    - Removes any fabricated claims identified by the fact-checker
    - Returns a new dict (does not mutate inputs)
    """
    merged = dict(draft_content)

    # Attach optimizer report for quality display
    merged["_optimization_report"] = {
        "keyword_analysis": optimizer_content.get("keyword_analysis", {}),
        "readability_score": optimizer_content.get("readability_score"),
        "suggestions": optimizer_content.get("suggestions", []),
    }

    # Attach fact-check report
    merged["_fact_check_report"] = {
        "summary": fact_check_content.get("summary", {}),
        "claims": fact_check_content.get("claims", []),
    }

    # Remove fabricated claims from HTML content if present
    fabricated = fact_check_content.get("fabricated_claims", [])
    if fabricated and "html" in merged:
        html = merged["html"]
        for claim in fabricated:
            text = claim.get("text", "")
            if text and text in html:
                html = html.replace(text, "")
        merged["html"] = html

    return merged


class AgentPipeline:
    """Orchestrates multi-stage agent execution with parallel stages."""

    def __init__(
        self,
        name: str,
        researcher: Optional[BaseAgent] = None,
        drafter: Any = None,
        critic: Optional[BaseAgent] = None,
        optimizer: Optional[BaseAgent] = None,
        fact_checker: Optional[BaseAgent] = None,
        validator: Optional[BaseAgent] = None,
        max_iterations: int = 2,
        lock_manager: Optional[PipelineLockManager] = None,
        on_stage_update: Optional[Callable] = None,
    ):
        self.name = name
        self.researcher = researcher
        self.drafter = drafter
        self.critic = critic
        self.optimizer = optimizer
        self.fact_checker = fact_checker
        self.validator = validator
        self.max_iterations = max_iterations
        self.lock_manager = lock_manager or PipelineLockManager()
        self.on_stage_update = on_stage_update  # SSE callback

    async def execute(self, context: dict) -> PipelineResult:
        pipeline_id = str(uuid4())
        user_id = context.get("user_id", "unknown")
        tracer = AgentTracer(pipeline_id, self.name, user_id)

        async with self.lock_manager.acquire(user_id, self.name, pipeline_id):
            enriched_context = dict(context)

            # Stage 1: Research (sequential — Drafter needs this output)
            if self.researcher:
                await self._emit("researcher", "running")
                research = await self.researcher.run(context)
                tracer.record_stage("researcher", research.latency_ms, "completed")
                enriched_context["research"] = research.content
                await self._emit("researcher", "completed", research.latency_ms)

            # Stage 2: Draft (uses research context)
            await self._emit("drafter", "running")
            draft = await self.drafter.run(enriched_context)
            tracer.record_stage("drafter", draft.latency_ms, "completed")
            await self._emit("drafter", "completed", draft.latency_ms)

            # Stage 3: Parallel critique + optimize + fact-check
            parallel_agents = []
            parallel_names = []
            if self.critic:
                parallel_agents.append(self.critic.run(draft))
                parallel_names.append("critic")
            if self.optimizer:
                parallel_agents.append(self.optimizer.run(draft))
                parallel_names.append("optimizer")
            if self.fact_checker:
                parallel_agents.append(self.fact_checker.run({"draft": draft, "source": context}))
                parallel_names.append("fact_checker")

            for name in parallel_names:
                await self._emit(name, "running")

            parallel_results = await asyncio.gather(*parallel_agents) if parallel_agents else []

            # Map results back to named variables
            critic_result = optimizer_result = fact_check_result = None
            for name, result in zip(parallel_names, parallel_results):
                tracer.record_stage(name, result.latency_ms, "completed")
                await self._emit(name, "completed", result.latency_ms)
                if name == "critic":
                    critic_result = result
                elif name == "optimizer":
                    optimizer_result = result
                elif name == "fact_checker":
                    fact_check_result = result

            # Stage 4: Revise if critic rejects
            iterations_used = 0
            if critic_result and critic_result.needs_revision and hasattr(self.drafter, 'revise'):
                await self._emit("drafter", "running", message="Revising based on feedback...")
                draft = await self.drafter.revise(
                    draft,
                    feedback={
                        "critic": critic_result.feedback or {},
                        "optimizer": optimizer_result.suggestions if optimizer_result else {},
                        "fact_check": fact_check_result.flags if fact_check_result else [],
                    },
                )
                tracer.record_stage("drafter_revision", draft.latency_ms, "completed")
                await self._emit("drafter", "completed", draft.latency_ms)
                iterations_used = 1
            elif optimizer_result or fact_check_result:
                # Apply optimizer suggestions and fact-check fixes without full re-generation
                draft = AgentResult(
                    content=_merge_optimizations(
                        draft.content,
                        optimizer_result.content if optimizer_result else {},
                        fact_check_result.content if fact_check_result else {},
                    ),
                    quality_scores=critic_result.quality_scores if critic_result else {},
                    flags=fact_check_result.flags if fact_check_result else [],
                    latency_ms=draft.latency_ms,
                    metadata=draft.metadata,
                )

            # Stage 5: Validate
            if self.validator:
                await self._emit("validator", "running")
                validation = await self.validator.run(draft)
                tracer.record_stage("validator", validation.latency_ms, "completed")
                await self._emit("validator", "completed", validation.latency_ms)
            else:
                validation = draft

            total_latency = sum(s["latency_ms"] for s in tracer.stages)

            return PipelineResult(
                content=validation.content,
                quality_scores=critic_result.quality_scores if critic_result else {},
                optimization_report=optimizer_result.content if optimizer_result else {},
                fact_check_report=fact_check_result.content if fact_check_result else {},
                iterations_used=iterations_used,
                total_latency_ms=total_latency,
                trace_id=pipeline_id,
            )

    async def _emit(
        self, stage: str, status: str, latency_ms: int = 0, message: str = ""
    ) -> None:
        """Emit SSE event via callback if registered."""
        if self.on_stage_update:
            try:
                await self.on_stage_update({
                    "pipeline_name": self.name,
                    "stage": stage,
                    "status": status,
                    "latency_ms": latency_ms,
                    "message": message,
                })
            except Exception as e:
                logger.warning("sse_emit_failed", stage=stage, error=str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/unit/test_agents/test_orchestrator.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add ai_engine/agents/orchestrator.py backend/tests/unit/test_agents/test_orchestrator.py
git commit -m "feat: add AgentPipeline orchestrator with parallel stages and SSE"
```

---

### Task 14: Update agents/**init**.py — Export All

**Files:**

- Modify: `ai_engine/agents/__init__.py`

- [ ] **Step 1: Update exports**

```python
# ai_engine/agents/__init__.py
"""HireStack AI Agent Swarm Framework."""
from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.orchestrator import AgentPipeline, PipelineResult
from ai_engine.agents.drafter import DrafterAgent
from ai_engine.agents.critic import CriticAgent
from ai_engine.agents.optimizer import OptimizerAgent
from ai_engine.agents.fact_checker import FactCheckerAgent
from ai_engine.agents.researcher import ResearcherAgent
from ai_engine.agents.schema_validator import ValidatorAgent
from ai_engine.agents.memory import AgentMemory
from ai_engine.agents.trace import AgentTracer
from ai_engine.agents.lock import PipelineLockManager

__all__ = [
    "BaseAgent",
    "AgentResult",
    "AgentPipeline",
    "PipelineResult",
    "DrafterAgent",
    "CriticAgent",
    "OptimizerAgent",
    "FactCheckerAgent",
    "ResearcherAgent",
    "ValidatorAgent",
    "AgentMemory",
    "AgentTracer",
    "PipelineLockManager",
]
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/__init__.py
git commit -m "feat: export all agent classes from agents package"
```

---

### Task 15: IBM Plex Mono Font Integration

**Files:**

- Create: `frontend/src/fonts/ibm-plex-mono.ts`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Create font configuration**

```typescript
// frontend/src/fonts/ibm-plex-mono.ts
import { IBM_Plex_Mono } from "next/font/google";

export const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});
```

- [ ] **Step 2: Add font variable to layout.tsx**

In `frontend/src/app/layout.tsx`, add the IBM Plex Mono font variable to the `<body>` className alongside the existing Inter font:

```tsx
import { ibmPlexMono } from "@/fonts/ibm-plex-mono";

// In the body tag, add ibmPlexMono.variable:
<body className={`${inter.variable} ${ibmPlexMono.variable} font-sans antialiased`}>
```

- [ ] **Step 3: Add font-mono utility to tailwind config**

In `tailwind.config.ts` (or `tailwind.config.js`), add under `theme.extend.fontFamily`:

```js
fontFamily: {
  mono: ['var(--font-mono)', 'IBM Plex Mono', 'monospace'],
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/fonts/ibm-plex-mono.ts frontend/src/app/layout.tsx
git commit -m "feat: add IBM Plex Mono dual-font system"
```

---

### Task 16: Shared Feedback Components

**Files:**

- Create: `frontend/src/components/feedback/error-card.tsx`
- Create: `frontend/src/components/feedback/loading-skeleton.tsx`
- Create: `frontend/src/components/feedback/retry-button.tsx`

- [ ] **Step 1: Create ErrorCard component**

```tsx
// frontend/src/components/feedback/error-card.tsx
"use client";

import { AlertCircle } from "lucide-react";
import { RetryButton } from "./retry-button";

interface ErrorCardProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorCard({ title = "Something went wrong", message, onRetry, className = "" }: ErrorCardProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`rounded-xl border border-destructive/30 bg-destructive/5 p-4 ${className}`}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-destructive text-sm">{title}</p>
          <p className="text-sm text-muted-foreground mt-1">{message}</p>
          {onRetry && <RetryButton onClick={onRetry} className="mt-3" />}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create LoadingSkeleton component**

```tsx
// frontend/src/components/feedback/loading-skeleton.tsx
"use client";

import { cn } from "@/lib/utils";

interface LoadingSkeletonProps {
  lines?: number;
  className?: string;
}

export function LoadingSkeleton({ lines = 3, className = "" }: LoadingSkeletonProps) {
  return (
    <div aria-live="polite" aria-label="Loading content" className={cn("space-y-3", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-muted animate-pulse"
          style={{ width: `${85 - i * 15}%` }}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create RetryButton component**

```tsx
// frontend/src/components/feedback/retry-button.tsx
"use client";

import { useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface RetryButtonProps {
  onClick: () => void;
  className?: string;
  maxRetries?: number;
}

export function RetryButton({ onClick, className = "", maxRetries = 3 }: RetryButtonProps) {
  const [retryCount, setRetryCount] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);

  const handleRetry = useCallback(() => {
    if (retryCount >= maxRetries || isRetrying) return;
    setIsRetrying(true);
    setRetryCount((c) => c + 1);
    // Exponential backoff: 1s, 2s, 4s — delay before calling onClick
    const delay = Math.pow(2, retryCount) * 1000;
    setTimeout(() => {
      onClick();
      setIsRetrying(false);
    }, delay);
  }, [retryCount, maxRetries, onClick, isRetrying]);

  const attemptsLeft = maxRetries - retryCount;

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleRetry}
      disabled={isRetrying || attemptsLeft <= 0}
      className={className}
    >
      <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isRetrying ? "animate-spin" : ""}`} />
      {isRetrying ? "Retrying..." : attemptsLeft > 0 ? "Try again" : "Max retries reached"}
    </Button>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/feedback/
git commit -m "feat: add shared ErrorCard, LoadingSkeleton, and RetryButton components"
```

---

### Task 17: Command Palette Skeleton

**Files:**

- Create: `frontend/src/components/command-palette/use-commands.ts`
- Create: `frontend/src/components/command-palette/command-palette.tsx`

- [ ] **Step 1: Install cmdk**

Run: `cd "/Users/balabollineni/HireStack AI/frontend" && npm install cmdk@1`

- [ ] **Step 2: Create command registry hook**

```typescript
// frontend/src/components/command-palette/use-commands.ts
"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

export interface Command {
  id: string;
  label: string;
  category: "recent" | "actions" | "navigate";
  shortcut?: string;
  onSelect: () => void;
  icon?: string;
}

export function useCommands(): Command[] {
  const router = useRouter();

  return useMemo(
    () => [
      // Actions
      { id: "new-app", label: "New Application", category: "actions" as const, shortcut: "⌘N", onSelect: () => router.push("/new"), },
      // Navigation
      { id: "nav-dashboard", label: "Dashboard", category: "navigate" as const, shortcut: "⌘1", onSelect: () => router.push("/dashboard"), },
      { id: "nav-evidence", label: "Evidence Vault", category: "navigate" as const, shortcut: "⌘2", onSelect: () => router.push("/evidence"), },
      { id: "nav-analytics", label: "Career Analytics", category: "navigate" as const, shortcut: "⌘3", onSelect: () => router.push("/career-analytics"), },
      { id: "nav-ats", label: "ATS Scanner", category: "navigate" as const, onSelect: () => router.push("/ats-scanner"), },
      { id: "nav-interview", label: "Interview Prep", category: "navigate" as const, onSelect: () => router.push("/interview"), },
      { id: "nav-salary", label: "Salary Coach", category: "navigate" as const, onSelect: () => router.push("/salary"), },
      { id: "nav-jobs", label: "Job Board", category: "navigate" as const, onSelect: () => router.push("/job-board"), },
      { id: "nav-learning", label: "Daily Learn", category: "navigate" as const, onSelect: () => router.push("/learning"), },
      { id: "nav-ab-lab", label: "A/B Doc Lab", category: "navigate" as const, onSelect: () => router.push("/ab-lab"), },
      { id: "nav-api-keys", label: "API Keys", category: "navigate" as const, onSelect: () => router.push("/api-keys"), },
    ],
    [router]
  );
}
```

- [ ] **Step 3: Create CommandPalette component**

```tsx
// frontend/src/components/command-palette/command-palette.tsx
"use client";

import { useEffect, useState } from "react";
import { Command as Cmdk } from "cmdk";
import { useCommands } from "./use-commands";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const commands = useCommands();

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  if (!open) return null;

  const categories = ["recent", "actions", "navigate"] as const;

  return (
    <div className="fixed inset-0 z-50" onClick={() => setOpen(false)}>
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" />
      <div className="fixed top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <Cmdk
          className="glass-panel rounded-xl border border-white/20 shadow-2xl overflow-hidden"
          label="Command palette"
        >
          <Cmdk.Input
            placeholder="Type a command or search..."
            className="w-full px-4 py-3 text-sm bg-transparent border-b border-white/10 outline-none placeholder:text-muted-foreground"
            autoFocus
          />
          <Cmdk.List className="max-h-72 overflow-y-auto p-2">
            <Cmdk.Empty className="px-4 py-6 text-sm text-muted-foreground text-center">
              No results found.
            </Cmdk.Empty>
            {categories.map((cat) => {
              const items = commands.filter((c) => c.category === cat);
              if (items.length === 0) return null;
              return (
                <Cmdk.Group
                  key={cat}
                  heading={cat.charAt(0).toUpperCase() + cat.slice(1)}
                  className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground"
                >
                  {items.map((cmd) => (
                    <Cmdk.Item
                      key={cmd.id}
                      value={cmd.label}
                      onSelect={() => {
                        cmd.onSelect();
                        setOpen(false);
                      }}
                      className="flex items-center justify-between px-3 py-2 text-sm rounded-lg cursor-pointer aria-selected:bg-primary/10 aria-selected:text-primary"
                    >
                      <span>{cmd.label}</span>
                      {cmd.shortcut && (
                        <kbd className="font-mono text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </Cmdk.Item>
                  ))}
                </Cmdk.Group>
              );
            })}
          </Cmdk.List>
        </Cmdk>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add CommandPalette to app shell**

In `frontend/src/components/app-shell.tsx`, add the CommandPalette import and render it inside the layout:

```tsx
import { CommandPalette } from "@/components/command-palette/command-palette";

// Inside the component's return, add before the closing fragment/div:
<CommandPalette />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/command-palette/ frontend/package.json frontend/package-lock.json
git commit -m "feat: add Cmd+K command palette with cmdk"
```

---

### Task 18: Add Micro-Animation Keyframes

**Files:**

- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Add new keyframes to globals.css**

Append these keyframes to the existing `@keyframes` section in `globals.css`:

```css
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-4px); }
  40% { transform: translateX(4px); }
  60% { transform: translateX(-3px); }
  80% { transform: translateX(2px); }
}

@keyframes digit-flip {
  0% { transform: translateY(100%); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
}

@keyframes check-pop {
  0% { transform: scale(0); opacity: 0; }
  60% { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes bounce-sm {
  0%, 100% { transform: translateY(0); }
  40% { transform: translateY(-2px); }
  60% { transform: translateY(1px); }
}
```

And add the corresponding utility classes:

```css
.animate-shake { animation: shake 0.3s ease-out; }
.animate-digit-flip { animation: digit-flip 0.6s ease-out; }
.animate-check-pop { animation: check-pop 0.3s ease-out; }
.animate-bounce-sm { animation: bounce-sm 0.4s ease-out; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat: add micro-animation keyframes (shake, digit-flip, check-pop, bounce-sm)"
```

---

### Task 19: Install pytest-asyncio Dependency

**Files:**

- Modify: backend dependencies

- [ ] **Step 1: Install pytest-asyncio**

Run: `cd "/Users/balabollineni/HireStack AI" && pip install pytest-asyncio`

- [ ] **Step 2: Create pytest.ini or pyproject.toml config**

Add to `backend/pytest.ini` (create if needed):

```ini
[pytest]
asyncio_mode = auto
testpaths = backend/tests
pythonpath = .
```

- [ ] **Step 3: Run all agent tests**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/pytest.ini
git commit -m "chore: add pytest config with asyncio auto mode"
```

---

### Task 20: JSON Schemas for AI Output Validation (Phase 1 — per spec)

**Files:**

- Create: `ai_engine/schemas/profile_schema.json`
- Create: `ai_engine/schemas/benchmark_schema.json`
- Create: `ai_engine/schemas/gap_analysis_schema.json`
- Create: `ai_engine/schemas/cv_schema.json`
- Create: `ai_engine/schemas/cover_letter_schema.json`

- [ ] **Step 1: Create profile schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["name", "skills", "experience"],
  "properties": {
    "name": { "type": "string", "minLength": 1 },
    "title": { "type": "string" },
    "summary": { "type": "string" },
    "contact_info": { "type": "object" },
    "skills": {
      "type": "array",
      "items": { "type": ["string", "object"] }
    },
    "experience": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["title"],
        "properties": {
          "title": { "type": "string" },
          "company": { "type": "string" },
          "start_date": { "type": "string" },
          "end_date": { "type": "string" },
          "description": { "type": "string" }
        }
      }
    },
    "education": { "type": "array" },
    "certifications": { "type": "array" },
    "projects": { "type": "array" },
    "languages": { "type": "array" },
    "achievements": { "type": "array" }
  }
}
```

- [ ] **Step 2: Create benchmark schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["ideal_candidate"],
  "properties": {
    "ideal_candidate": {
      "type": "object",
      "properties": {
        "title": { "type": "string" },
        "experience_years": { "type": "number" },
        "required_skills": { "type": "array", "items": { "type": "string" } },
        "preferred_skills": { "type": "array", "items": { "type": "string" } },
        "education": { "type": "array" },
        "certifications": { "type": "array" }
      }
    }
  }
}
```

- [ ] **Step 3: Create gap analysis schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["compatibility_score"],
  "properties": {
    "compatibility_score": { "type": "number", "minimum": 0, "maximum": 100 },
    "readiness_level": { "type": "string" },
    "category_scores": { "type": "object" },
    "skill_gaps": { "type": "array" },
    "experience_gaps": { "type": "array" },
    "strengths": { "type": "array" },
    "recommendations": { "type": "array" },
    "quick_wins": { "type": "array" },
    "interview_readiness": { "type": "object" }
  }
}
```

- [ ] **Step 4: Create CV and cover letter schemas**

```json
// cv_schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["html"],
  "properties": {
    "html": { "type": "string", "minLength": 100 }
  }
}
```

```json
// cover_letter_schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["html"],
  "properties": {
    "html": { "type": "string", "minLength": 50 }
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add ai_engine/schemas/
git commit -m "feat: add JSON schemas for AI output validation"
```

---

### Task 21: Pipeline Factory — Create Pipelines for Each Feature

**Files:**

- Create: `ai_engine/agents/pipelines.py`

- [ ] **Step 1: Implement pipeline factory**

```python
# ai_engine/agents/pipelines.py
"""
Pipeline factory — creates pre-configured pipelines for each feature.

Each pipeline maps to a row in the per-feature configuration table (spec Section 2.9).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from ai_engine.agents.orchestrator import AgentPipeline
from ai_engine.agents.researcher import ResearcherAgent
from ai_engine.agents.drafter import DrafterAgent
from ai_engine.agents.critic import CriticAgent
from ai_engine.agents.optimizer import OptimizerAgent
from ai_engine.agents.fact_checker import FactCheckerAgent
from ai_engine.agents.schema_validator import ValidatorAgent
from ai_engine.agents.lock import PipelineLockManager
from ai_engine.client import AIClient, get_ai_client


# Shared lock manager (singleton per process)
_lock_manager = PipelineLockManager()


def create_pipeline(
    name: str,
    chain: Any,
    method_name: str,
    use_researcher: bool = True,
    use_critic: bool = True,
    use_optimizer: bool = True,
    use_fact_checker: bool = True,
    max_iterations: int = 2,
    on_stage_update: Optional[Callable] = None,
    ai_client: Optional[AIClient] = None,
) -> AgentPipeline:
    """Create a configured AgentPipeline for a specific feature."""
    client = ai_client or get_ai_client()

    return AgentPipeline(
        name=name,
        researcher=ResearcherAgent(ai_client=client) if use_researcher else None,
        drafter=DrafterAgent(chain=chain, method_name=method_name, ai_client=client),
        critic=CriticAgent(ai_client=client) if use_critic else None,
        optimizer=OptimizerAgent(ai_client=client) if use_optimizer else None,
        fact_checker=FactCheckerAgent(ai_client=client) if use_fact_checker else None,
        validator=ValidatorAgent(ai_client=client),
        max_iterations=max_iterations,
        lock_manager=_lock_manager,
        on_stage_update=on_stage_update,
    )


# ── Pre-configured pipeline creators ──────────────────────────────────

def resume_parse_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import RoleProfilerChain
    chain = RoleProfilerChain(client)
    return create_pipeline(
        "resume_parse", chain, "parse_resume",
        use_optimizer=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )


def benchmark_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import BenchmarkBuilderChain
    chain = BenchmarkBuilderChain(client)
    return create_pipeline(
        "benchmark", chain, "create_ideal_profile",
        max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )


def gap_analysis_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import GapAnalyzerChain
    chain = GapAnalyzerChain(client)
    return create_pipeline(
        "gap_analysis", chain, "analyze_gaps",
        use_researcher=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )


def cv_generation_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "cv_generation", chain, "generate_tailored_cv",
        max_iterations=2,
        ai_client=client, on_stage_update=on_stage_update,
    )


def cover_letter_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "cover_letter", chain, "generate_tailored_cover_letter",
        max_iterations=2,
        ai_client=client, on_stage_update=on_stage_update,
    )


def personal_statement_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "personal_statement", chain, "generate_tailored_personal_statement",
        use_researcher=False, use_optimizer=False, use_fact_checker=False,
        max_iterations=2,
        ai_client=client, on_stage_update=on_stage_update,
    )


def portfolio_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "portfolio", chain, "generate_tailored_portfolio",
        use_researcher=False, use_critic=False, use_fact_checker=False,
        max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )
```

- [ ] **Step 2: Update agents **init**.py**

Add to `ai_engine/agents/__init__.py`:

```python
from ai_engine.agents.pipelines import (
    create_pipeline,
    resume_parse_pipeline,
    benchmark_pipeline,
    gap_analysis_pipeline,
    cv_generation_pipeline,
    cover_letter_pipeline,
    personal_statement_pipeline,
    portfolio_pipeline,
)
```

- [ ] **Step 3: Commit**

```bash
git add ai_engine/agents/pipelines.py ai_engine/agents/__init__.py
git commit -m "feat: add pipeline factory with pre-configured pipelines for all core features"
```

---

**End of Chunk 1 — Phase 1: Agent Framework Foundation (Tasks 1-21)**

---

## Chunk 2: Phase 2 — Tier 1 Core Pipeline (Backend Service Integration + SSE)

This chunk wires the agent pipelines into existing backend services and enhances the SSE streaming endpoint for real-time agent progress.

### File Structure (modifications)

```
backend/app/services/
├── profile.py              # MODIFY: wrap RoleProfilerChain with agent pipeline
├── benchmark.py            # MODIFY: wrap BenchmarkBuilderChain with agent pipeline
├── gap.py                  # MODIFY: wrap GapAnalyzerChain with agent pipeline
├── document.py             # MODIFY: wrap DocumentGeneratorChain with agent pipeline
├── export.py               # MODIFY: add quality_report.pdf, python-docx backend DOCX

backend/app/api/routes/
├── generate.py             # MODIFY: enhanced SSE with agent_status events
├── profile.py              # MODIFY: standardized response format
├── benchmark.py            # MODIFY: standardized response format + validation
├── gaps.py                 # MODIFY: standardized response format
```

---

### Task 22: Enhanced SSE Generate Endpoint with Agent Pipeline

**Files:**

- Modify: `backend/app/api/routes/generate.py`

This is the most critical integration point. The existing `/api/generate/pipeline/stream` endpoint runs chains directly. We replace the chain calls with agent pipeline calls while keeping the SSE event format compatible (adding new `agent_status` events alongside existing `progress` events).

- [ ] **Step 1: Add agent pipeline imports to generate.py**

At the top of `backend/app/api/routes/generate.py`, add after the existing chain imports:

```python
from ai_engine.agents.pipelines import (
    resume_parse_pipeline,
    benchmark_pipeline,
    gap_analysis_pipeline,
    cv_generation_pipeline,
    cover_letter_pipeline,
    personal_statement_pipeline,
    portfolio_pipeline,
)
from ai_engine.agents.orchestrator import PipelineResult
from ai_engine.agents.trace import AgentTracer
```

- [ ] **Step 2: Create SSE helper for agent events**

Add after the existing `_sse()` helper in `generate.py`:

```python
def _agent_sse(pipeline_name: str, stage: str, status: str, latency_ms: int = 0, message: str = "", quality_scores: dict | None = None) -> str:
    """Emit an agent_status SSE event."""
    data = {
        "pipeline_name": pipeline_name,
        "stage": stage,
        "status": status,
        "latency_ms": latency_ms,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if quality_scores:
        data["quality_scores"] = quality_scores
    return f"event: agent_status\ndata: {json.dumps(data)}\n\n"
```

Also add import at top:

```python
from datetime import datetime, timezone
```

- [ ] **Step 3: Create agent-powered streaming generator**

Add a new streaming generator function alongside the existing one. The existing `_stream_pipeline` function is preserved as fallback. The new function uses agent pipelines:

```python
async def _stream_agent_pipeline(
    req: PipelineRequest,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """Agent-powered pipeline with per-stage SSE events."""
    from ai_engine.client import get_ai_client
    from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
    from ai_engine.chains.career_consultant import CareerConsultantChain

    ai = get_ai_client()

    # SSE callback that emits agent_status events
    async def emit(event: dict):
        # This is called by AgentPipeline._emit() during execution
        pass  # Events are collected and yielded below

    events_queue: list[str] = []

    async def stage_callback(event: dict):
        events_queue.append(_agent_sse(
            pipeline_name=event.get("pipeline_name", ""),
            stage=event.get("stage", ""),
            status=event.get("status", ""),
            latency_ms=event.get("latency_ms", 0),
            message=event.get("message", ""),
        ))

    company = req.company or "the company"

    try:
        # ── Phase 1: Resume Parse (agent pipeline) ────────────────
        yield _sse("progress", {"phase": "parsing", "step": 1, "totalSteps": 6, "progress": 10, "message": "Analyzing resume..."})

        context = {
            "user_id": user_id,
            "resume_text": req.resume_text,
            "job_title": req.job_title,
            "company": company,
            "jd_text": req.jd_text,
        }

        # Parse resume via agent pipeline
        if req.resume_text.strip():
            parse_pipeline = resume_parse_pipeline(ai_client=ai, on_stage_update=stage_callback)
            parse_result = await parse_pipeline.execute(context)
            user_profile = parse_result.content
            for ev in events_queue:
                yield ev
            events_queue.clear()
        else:
            user_profile = {}

        # Benchmark via agent pipeline
        yield _sse("progress", {"phase": "benchmarking", "step": 2, "totalSteps": 6, "progress": 25, "message": "Building benchmark..."})
        bench_pipeline = benchmark_pipeline(ai_client=ai, on_stage_update=stage_callback)
        bench_result = await bench_pipeline.execute({
            **context,
            "user_profile": user_profile,
        })
        benchmark_data = bench_result.content
        for ev in events_queue:
            yield ev
        events_queue.clear()

        # Benchmark CV HTML (not agent-powered, keep existing)
        benchmark_cv_html = ""
        try:
            bench_chain = BenchmarkBuilderChain(ai)
            benchmark_cv_html = await bench_chain.create_benchmark_cv_html(
                user_profile=user_profile,
                benchmark_data=benchmark_data,
                job_title=req.job_title,
                company=company,
                jd_text=req.jd_text,
            )
        except Exception as bcv_err:
            logger.warning("pipeline.benchmark_cv_failed", error=str(bcv_err))

        # Keywords
        ideal_skills = benchmark_data.get("ideal_skills", [])
        keywords = [s.get("name", "") for s in ideal_skills if isinstance(s, dict) and s.get("name")]
        if not keywords:
            keywords = _extract_keywords_from_jd(req.jd_text)

        # ── Phase 2: Gap Analysis (agent pipeline) ────────────────
        yield _sse("progress", {"phase": "gap_analysis", "step": 3, "totalSteps": 6, "progress": 40, "message": "Analyzing gaps..."})
        gap_pipe = gap_analysis_pipeline(ai_client=ai, on_stage_update=stage_callback)
        gap_result = await gap_pipe.execute({
            **context,
            "user_profile": user_profile,
            "benchmark_data": benchmark_data,
        })
        gap_analysis = gap_result.content
        for ev in events_queue:
            yield ev
        events_queue.clear()

        # ── Phase 3: Documents (agent pipelines — CV + CL parallel) ──
        yield _sse("progress", {"phase": "documents", "step": 4, "totalSteps": 6, "progress": 55, "message": "Generating documents..."})

        doc_context = {
            **context,
            "user_profile": user_profile,
            "gap_analysis": gap_analysis,
        }

        cv_pipe = cv_generation_pipeline(ai_client=ai, on_stage_update=stage_callback)
        cl_pipe = cover_letter_pipeline(ai_client=ai, on_stage_update=stage_callback)
        consultant = CareerConsultantChain(ai)

        cv_result, cl_result, roadmap = await asyncio.gather(
            cv_pipe.execute(doc_context),
            cl_pipe.execute(doc_context),
            consultant.generate_roadmap(gap_analysis, user_profile, req.job_title, company),
            return_exceptions=True,
        )
        for ev in events_queue:
            yield ev
        events_queue.clear()

        # Extract results (handle exceptions from gather)
        cv_html = cv_result.content.get("html", "") if isinstance(cv_result, PipelineResult) else ""
        cl_html = cl_result.content.get("html", "") if isinstance(cl_result, PipelineResult) else ""
        if isinstance(roadmap, Exception):
            logger.error("pipeline.roadmap_failed", error=str(roadmap))
            roadmap = {}

        # Quality data from agent pipelines
        cv_quality = cv_result.quality_scores if isinstance(cv_result, PipelineResult) else {}
        cv_fact_check = cv_result.fact_check_report if isinstance(cv_result, PipelineResult) else {}
        cl_quality = cl_result.quality_scores if isinstance(cl_result, PipelineResult) else {}

        # ── Phase 4: PS + Portfolio (agent pipelines) ─────────────
        yield _sse("progress", {"phase": "additional_docs", "step": 5, "totalSteps": 6, "progress": 75, "message": "Generating personal statement & portfolio..."})

        ps_pipe = personal_statement_pipeline(ai_client=ai, on_stage_update=stage_callback)
        port_pipe = portfolio_pipeline(ai_client=ai, on_stage_update=stage_callback)

        ps_result, portfolio_result = await asyncio.gather(
            ps_pipe.execute(doc_context),
            port_pipe.execute(doc_context),
            return_exceptions=True,
        )
        for ev in events_queue:
            yield ev
        events_queue.clear()

        ps_html = ps_result.content.get("html", "") if isinstance(ps_result, PipelineResult) else ""
        portfolio_html = portfolio_result.content.get("html", "") if isinstance(portfolio_result, PipelineResult) else ""

        # ── Phase 6: Format response ──────────────────────────────
        yield _sse("progress", {"phase": "formatting", "step": 6, "totalSteps": 6, "progress": 95, "message": "Preparing results..."})

        response = _format_response(
            benchmark_data=benchmark_data,
            gap_analysis=gap_analysis,
            roadmap=roadmap if isinstance(roadmap, dict) else {},
            cv_html=cv_html,
            cl_html=cl_html,
            ps_html=ps_html,
            portfolio_html=portfolio_html,
            benchmark_cv_html=benchmark_cv_html,
            keywords=keywords,
        )

        # Add quality metadata from agent pipelines
        response["meta"] = {
            "quality_scores": {
                "cv": cv_quality,
                "cover_letter": cl_quality,
            },
            "fact_check": cv_fact_check,
            "agent_powered": True,
        }

        # Emit pipeline_complete event
        yield f"event: pipeline_complete\ndata: {json.dumps({'quality_scores': cv_quality, 'fact_check_summary': cv_fact_check.get('summary', {})})}\n\n"

        yield _sse("complete", response)

    except Exception as exc:
        classified = _classify_ai_error(exc)
        if classified:
            yield _sse("error", {
                "code": classified.get("code", 500),
                "message": classified["message"],
                "retry_after_seconds": classified.get("retry_after_seconds"),
            })
        else:
            logger.error("agent_pipeline.error", error=str(exc), traceback=traceback.format_exc())
            yield f"event: pipeline_error\ndata: {json.dumps({'error_code': 'PIPELINE_FAILED', 'message': 'AI generation temporarily unavailable', 'retryable': True})}\n\n"
            yield _sse("error", {"code": 500, "message": str(exc)[:200]})
```

- [ ] **Step 4: Wire the new streaming endpoint**

Replace the existing streaming endpoint to use the agent-powered generator:

```python
@router.post("/pipeline/stream")
@limiter.limit("5/minute")
async def generate_pipeline_stream(
    request: Request,
    req: PipelineRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """SSE streaming endpoint with agent pipeline progress."""
    user_id = current_user.get("id") or current_user.get("sub", "")
    _validate_uuid(user_id, "user_id")

    return StreamingResponse(
        _stream_agent_pipeline(req, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/generate.py
git commit -m "feat: wire agent pipelines into SSE streaming endpoint with agent_status events"
```

---

### Task 23: Standardized Response Format Helper

**Files:**

- Create: `backend/app/api/response.py`

- [ ] **Step 1: Create standardized response helper**

```python
# backend/app/api/response.py
"""Standardized API response format for all endpoints."""
from typing import Any, Optional


def success_response(
    data: Any,
    meta: Optional[dict] = None,
) -> dict:
    """Wrap data in standardized success response."""
    resp = {"success": True, "data": data}
    if meta:
        resp["meta"] = meta
    return resp


def error_response(
    code: str,
    message: str,
    details: Optional[dict] = None,
    status_code: int = 400,
) -> dict:
    """Build standardized error response body.
    Note: Caller still needs to raise HTTPException with the status_code.
    """
    resp: dict = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        resp["error"]["details"] = details
    return resp
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/response.py
git commit -m "feat: add standardized success_response/error_response helpers"
```

---

### Task 24: Backend Input Validation and Response Format Fixes

**Files:**

- Modify: `backend/app/services/profile.py` (add input size validation)
- Modify: `backend/app/services/benchmark.py` (validate JD non-empty)
- Modify: `backend/app/services/gap.py` (fix N+1 query)
- Modify: `backend/app/api/routes/benchmark.py` (standardized response)
- Modify: `backend/app/api/routes/gaps.py` (standardized response)

- [ ] **Step 1: Add input size validation to profile service**

In `backend/app/services/profile.py`, in the `parse_resume` method (or wherever resume text is processed), add at the top:

```python
MAX_RESUME_SIZE = 50 * 1024  # 50KB

async def parse_resume(self, user_id: str, resume_text: str, ...) -> Dict[str, Any]:
    if len(resume_text.encode("utf-8")) > MAX_RESUME_SIZE:
        raise ValueError(f"Resume text exceeds maximum size of {MAX_RESUME_SIZE // 1024}KB")
    if not resume_text.strip():
        raise ValueError("Resume text cannot be empty")
    # ... existing logic
```

- [ ] **Step 2: Add JD validation to benchmark service**

In `backend/app/services/benchmark.py`, before calling the benchmark chain:

```python
async def generate_benchmark(self, ..., jd_text: str, ...) -> Dict[str, Any]:
    if not jd_text or not jd_text.strip():
        raise ValueError("Job description text is required for benchmark generation")
    # ... existing logic
```

- [ ] **Step 3: Fix N+1 query in gap service**

In `backend/app/services/gap.py`, replace separate queries with a joined query:

```python
# BEFORE: separate queries
# gap_report = await self.db.get(TABLES["gap_reports"], gap_id)
# job = await self.db.get(TABLES["jobs"], gap_report["job_description_id"])

# AFTER: single query with select join
result = self.db.client.table("gap_reports").select(
    "*, job_descriptions(*)"
).eq("id", gap_id).eq("user_id", user_id).execute()
```

- [ ] **Step 4: Update benchmark route to use standardized response**

In `backend/app/api/routes/benchmark.py`:

```python
from app.api.response import success_response

@router.post("/")
async def create_benchmark(...):
    result = await service.generate_benchmark(...)
    return success_response(data=result, meta={"trace_id": str(uuid4())})
```

- [ ] **Step 5: Update gaps route similarly**

```python
from app.api.response import success_response

@router.get("/")
async def list_gaps(...):
    gaps = await service.list_gaps(...)
    return success_response(data=gaps, meta={"total": len(gaps)})
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/profile.py backend/app/services/benchmark.py backend/app/services/gap.py backend/app/api/routes/benchmark.py backend/app/api/routes/gaps.py
git commit -m "fix: add input validation, fix N+1 query, standardize response format"
```

---

### Task 25: Backend Error Handling Standardization

**Files:**

- Modify: `backend/app/api/routes/` (multiple route files)

- [ ] **Step 1: Replace bare except blocks across all route files**

Search for `except Exception` blocks in all route files. Replace with typed handlers:

```python
# Pattern to apply in all route files:
except ValueError as e:
    raise HTTPException(status_code=422, detail=str(e))
except Exception as e:
    logger.error("unexpected_error", error=str(e), endpoint="<endpoint_name>")
    raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

Apply this pattern in these files (find the bare except blocks):

- `backend/app/api/routes/profile.py`
- `backend/app/api/routes/benchmark.py`
- `backend/app/api/routes/gaps.py`
- `backend/app/api/routes/builder.py`
- `backend/app/api/routes/consultant.py`
- `backend/app/api/routes/export.py`

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/
git commit -m "fix: replace bare except blocks with typed error handlers across all routes"
```

---

### Task 26: Backend DOCX Generation via python-docx

**Files:**

- Modify: `backend/app/services/export.py`

- [ ] **Step 1: Install python-docx**

Run: `cd "/Users/balabollineni/HireStack AI" && pip install python-docx`

- [ ] **Step 2: Add DOCX generation method to export service**

In `backend/app/services/export.py`, add a method that generates proper .docx files from HTML content:

```python
from docx import Document as DocxDocument
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re
from io import BytesIO


def generate_docx_from_html(html_content: str, document_type: str = "cv") -> bytes:
    """Convert HTML content to proper DOCX using python-docx.

    Replaces the frontend MHTML hack with real DOCX generation.
    """
    doc = DocxDocument()

    # Set margins
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

    # Strip HTML tags and convert to text paragraphs
    # (Full HTML-to-DOCX conversion would use htmldocx or similar,
    #  but for career documents, structured text extraction works well)
    text = re.sub(r"<br\s*/?>", "\n", html_content)
    text = re.sub(r"</(p|div|h[1-6]|li)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    for para_text in paragraphs:
        p = doc.add_paragraph(para_text)
        p.style.font.size = Pt(11)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 3: Add DOCX export endpoint**

Add to `backend/app/api/routes/export.py`:

```python
@router.post("/docx")
async def export_docx(
    request: ExportRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Generate a proper DOCX file from document HTML content."""
    from app.services.export import generate_docx_from_html
    from fastapi.responses import Response

    docx_bytes = generate_docx_from_html(
        request.content, request.document_type
    )
    filename = f"{request.document_type or 'document'}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/export.py backend/app/api/routes/export.py
git commit -m "feat: add backend DOCX generation via python-docx (replaces frontend MHTML hack)"
```

---

**End of Chunk 2 — Phase 2: Backend Service Integration + SSE (Tasks 22-26)**

---

## Chunk 3: Phase 2 — Frontend Workspace Transformation

This chunk transforms the application workspace from a scrolling page to a Replit-style panel-based workspace with real-time agent progress, quality reports, and inline editing.

### File Structure

```
frontend/src/
├── hooks/
│   └── use-agent-status.ts          # SSE subscription hook
├── components/
│   ├── workspace/
│   │   ├── panel-layout.tsx          # react-resizable-panels wrapper
│   │   ├── context-panel.tsx         # right panel (quality, coach, history)
│   │   ├── bottom-panel.tsx          # generation log + status bar
│   │   ├── agent-progress.tsx        # pipeline step visualization
│   │   ├── quality-report.tsx        # score cards with breakdowns
│   │   ├── workspace-header.tsx      # NEW: dense score dashboard
│   │   ├── document-tabs.tsx         # NEW: CV/CL/PS/Portfolio tab switcher
│   │   └── fact-check-badge.tsx      # NEW: verification summary
│   ├── inline-edit/
│   │   ├── inline-editable.tsx       # click-to-edit wrapper
│   │   └── inline-tag-editor.tsx     # skill/keyword inline editing
│   └── scores/
│       ├── score-bar.tsx             # animated progress bar
│       ├── score-grid.tsx            # dense score dashboard
│       └── digit-counter.tsx         # animated number counter
├── app/(dashboard)/applications/[id]/
│   ├── page.tsx                      # REFACTOR: ~50 lines, layout + Suspense
│   └── _components/                  # extracted from monolith
│       ├── workspace-layout.tsx
│       └── module-grid.tsx
```

---

### Task 27: Install Frontend Dependencies

- [ ] **Step 1: Install react-resizable-panels and cmdk**

Run: `cd "/Users/balabollineni/HireStack AI/frontend" && npm install react-resizable-panels`

- [ ] **Step 2: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add react-resizable-panels dependency"
```

---

### Task 28: useAgentStatus SSE Hook

**Files:**

- Create: `frontend/src/hooks/use-agent-status.ts`

- [ ] **Step 1: Create the SSE hook**

```typescript
// frontend/src/hooks/use-agent-status.ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface AgentStage {
  stage: string;
  status: "waiting" | "running" | "completed" | "failed";
  latency_ms: number;
  message: string;
}

export interface AgentStatusState {
  stages: AgentStage[];
  isRunning: boolean;
  currentStage: string | null;
  qualityScores: Record<string, number>;
  factCheckSummary: { verified: number; enhanced: number; fabricated: number } | null;
  error: string | null;
}

const INITIAL_STATE: AgentStatusState = {
  stages: [],
  isRunning: false,
  currentStage: null,
  qualityScores: {},
  factCheckSummary: null,
  error: null,
};

export function useAgentStatus(): {
  state: AgentStatusState;
  subscribe: (pipelineName: string) => void;
  reset: () => void;
} {
  const [state, setState] = useState<AgentStatusState>(INITIAL_STATE);
  const eventSourceRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  const subscribe = useCallback((pipelineName: string) => {
    setState((prev) => ({ ...prev, isRunning: true, stages: [], error: null }));
  }, []);

  // Listen for agent_status events from the SSE stream
  // This hook is consumed by the workspace components
  // The actual EventSource connection is managed by the generate pipeline caller

  const handleAgentEvent = useCallback((event: { stage: string; status: string; latency_ms: number; message: string }) => {
    setState((prev) => {
      const existingIdx = prev.stages.findIndex((s) => s.stage === event.stage);
      const newStage: AgentStage = {
        stage: event.stage,
        status: event.status as AgentStage["status"],
        latency_ms: event.latency_ms,
        message: event.message,
      };

      const stages = [...prev.stages];
      if (existingIdx >= 0) {
        stages[existingIdx] = newStage;
      } else {
        stages.push(newStage);
      }

      return {
        ...prev,
        stages,
        currentStage: event.status === "running" ? event.stage : prev.currentStage,
      };
    });
  }, []);

  const handleComplete = useCallback((data: { quality_scores?: Record<string, number>; fact_check_summary?: any }) => {
    setState((prev) => ({
      ...prev,
      isRunning: false,
      currentStage: null,
      qualityScores: data.quality_scores || {},
      factCheckSummary: data.fact_check_summary || null,
    }));
  }, []);

  const handleError = useCallback((message: string) => {
    setState((prev) => ({ ...prev, isRunning: false, error: message }));
  }, []);

  return {
    state,
    subscribe,
    reset,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/use-agent-status.ts
git commit -m "feat: add useAgentStatus SSE hook for real-time pipeline progress"
```

---

### Task 29: Agent Progress Component

**Files:**

- Create: `frontend/src/components/workspace/agent-progress.tsx`

- [ ] **Step 1: Create AgentProgress component**

```tsx
// frontend/src/components/workspace/agent-progress.tsx
"use client";

import { memo } from "react";
import { Check, Loader2, Circle, AlertCircle } from "lucide-react";
import type { AgentStage } from "@/hooks/use-agent-status";

const STAGE_LABELS: Record<string, string> = {
  researcher: "Analyzing job requirements",
  drafter: "Creating first draft",
  critic: "Reviewing for quality",
  optimizer: "Optimizing for ATS",
  fact_checker: "Verifying facts",
  validator: "Final validation",
};

function StageIcon({ status }: { status: AgentStage["status"] }) {
  switch (status) {
    case "completed":
      return <Check className="h-4 w-4 text-emerald-600 animate-check-pop" />;
    case "running":
      return <Loader2 className="h-4 w-4 text-primary animate-spin" />;
    case "failed":
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground" />;
  }
}

interface AgentProgressProps {
  stages: AgentStage[];
  isRunning: boolean;
  pipelineName?: string;
}

export const AgentProgress = memo(function AgentProgress({
  stages,
  isRunning,
  pipelineName,
}: AgentProgressProps) {
  if (stages.length === 0 && !isRunning) return null;

  const completedCount = stages.filter((s) => s.status === "completed").length;
  const totalCount = Math.max(stages.length, 6); // at least 6 stages expected
  const progressPct = Math.round((completedCount / totalCount) * 100);

  return (
    <div className="space-y-2">
      {pipelineName && (
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {pipelineName.replace(/_/g, " ")}
        </p>
      )}
      {stages.map((stage) => (
        <div key={stage.stage} className="flex items-center gap-3 text-sm">
          <StageIcon status={stage.status} />
          <span className={stage.status === "running" ? "text-foreground" : "text-muted-foreground"}>
            {STAGE_LABELS[stage.stage] || stage.message || stage.stage}
          </span>
          {stage.status === "completed" && stage.latency_ms > 0 && (
            <span className="font-mono text-xs text-muted-foreground ml-auto">
              {(stage.latency_ms / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      ))}
      {isRunning && (
        <div className="mt-3">
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground font-mono mt-1 text-right">{progressPct}%</p>
        </div>
      )}
    </div>
  );
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/agent-progress.tsx
git commit -m "feat: add AgentProgress component with stage visualization"
```

---

### Task 30: Quality Report Component

**Files:**

- Create: `frontend/src/components/workspace/quality-report.tsx`

- [ ] **Step 1: Create QualityReport component**

```tsx
// frontend/src/components/workspace/quality-report.tsx
"use client";

import { memo } from "react";
import { Check, Shield } from "lucide-react";
import { cn, getScoreColor } from "@/lib/utils";

interface QualityReportProps {
  scores: Record<string, number>;
  factCheck?: { verified: number; enhanced: number; fabricated: number } | null;
  className?: string;
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const color =
    score >= 90 ? "bg-emerald-500" :
    score >= 70 ? "bg-primary" :
    score >= 50 ? "bg-amber-500" :
    "bg-rose-500";

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground w-28 shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-600 ease-out", color)}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="font-mono text-sm font-semibold w-12 text-right">{score}%</span>
    </div>
  );
}

export const QualityReport = memo(function QualityReport({
  scores,
  factCheck,
  className,
}: QualityReportProps) {
  const scoreEntries = Object.entries(scores).filter(([, v]) => typeof v === "number");

  if (scoreEntries.length === 0) return null;

  return (
    <div className={cn("space-y-4", className)}>
      <h3 className="text-sm font-semibold">Quality Report</h3>
      <div className="space-y-2.5">
        {scoreEntries.map(([key, value]) => (
          <ScoreBar key={key} label={key.replace(/_/g, " ")} score={value} />
        ))}
      </div>
      {factCheck && (
        <div className="mt-4 space-y-1.5">
          <div className="flex items-center gap-2 text-sm text-emerald-600">
            <Check className="h-3.5 w-3.5" />
            <span>{factCheck.verified} claims verified against your profile</span>
          </div>
          {factCheck.enhanced > 0 && (
            <div className="flex items-center gap-2 text-sm text-primary">
              <Shield className="h-3.5 w-3.5" />
              <span>{factCheck.enhanced} claims strategically enhanced</span>
            </div>
          )}
          {factCheck.fabricated > 0 && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <span className="font-mono font-bold">!</span>
              <span>{factCheck.fabricated} fabricated claims removed</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/quality-report.tsx
git commit -m "feat: add QualityReport component with score bars and fact-check summary"
```

---

### Task 31: Score Components (ScoreBar, ScoreGrid, DigitCounter)

**Files:**

- Create: `frontend/src/components/scores/score-bar.tsx`
- Create: `frontend/src/components/scores/score-grid.tsx`
- Create: `frontend/src/components/scores/digit-counter.tsx`

- [ ] **Step 1: Create DigitCounter (animated number)**

```tsx
// frontend/src/components/scores/digit-counter.tsx
"use client";

import { memo, useEffect, useState } from "react";
import { cn } from "@/lib/utils";

interface DigitCounterProps {
  value: number;
  suffix?: string;
  className?: string;
  duration?: number;
}

export const DigitCounter = memo(function DigitCounter({
  value,
  suffix = "",
  className,
  duration = 600,
}: DigitCounterProps) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const start = display;
    const diff = value - start;
    if (diff === 0) return;

    const startTime = performance.now();
    let raf: number;

    function step(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + diff * eased));
      if (progress < 1) raf = requestAnimationFrame(step);
    }

    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return (
    <span className={cn("font-mono font-semibold tabular-nums", className)}>
      {display}{suffix}
    </span>
  );
});
```

- [ ] **Step 2: Create ScoreGrid (dense dashboard)**

```tsx
// frontend/src/components/scores/score-grid.tsx
"use client";

import { memo } from "react";
import { cn } from "@/lib/utils";
import { DigitCounter } from "./digit-counter";

interface ScoreEntry {
  label: string;
  value: number;
}

interface ScoreGridProps {
  scores: ScoreEntry[];
  className?: string;
}

function barColor(score: number): string {
  if (score >= 90) return "bg-emerald-500";
  if (score >= 70) return "bg-primary";
  if (score >= 50) return "bg-amber-500";
  return "bg-rose-500";
}

export const ScoreGrid = memo(function ScoreGrid({ scores, className }: ScoreGridProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-x-6 gap-y-2", className)} role="status">
      {scores.map((s) => (
        <div key={s.label} className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-24 shrink-0 truncate">{s.label}</span>
          <DigitCounter value={s.value} suffix="%" className="text-sm w-10" />
          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all duration-500", barColor(s.value))}
              style={{ width: `${s.value}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/scores/
git commit -m "feat: add score components (DigitCounter, ScoreGrid) with animations"
```

---

### Task 32: Panel-Based Workspace Layout

**Files:**

- Create: `frontend/src/components/workspace/panel-layout.tsx`

- [ ] **Step 1: Create PanelLayout component**

```tsx
// frontend/src/components/workspace/panel-layout.tsx
"use client";

import { memo, type ReactNode } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

interface PanelLayoutProps {
  mainPanel: ReactNode;
  contextPanel: ReactNode;
  bottomPanel?: ReactNode;
  bottomCollapsed?: boolean;
}

function ResizeHandle({ direction = "horizontal" }: { direction?: "horizontal" | "vertical" }) {
  return (
    <PanelResizeHandle
      className={
        direction === "horizontal"
          ? "w-1 hover:w-1.5 bg-border/50 hover:bg-primary/30 transition-all duration-150 cursor-col-resize"
          : "h-1 hover:h-1.5 bg-border/50 hover:bg-primary/30 transition-all duration-150 cursor-row-resize"
      }
    />
  );
}

export const PanelLayout = memo(function PanelLayout({
  mainPanel,
  contextPanel,
  bottomPanel,
  bottomCollapsed = false,
}: PanelLayoutProps) {
  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <PanelGroup direction="vertical">
        <Panel defaultSize={bottomPanel ? 75 : 100} minSize={40}>
          <PanelGroup direction="horizontal">
            <Panel defaultSize={65} minSize={30}>
              <div className="h-full overflow-y-auto p-4">{mainPanel}</div>
            </Panel>
            <ResizeHandle direction="horizontal" />
            <Panel defaultSize={35} minSize={20}>
              <div className="h-full overflow-y-auto p-4 border-l border-border/50">
                {contextPanel}
              </div>
            </Panel>
          </PanelGroup>
        </Panel>
        {bottomPanel && (
          <>
            <ResizeHandle direction="vertical" />
            <Panel
              defaultSize={25}
              minSize={5}
              collapsible
              collapsedSize={3}
            >
              <div className="h-full overflow-y-auto p-3 border-t border-border/50 bg-surface">
                {bottomPanel}
              </div>
            </Panel>
          </>
        )}
      </PanelGroup>
    </div>
  );
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/panel-layout.tsx
git commit -m "feat: add PanelLayout with resizable panels for workspace"
```

---

### Task 33: Inline Editing Components

**Files:**

- Create: `frontend/src/components/inline-edit/inline-editable.tsx`
- Create: `frontend/src/components/inline-edit/inline-tag-editor.tsx`

- [ ] **Step 1: Create InlineEditable component**

```tsx
// frontend/src/components/inline-edit/inline-editable.tsx
"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface InlineEditableProps {
  value: string;
  onSave: (newValue: string) => void;
  className?: string;
  hoverClassName?: string;
  inputClassName?: string;
  placeholder?: string;
}

export const InlineEditable = memo(function InlineEditable({
  value,
  onSave,
  className = "",
  hoverClassName = "bg-primary/5 rounded px-1 -mx-1",
  inputClassName = "",
  placeholder = "Click to edit",
}: InlineEditableProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const handleSave = useCallback(() => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== value) {
      onSave(trimmed);
    } else {
      setDraft(value);
    }
    setEditing(false);
  }, [draft, value, onSave]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") handleSave();
      if (e.key === "Escape") {
        setDraft(value);
        setEditing(false);
      }
    },
    [handleSave, value]
  );

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={handleSave}
        onKeyDown={handleKeyDown}
        className={cn(
          "bg-transparent border-b border-primary/40 outline-none text-sm",
          inputClassName
        )}
      />
    );
  }

  return (
    <span
      role="button"
      tabIndex={0}
      onClick={() => { setDraft(value); setEditing(true); }}
      onKeyDown={(e) => { if (e.key === "Enter") { setDraft(value); setEditing(true); } }}
      className={cn("cursor-pointer transition-colors", className, `hover:${hoverClassName}`)}
    >
      {value || <span className="text-muted-foreground italic">{placeholder}</span>}
    </span>
  );
});
```

- [ ] **Step 2: Create InlineTagEditor**

```tsx
// frontend/src/components/inline-edit/inline-tag-editor.tsx
"use client";

import { memo, useCallback, useState } from "react";
import { X, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

interface InlineTagEditorProps {
  tags: string[];
  onUpdate: (tags: string[]) => void;
  className?: string;
}

export const InlineTagEditor = memo(function InlineTagEditor({
  tags,
  onUpdate,
  className,
}: InlineTagEditorProps) {
  const [adding, setAdding] = useState(false);
  const [newTag, setNewTag] = useState("");

  const handleRemove = useCallback((idx: number) => {
    onUpdate(tags.filter((_, i) => i !== idx));
  }, [tags, onUpdate]);

  const handleAdd = useCallback(() => {
    const trimmed = newTag.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onUpdate([...tags, trimmed]);
    }
    setNewTag("");
    setAdding(false);
  }, [newTag, tags, onUpdate]);

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {tags.map((tag, i) => (
        <span
          key={`${tag}-${i}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-mono font-medium animate-bounce-sm"
        >
          {tag}
          <button
            onClick={() => handleRemove(i)}
            className="hover:text-destructive transition-colors"
            aria-label={`Remove ${tag}`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      {adding ? (
        <input
          autoFocus
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          onBlur={handleAdd}
          onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); if (e.key === "Escape") setAdding(false); }}
          className="text-xs font-mono bg-transparent border-b border-primary/40 outline-none w-24"
          placeholder="Add tag..."
        />
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md border border-dashed border-muted-foreground/30 text-xs text-muted-foreground hover:border-primary hover:text-primary transition-colors"
          aria-label="Add tag"
        >
          <Plus className="h-3 w-3" />
        </button>
      )}
    </div>
  );
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/inline-edit/
git commit -m "feat: add InlineEditable and InlineTagEditor components"
```

---

### Task 34: Fact-Check Badge Component

**Files:**

- Create: `frontend/src/components/workspace/fact-check-badge.tsx`

- [ ] **Step 1: Create FactCheckBadge**

```tsx
// frontend/src/components/workspace/fact-check-badge.tsx
"use client";

import { memo } from "react";
import { Shield, ShieldCheck, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

interface FactCheckBadgeProps {
  verified: number;
  enhanced: number;
  fabricated: number;
  className?: string;
}

export const FactCheckBadge = memo(function FactCheckBadge({
  verified,
  enhanced,
  fabricated,
  className,
}: FactCheckBadgeProps) {
  const total = verified + enhanced + fabricated;
  const accuracy = total > 0 ? Math.round(((verified + enhanced) / total) * 100) : 100;

  return (
    <div className={cn("inline-flex items-center gap-2 px-3 py-1.5 rounded-lg", className,
      fabricated > 0 ? "bg-destructive/10 border border-destructive/20" : "bg-emerald-500/10 border border-emerald-500/20"
    )}>
      {fabricated > 0 ? (
        <ShieldAlert className="h-4 w-4 text-destructive" />
      ) : (
        <ShieldCheck className="h-4 w-4 text-emerald-600" />
      )}
      <span className="font-mono text-xs font-medium">
        {verified} verified · {enhanced} enhanced
        {fabricated > 0 && <span className="text-destructive"> · {fabricated} fabricated</span>}
      </span>
      <span className="font-mono text-xs text-muted-foreground">({accuracy}%)</span>
    </div>
  );
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/fact-check-badge.tsx
git commit -m "feat: add FactCheckBadge component"
```

---

**End of Chunk 3 — Phase 2: Frontend Workspace (Tasks 27-34)**

---

## Chunk 4: Phase 3 — Tier 2 Features

Tier 2 adds agent pipelines to ATS Scanner, Interview Simulator (text only), and Career Consultant.

---

### Task 35: ATS Scanner Agent Pipeline

**Files:**

- Create: `ai_engine/agents/pipelines.py` (add `ats_scanner_pipeline`)
- Modify: `backend/app/services/ats.py` (wire pipeline)
- Modify: `backend/app/api/routes/ats.py` (standardized response + input validation)

- [ ] **Step 1: Add ats_scanner_pipeline to pipelines.py**

```python
def ats_scanner_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import ATSScannerChain
    chain = ATSScannerChain(client)
    return create_pipeline(
        "ats_scanner", chain, "scan_document",
        use_critic=False, use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )
```

- [ ] **Step 2: Add input validation to ATS route**

```python
# In backend/app/api/routes/ats.py
MAX_ATS_INPUT_SIZE = 100 * 1024  # 100KB combined

@router.post("/scan")
async def scan_document(...):
    combined_size = len((req.document_content + req.jd_text).encode("utf-8"))
    if combined_size > MAX_ATS_INPUT_SIZE:
        raise HTTPException(status_code=422, detail="Combined input exceeds 100KB limit")
    # ... pipeline call
```

- [ ] **Step 3: Commit**

```bash
git add ai_engine/agents/pipelines.py backend/app/services/ats.py backend/app/api/routes/ats.py
git commit -m "feat: add ATS Scanner agent pipeline with input validation"
```

---

### Task 36: Interview Simulator Agent Pipeline (Text Only)

**Files:**

- Add to `ai_engine/agents/pipelines.py`
- Modify: `backend/app/services/interview.py`
- Modify: `backend/app/api/routes/interview.py`

- [ ] **Step 1: Add interview_pipeline to pipelines.py**

```python
def interview_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import InterviewSimulatorChain
    chain = InterviewSimulatorChain(client)
    return create_pipeline(
        "interview", chain, "generate_questions",
        use_optimizer=False, use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )
```

- [ ] **Step 2: Add session timeout and answer validation**

In `backend/app/services/interview.py`:

```python
SESSION_TIMEOUT_HOURS = 2

async def submit_answer(self, session_id: str, answer_text: str, ...) -> Dict:
    if not answer_text or not answer_text.strip():
        raise ValueError("Answer text cannot be empty")

    # Check session timeout
    session = await self.db.get(TABLES["interview_sessions"], session_id)
    created = session.get("created_at")
    if created:
        from datetime import datetime, timezone, timedelta
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - created_dt > timedelta(hours=SESSION_TIMEOUT_HOURS):
            raise ValueError("Interview session has expired (2 hour limit)")
    # ... existing logic
```

- [ ] **Step 3: Fix bare exception handler in interview route**

```python
# Replace bare except with typed handlers
except ValueError as e:
    raise HTTPException(status_code=422, detail=str(e))
except Exception as e:
    logger.error("interview_error", error=str(e))
    raise HTTPException(status_code=500, detail="Interview generation failed")
```

- [ ] **Step 4: Commit**

```bash
git add ai_engine/agents/pipelines.py backend/app/services/interview.py backend/app/api/routes/interview.py
git commit -m "feat: add Interview Simulator agent pipeline (text only) with session timeout"
```

---

### Task 37: Career Consultant Agent Pipeline

**Files:**

- Add to `ai_engine/agents/pipelines.py`
- Modify: `backend/app/services/roadmap.py`

- [ ] **Step 1: Add career_roadmap_pipeline to pipelines.py**

```python
def career_roadmap_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import CareerConsultantChain
    chain = CareerConsultantChain(client)
    return create_pipeline(
        "career_roadmap", chain, "generate_roadmap",
        use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )
```

- [ ] **Step 2: Add milestone dependency validation**

In `backend/app/services/roadmap.py`:

```python
def _validate_milestones(roadmap: dict) -> dict:
    """Validate milestone dependencies are correctly sequenced."""
    milestones = roadmap.get("milestones", [])
    for i, milestone in enumerate(milestones):
        deps = milestone.get("dependencies", [])
        for dep_idx in deps:
            if isinstance(dep_idx, int) and dep_idx >= i:
                milestone["dependencies"] = [d for d in deps if isinstance(d, int) and d < i]
    return roadmap
```

- [ ] **Step 3: Commit**

```bash
git add ai_engine/agents/pipelines.py backend/app/services/roadmap.py
git commit -m "feat: add Career Consultant agent pipeline with milestone validation"
```

---

### Task 38: Database — Tier 2 CHECK Constraints

**Files:**

- Create: `supabase/migrations/20260316000000_tier2_constraints.sql`

- [ ] **Step 1: Write migration**

```sql
-- CHECK constraints for Tier 2 feature enums
ALTER TABLE ats_scans
  ADD CONSTRAINT ck_ats_scans_status
  CHECK (status IN ('pending', 'scanning', 'completed', 'failed'));

ALTER TABLE interview_sessions
  ADD CONSTRAINT ck_interview_status
  CHECK (status IN ('active', 'completed', 'abandoned', 'expired'));
```

- [ ] **Step 2: Commit**

```bash
git add supabase/migrations/20260316000000_tier2_constraints.sql
git commit -m "feat: add CHECK constraints for ATS and interview enums"
```

---

**End of Chunk 4 — Phase 3: Tier 2 Features (Tasks 35-38)**

---

## Chunk 5: Phase 4 — Tier 3 Features + Phase 5 — Full Elevation

### Task 39: A/B Doc Lab — Three-Drafter Variant Pipeline

**Files:**

- Add to `ai_engine/agents/pipelines.py`

- [ ] **Step 1: Add ab_lab_pipeline**

```python
# Tone constants for A/B Lab variants
CONSERVATIVE_TONE = "Use formal language, traditional structure, quantified achievements, no personality flair"
BALANCED_TONE = "Professional but approachable, mix of quantified and narrative, moderate personality"
CREATIVE_TONE = "Bold opening, storytelling elements, unique framing, personality-forward"


def ab_lab_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    """Special pipeline: 3 parallel Drafters → comparative Critic → Optimizer → Validator."""
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentVariantChain
    chain = DocumentVariantChain(client)

    # A/B Lab uses a custom orchestration pattern (not the standard pipeline)
    # The pipeline factory creates a standard pipeline; the service layer
    # handles the 3-drafter parallelism by calling the pipeline 3x with
    # different tone_instruction context values, then passing all 3 to
    # the Critic in comparative mode.
    return create_pipeline(
        "ab_lab", chain, "generate_variant",
        use_researcher=False, use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )
```

- [ ] **Step 2: Commit**

```bash
git add ai_engine/agents/pipelines.py
git commit -m "feat: add A/B Doc Lab pipeline with tone constants"
```

---

### Task 40: Salary Coach + Learning Pipelines

**Files:**

- Add to `ai_engine/agents/pipelines.py`

- [ ] **Step 1: Add salary and learning pipelines**

```python
def salary_coach_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import SalaryCoachChain
    chain = SalaryCoachChain(client)
    return create_pipeline(
        "salary_coach", chain, "analyze_salary",
        use_critic=False, use_optimizer=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )


def learning_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import LearningChallengeChain
    chain = LearningChallengeChain(client)
    return create_pipeline(
        "learning", chain, "generate_challenge",
        use_researcher=False, use_critic=False, use_optimizer=False,
        use_fact_checker=False, max_iterations=0,
        ai_client=client, on_stage_update=on_stage_update,
    )
```

- [ ] **Step 2: Update agents **init**.py with all new pipelines**

Add the new pipeline exports to `ai_engine/agents/__init__.py`.

- [ ] **Step 3: Commit**

```bash
git add ai_engine/agents/pipelines.py ai_engine/agents/__init__.py
git commit -m "feat: add Salary Coach and Learning pipelines"
```

---

### Task 41: Database — Tier 3 Constraints + Indexes

**Files:**

- Create: `supabase/migrations/20260316100000_tier3_and_indexes.sql`

- [ ] **Step 1: Write migration**

```sql
-- Tier 3 CHECK constraints
ALTER TABLE doc_variants
  ADD CONSTRAINT ck_doc_variants_tone
  CHECK (tone IN ('conservative', 'balanced', 'creative'));

ALTER TABLE learning_challenges
  ADD CONSTRAINT ck_learning_difficulty
  CHECK (difficulty IN ('beginner', 'intermediate', 'advanced'));

-- Performance indexes (Phase 5 items moved earlier)
CREATE INDEX IF NOT EXISTS idx_applications_user_status
  ON applications(user_id, status);

CREATE INDEX IF NOT EXISTS idx_documents_app_type
  ON documents(application_id, document_type);

CREATE INDEX IF NOT EXISTS idx_applications_user_created
  ON applications(user_id, created_at DESC);

-- Realtime publication
ALTER PUBLICATION supabase_realtime ADD TABLE doc_variants;
ALTER PUBLICATION supabase_realtime ADD TABLE review_comments;
```

- [ ] **Step 2: Commit**

```bash
git add supabase/migrations/20260316100000_tier3_and_indexes.sql
git commit -m "feat: add Tier 3 constraints, performance indexes, and realtime publication"
```

---

### Task 42: Frontend Type Safety — Replace Record<string, any>

**Files:**

- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Replace Record<string, any> types with strict interfaces**

Search `frontend/src/types/index.ts` for all `Record<string, any>` occurrences. Replace each with a specific interface. Key replacements:

```typescript
// BEFORE
ai_analysis?: Record<string, any>;
// AFTER
ai_analysis?: {
  compatibility_score?: number;
  readiness_level?: string;
  category_scores?: Record<string, number>;
  skill_gaps?: Array<{ skill: string; importance: string; recommendation: string }>;
};

// BEFORE
payload?: Record<string, any>;
// AFTER
payload?: {
  question?: string;
  answer?: string;
  score?: number;
  feedback?: string;
};

// BEFORE
benefits_analysis?: Record<string, any>;
// AFTER
benefits_analysis?: {
  total_compensation?: number;
  base_salary?: { min: number; max: number; median: number };
  equity?: { value?: number; vesting?: string };
  benefits?: string[];
};
```

Add new types for agent pipeline metadata:

```typescript
// Agent pipeline quality metadata
export interface QualityScores {
  impact?: number;
  clarity?: number;
  tone_match?: number;
  completeness?: number;
  ats_readiness?: number;
  readability?: number;
}

export interface FactCheckSummary {
  verified: number;
  enhanced: number;
  fabricated: number;
}

export interface PipelineMeta {
  quality_scores?: QualityScores;
  fact_check?: FactCheckSummary;
  agent_powered?: boolean;
  trace_id?: string;
  total_latency_ms?: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "fix: replace Record<string, any> with strict interfaces, add agent pipeline types"
```

---

### Task 43: Integration Test Suite

**Files:**

- Create: `backend/tests/integration/test_agent_pipelines.py`

- [ ] **Step 1: Create integration test with mock AIClient**

```python
# backend/tests/integration/test_agent_pipelines.py
"""Integration tests for agent pipelines with mock AIClient."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_engine.agents.pipelines import cv_generation_pipeline
from ai_engine.agents.orchestrator import PipelineResult


@pytest.fixture
def mock_ai():
    """Mock AIClient that returns structured JSON for all agents."""
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=_mock_complete_json)
    client.complete = AsyncMock(return_value="<p>Generated CV HTML</p>")
    client.provider_name = "mock"
    client.model = "mock-model"
    client.max_tokens = 4096
    return client


_call_count = 0


async def _mock_complete_json(prompt: str, **kwargs) -> dict:
    """Return appropriate mock data based on the prompt content."""
    global _call_count
    _call_count += 1
    prompt_lower = prompt.lower()

    if "analyze" in prompt_lower and "job" in prompt_lower:
        # Researcher
        return {"industry": "tech", "keyword_priority": [{"keyword": "Python", "priority": "high"}]}
    if "evaluate" in prompt_lower or "quality" in prompt_lower:
        # Critic
        return {"quality_scores": {"impact": 85, "clarity": 90}, "needs_revision": False, "feedback": {}}
    if "optimize" in prompt_lower or "ats" in prompt_lower:
        # Optimizer
        return {"keyword_analysis": {"present": ["Python"], "missing": []}, "suggestions": []}
    if "verify" in prompt_lower or "claim" in prompt_lower:
        # Fact-Checker
        return {"summary": {"verified": 10, "enhanced": 3, "fabricated": 0}, "claims": [], "fabricated_claims": []}
    if "validate" in prompt_lower:
        # Validator
        return {"valid": True, "checks": {}, "issues": []}

    return {"result": "mock"}


@pytest.mark.asyncio
async def test_cv_pipeline_end_to_end(mock_ai):
    """Full CV generation pipeline with all agent stages."""
    global _call_count
    _call_count = 0

    # Mock the chain method that DrafterAgent wraps
    mock_chain = MagicMock()
    mock_chain.generate_tailored_cv = AsyncMock(return_value="<h1>John Doe</h1><p>Software Engineer</p>")

    with patch("ai_engine.agents.pipelines.get_ai_client", return_value=mock_ai):
        with patch("ai_engine.agents.pipelines.DocumentGeneratorChain", return_value=mock_chain):
            pipeline = cv_generation_pipeline(ai_client=mock_ai)
            result = await pipeline.execute({
                "user_id": "test-user-1",
                "user_profile": {"name": "John", "skills": [{"name": "Python"}]},
                "job_title": "Senior Software Engineer",
                "company": "TestCorp",
                "jd_text": "We need a senior Python developer...",
                "resume_text": "John Doe, 5 years Python experience...",
            })

    assert isinstance(result, PipelineResult)
    assert result.content is not None
    assert result.trace_id is not None
    assert result.total_latency_ms >= 0
    # Verify all agent stages were called
    assert _call_count >= 4  # researcher, critic, optimizer, fact_checker, validator
```

- [ ] **Step 2: Run integration test**

Run: `cd "/Users/balabollineni/HireStack AI" && python -m pytest backend/tests/integration/test_agent_pipelines.py -v`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/
git commit -m "test: add integration test for CV generation agent pipeline"
```

---

### Task 44: CI/CD GitHub Actions Workflow

**Files:**

- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install Python deps
        run: pip install ruff mypy pytest pytest-asyncio structlog pydantic-settings httpx tenacity
      - name: Lint Python
        run: ruff check ai_engine/ backend/
      - name: Install Node deps
        run: cd frontend && npm ci
      - name: Lint TypeScript
        run: cd frontend && npx tsc --noEmit

  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: pip install -r requirements.txt 2>/dev/null || pip install pytest pytest-asyncio structlog pydantic-settings httpx tenacity python-docx jsonschema
      - name: Run tests
        run: python -m pytest backend/tests/ -v --tb=short

  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build backend image
        run: docker build -f infra/Dockerfile.backend -t hirestack-backend .
      - name: Build frontend image
        run: docker build -f infra/Dockerfile.frontend -t hirestack-frontend .
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for lint, test, and Docker build"
```

---

**End of Chunk 5 — Phase 4 + Phase 5 (Tasks 39-44)**

---

## Summary

| Chunk | Phase | Tasks | Focus |
|-------|-------|-------|-------|
| 1 | Phase 1 | 1-21 | Agent framework foundation (base classes, 7 agents, pipeline engine, memory, tracing, prompts, DB, fonts, command palette) |
| 2 | Phase 2A | 22-26 | Backend service integration (SSE agent pipeline, response helpers, input validation, error handling, DOCX) |
| 3 | Phase 2B | 27-34 | Frontend workspace (panels, agent progress, quality report, scores, inline editing, fact-check badge) |
| 4 | Phase 3 | 35-38 | Tier 2 features (ATS Scanner, Interview Simulator, Career Consultant, DB constraints) |
| 5 | Phase 4+5 | 39-44 | Tier 3 features (A/B Lab, Salary, Learning) + Full elevation (type safety, integration tests, CI/CD) |
