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
