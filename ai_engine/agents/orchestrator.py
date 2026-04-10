"""
Agent Pipeline Orchestrator — policy-driven multi-stage agent execution.

Execution is governed by a PipelinePolicy that decides which stages
to run based on task type, confidence from prior stages, cost budget,
and historical outcomes. Stages:
  1 (conditional): Researcher gathers context
  2 (always): Drafter generates first pass
  3 (conditional): Parallel Critic + Optimizer + Fact-Checker
  4 (conditional): Iterative revision loop
  5 (always): Validator
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import uuid4

import structlog

from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.agents.lock import PipelineLockManager
from ai_engine.agents.memory import AgentMemory
from ai_engine.agents.trace import AgentTracer

logger = structlog.get_logger("hirestack.agents.orchestrator")


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Policy — controls stage execution decisions
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PipelinePolicy:
    """Controls which stages run and when to stop.

    Attributes:
        skip_research: Skip researcher stage (e.g., for simple parsing tasks).
        skip_critique: Skip critic/optimizer/fact-checker for low-risk tasks.
        skip_fact_check: Skip fact-check for tasks without factual claims.
        confidence_threshold: Minimum confidence from critic to skip revision (0-1).
        cost_budget_tokens: Max estimated tokens to spend (0 = unlimited).
        require_fact_check_for_claims: Auto-enable fact-check if draft has >N claims.
        claim_threshold: Number of detected claims that forces fact-checking.
        max_iterations: Override pipeline max_iterations.
    """
    skip_research: bool = False
    skip_critique: bool = False
    skip_fact_check: bool = False
    confidence_threshold: float = 0.85
    cost_budget_tokens: int = 0
    require_fact_check_for_claims: bool = True
    claim_threshold: int = 3
    max_iterations: Optional[int] = None

    def should_research(self, pipeline_name: str, context: dict) -> bool:
        if self.skip_research:
            return False
        # Low-risk tasks skip research
        low_risk = {"learning", "salary_coach"}
        return pipeline_name not in low_risk

    def should_critique(self, pipeline_name: str) -> bool:
        if self.skip_critique:
            return False
        # Simple extraction tasks skip critique
        skip_for = {"resume_parse"}
        return pipeline_name not in skip_for

    def should_fact_check(
        self, pipeline_name: str, draft_content: dict,
    ) -> bool:
        if self.skip_fact_check:
            return False
        # Always fact-check document generation
        always_check = {"cv_generation", "cover_letter", "portfolio"}
        if pipeline_name in always_check:
            return True
        # Check if draft has enough claims to warrant fact-checking
        if self.require_fact_check_for_claims:
            claim_indicators = sum(
                1 for v in draft_content.values()
                if isinstance(v, str) and any(
                    c.isdigit() for c in v
                )
            )
            return claim_indicators >= self.claim_threshold
        return True

    def should_revise(self, critic_confidence: float) -> bool:
        """Return True if revision is needed based on confidence."""
        return critic_confidence < self.confidence_threshold

    def effective_max_iterations(self, pipeline_default: int) -> int:
        if self.max_iterations is not None:
            return self.max_iterations
        return pipeline_default


# Pre-built policies for common pipeline types
POLICY_FULL = PipelinePolicy()
POLICY_LIGHT = PipelinePolicy(skip_research=True, skip_fact_check=True, max_iterations=1)
POLICY_STRICT = PipelinePolicy(confidence_threshold=0.95, max_iterations=3)

# Map pipeline names to default policies
DEFAULT_POLICIES: dict[str, PipelinePolicy] = {
    "resume_parse": PipelinePolicy(skip_critique=True, skip_fact_check=True, max_iterations=1),
    "benchmark": POLICY_FULL,
    "gap_analysis": PipelinePolicy(skip_research=True, max_iterations=1),
    "cv_generation": POLICY_STRICT,
    "cover_letter": POLICY_STRICT,
    "personal_statement": PipelinePolicy(skip_research=True, skip_fact_check=True),
    "portfolio": PipelinePolicy(skip_research=True, skip_critique=False),
    "ats_scanner": PipelinePolicy(skip_critique=True, skip_fact_check=True, max_iterations=1),
    "interview": PipelinePolicy(skip_fact_check=True, max_iterations=1),
    "career_roadmap": PipelinePolicy(skip_fact_check=True, max_iterations=1),
    "ab_lab": PipelinePolicy(skip_research=True, skip_fact_check=True, max_iterations=1),
    "salary_coach": PipelinePolicy(skip_research=True, skip_critique=True, max_iterations=1),
    "learning": POLICY_LIGHT,
}


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
    """Policy-driven orchestrator for multi-stage agent execution."""

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
        max_iterations: int = 2,
        policy: Optional[PipelinePolicy] = None,
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
        self.max_iterations = max(1, max_iterations)
        self.policy = policy or DEFAULT_POLICIES.get(name, POLICY_FULL)
        self.memory: Optional[AgentMemory] = None

    async def execute(self, context: dict) -> PipelineResult:
        pipeline_id = str(uuid4())
        user_id = context.get("user_id", "unknown")
        policy = self.policy
        tracer = AgentTracer(pipeline_id, self.name, user_id)

        async with self.lock_manager.acquire(user_id, self.name, pipeline_id):
            enriched_context = dict(context)

            # Memory recall — inject stored learnings into context
            recalled_memories: list[dict] = []
            if self.memory and user_id != "unknown":
                try:
                    recalled_memories = await self.memory.arecall(
                        user_id, self.name, limit=10,
                    )
                    if recalled_memories:
                        enriched_context["agent_memories"] = recalled_memories
                        logger.info(
                            "memory_recalled",
                            user_id=user_id,
                            pipeline=self.name,
                            count=len(recalled_memories),
                        )
                except Exception as e:
                    logger.warning("memory_recall_failed", error=str(e))

            # Stage 1: Research (policy-gated)
            run_research = (
                self.researcher
                and policy.should_research(self.name, enriched_context)
            )
            if run_research:
                await self._emit("researcher", "running")
                research = await self.researcher.run(enriched_context)
                tracer.record_stage("researcher", research.latency_ms, "completed")
                enriched_context["research"] = research.content
                await self._emit("researcher", "completed", research.latency_ms)
            elif self.researcher:
                await self._emit("researcher", "skipped", message="Policy: skipped for this task type")
                tracer.record_stage("researcher", 0, "skipped")

            # Stage 2: Draft (always runs)
            await self._emit("drafter", "running")
            draft = await self.drafter.run(enriched_context)
            tracer.record_stage("drafter", draft.latency_ms, "completed")
            await self._emit("drafter", "completed", draft.latency_ms)

            # Stage 3: Parallel evaluation agents (policy-gated)
            parallel_agents = []
            parallel_names = []

            run_critic = self.critic and policy.should_critique(self.name)
            run_optimizer = self.optimizer is not None  # Optimizer always runs if present
            run_fact_check = (
                self.fact_checker
                and policy.should_fact_check(self.name, draft.content)
            )

            if run_critic:
                critic_ctx = {
                    "draft": draft.content,
                    "original_context": enriched_context,
                    "agent_memories": recalled_memories,
                }
                parallel_agents.append(self.critic.run(critic_ctx))
                parallel_names.append("critic")
            elif self.critic:
                tracer.record_stage("critic", 0, "skipped")

            if run_optimizer:
                optimizer_ctx = {"draft": draft.content, "original_context": enriched_context}
                parallel_agents.append(self.optimizer.run(optimizer_ctx))
                parallel_names.append("optimizer")

            if run_fact_check:
                fact_check_ctx = {"draft": draft.content, "source": context}
                parallel_agents.append(self.fact_checker.run(fact_check_ctx))
                parallel_names.append("fact_checker")
            elif self.fact_checker:
                tracer.record_stage("fact_checker", 0, "skipped")

            for name in parallel_names:
                await self._emit(name, "running")

            parallel_results = (
                await asyncio.gather(*parallel_agents, return_exceptions=True)
                if parallel_agents
                else []
            )

            # Map results back to named variables
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

            # Stage 4: Iterative revision loop (policy-controlled)
            max_iter = policy.effective_max_iterations(self.max_iterations)
            iterations_used = 0

            # Determine if revision is needed: both critic says so AND policy agrees
            critic_confidence = (
                critic_result.content.get("confidence", 0.5)
                if critic_result
                else 1.0
            )
            should_revise = (
                critic_result
                and critic_result.needs_revision
                and policy.should_revise(critic_confidence)
                and hasattr(self.drafter, "revise")
            )

            while should_revise and iterations_used < max_iter:
                iterations_used += 1
                await self._emit(
                    "drafter", "running",
                    message=f"Revision {iterations_used}/{max_iter}...",
                )
                draft = await self.drafter.revise(
                    draft,
                    feedback={
                        "critic": critic_result.feedback or {},
                        "optimizer": (optimizer_result.suggestions or {}) if optimizer_result else {},
                        "fact_check": fact_check_result.flags if fact_check_result else [],
                    },
                )
                tracer.record_stage(
                    f"drafter_revision_{iterations_used}", draft.latency_ms, "completed",
                )
                await self._emit("drafter", "completed", draft.latency_ms)

                # Re-critique the revision if we have iterations left
                if self.critic and run_critic and iterations_used < max_iter:
                    await self._emit("critic", "running", message="Re-evaluating revision...")
                    critic_ctx = {
                        "draft": draft.content,
                        "original_context": enriched_context,
                        "agent_memories": recalled_memories,
                    }
                    critic_result = await self.critic.run(critic_ctx)
                    tracer.record_stage(
                        f"critic_re_eval_{iterations_used}",
                        critic_result.latency_ms, "completed",
                    )
                    await self._emit("critic", "completed", critic_result.latency_ms)

                    # Re-check if revision is still needed
                    critic_confidence = critic_result.content.get("confidence", 0.5)
                    should_revise = (
                        critic_result.needs_revision
                        and policy.should_revise(critic_confidence)
                    )
                else:
                    break

            if iterations_used == 0 and (optimizer_result or fact_check_result):
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

            # Memory write-back — store useful learnings
            if self.memory and user_id != "unknown":
                try:
                    learning: dict[str, Any] = {
                        "pipeline": self.name,
                        "iterations_used": iterations_used,
                    }
                    if critic_result and critic_result.quality_scores:
                        learning["quality_scores"] = critic_result.quality_scores
                    if critic_result and critic_result.feedback:
                        learning["feedback_summary"] = {
                            k: v[:200] if isinstance(v, str) else v
                            for k, v in (critic_result.feedback or {}).items()
                        }
                    if optimizer_result and optimizer_result.suggestions:
                        learning["optimization_patterns"] = optimizer_result.suggestions
                    if fact_check_result:
                        summary = fact_check_result.content.get("summary", {})
                        if summary.get("fabricated", 0) > 0:
                            learning["fabrication_flags"] = summary

                    await self.memory.astore(
                        user_id, self.name,
                        f"run_{pipeline_id[:8]}",
                        learning,
                    )
                except Exception as e:
                    logger.warning("memory_writeback_failed", error=str(e))

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
