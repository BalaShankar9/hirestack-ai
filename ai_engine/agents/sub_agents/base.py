"""
SubAgent base classes and coordinator pattern.

SubAgent
    Lightweight specialist that runs ONE focused task (e.g. "gather company
    intel", "extract profile evidence") and returns a SubAgentResult.

SubAgentCoordinator
    Fans out N SubAgents via asyncio.gather, collects results (tolerating
    individual failures), and returns the ordered list.
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
#  SubAgentResult
# ────────────────────────────────────────────────────────────────────────

@dataclass
class SubAgentResult:
    """Output container for a single sub-agent execution."""

    agent_name: str
    data: dict = field(default_factory=dict)
    evidence_items: list[dict] = field(default_factory=list)
    confidence: float = 0.5
    latency_ms: int = 0
    error: Optional[str] = None
    _metadata: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def content(self) -> dict:
        """Alias for ``data`` — matches AgentResult interface."""
        return self.data

    @property
    def metadata(self) -> dict:
        return self._metadata

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "data": self.data,
            "evidence_items": self.evidence_items,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


# ────────────────────────────────────────────────────────────────────────
#  SubAgent  (abstract)
# ────────────────────────────────────────────────────────────────────────

class SubAgent(ABC):
    """
    A lightweight specialist worker that runs a single focused task.

    Sub-agents are NOT full pipeline agents — they don't loop or call LLMs
    in a multi-step reasoning loop (unless needed). They perform tool calls,
    deterministic analysis, or a single LLM pass, then return structured data.
    """

    def __init__(
        self,
        name: str,
        ai_client: Optional[AIClient] = None,
    ):
        self.name = name
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    @abstractmethod
    async def run(self, context: dict) -> SubAgentResult:
        """Execute the sub-agent's focused task."""
        ...

    async def safe_run(self, context: dict) -> SubAgentResult:
        """Run with error isolation — never raises, returns error result instead."""
        start = time.monotonic_ns()
        try:
            result = await self.run(context)
            result.latency_ms = int((time.monotonic_ns() - start) / 1_000_000)
            return result
        except Exception as exc:
            elapsed = int((time.monotonic_ns() - start) / 1_000_000)
            logger.warning("SubAgent %s failed: %s", self.name, exc)
            return SubAgentResult(
                agent_name=self.name,
                error=str(exc),
                latency_ms=elapsed,
            )


# ────────────────────────────────────────────────────────────────────────
#  SubAgentCoordinator
# ────────────────────────────────────────────────────────────────────────

class SubAgentCoordinator:
    """
    Fans out N SubAgents in parallel and collects results.

    Usage::

        coord = SubAgentCoordinator([agent_a, agent_b, agent_c])
        results = await coord.gather(context)
        # results: list[SubAgentResult]  — one per sub-agent, order preserved
    """

    def __init__(self, sub_agents: list[SubAgent]):
        self._sub_agents = list(sub_agents)

    @property
    def agent_names(self) -> list[str]:
        return [a.name for a in self._sub_agents]

    async def gather(
        self,
        context: dict,
        *,
        timeout: float | None = 120.0,
    ) -> list[SubAgentResult]:
        """
        Run all sub-agents concurrently.

        * Each sub-agent is wrapped with ``safe_run`` so failures are isolated.
        * An optional *timeout* (seconds) caps the total wall-clock time.
        """
        coros = [agent.safe_run(context) for agent in self._sub_agents]
        try:
            if timeout:
                results = await asyncio.wait_for(
                    asyncio.gather(*coros), timeout=timeout
                )
            else:
                results = await asyncio.gather(*coros)
        except asyncio.TimeoutError:
            logger.error("SubAgentCoordinator timed out after %.1fs", timeout)
            results = [
                SubAgentResult(
                    agent_name=a.name,
                    error=f"Coordinator timeout after {timeout}s",
                )
                for a in self._sub_agents
            ]
        return list(results)

    def merge_evidence(self, results: list[SubAgentResult]) -> list[dict]:
        """Flatten all evidence_items from successful sub-agent results."""
        evidence: list[dict] = []
        for r in results:
            if r.ok:
                evidence.extend(r.evidence_items)
        return evidence

    def merge_data(self, results: list[SubAgentResult]) -> dict[str, Any]:
        """Merge all sub-agent data dicts, keyed by agent_name."""
        merged: dict[str, Any] = {}
        for r in results:
            if r.ok:
                merged[r.agent_name] = r.data
        return merged
