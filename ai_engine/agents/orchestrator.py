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
        lock_manager: Optional[PipelineLockManager] = None,
        on_stage_update: Optional[Callable] = None,
        db: Any = None,
    ):
        self.name = name
        self.researcher = researcher
        self.drafter = drafter
        self.critic = critic
        self.optimizer = optimizer
        self.fact_checker = fact_checker
        self.validator = validator
        self.lock_manager = lock_manager or PipelineLockManager()
        self.on_stage_update = on_stage_update  # SSE callback
        self.db = db  # Supabase client for trace persistence

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
                critic_ctx = {"draft": draft.content, "original_context": enriched_context}
                parallel_agents.append(self.critic.run(critic_ctx))
                parallel_names.append("critic")
            if self.optimizer:
                optimizer_ctx = {"draft": draft.content, "original_context": enriched_context}
                parallel_agents.append(self.optimizer.run(optimizer_ctx))
                parallel_names.append("optimizer")
            if self.fact_checker:
                fact_check_ctx = {"draft": draft.content, "source": context}
                parallel_agents.append(self.fact_checker.run(fact_check_ctx))
                parallel_names.append("fact_checker")

            for name in parallel_names:
                await self._emit(name, "running")

            parallel_results = await asyncio.gather(*parallel_agents, return_exceptions=True) if parallel_agents else []

            # Map results back to named variables — handle individual failures gracefully
            critic_result = optimizer_result = fact_check_result = None
            for name, result in zip(parallel_names, parallel_results):
                if isinstance(result, Exception):
                    logger.warning("parallel_agent_failed", agent=name, error=str(result))
                    tracer.record_stage(name, 0, "failed")
                    await self._emit(name, "failed", message=str(result))
                    continue
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
                        "optimizer": (optimizer_result.suggestions or {}) if optimizer_result else {},
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
                validator_ctx = {"draft": draft.content, "metadata": draft.metadata}
                validation = await self.validator.run(validator_ctx)
                tracer.record_stage("validator", validation.latency_ms, "completed")
                await self._emit("validator", "completed", validation.latency_ms)
            else:
                validation = draft

            total_latency = sum(s["latency_ms"] for s in tracer.stages)

            if self.db:
                tracer.persist(self.db)

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
