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

v3: Durable execution via WorkflowRuntime (per-stage timeout, heartbeat,
    retry, event-sourced checkpoints).  Evidence Ledger flows through all
    stages — researcher populates it, drafter cites it, fact-checker and
    validator enforce it.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import uuid4

import structlog

from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.agents.contracts import validate_stage_output, validate_pipeline_result
from ai_engine.agents.evidence import (
    EvidenceLedger,
    EvidenceSource,
    EvidenceTier,
    populate_from_jd,
    populate_from_profile,
    populate_from_tool_result,
    populate_from_company_intel,
)
from ai_engine.agents.lock import PipelineLockManager
from ai_engine.agents.memory import AgentMemory
from ai_engine.agents.tool_normalizer import normalize_all_tool_results
from ai_engine.agents.trace import AgentTracer
from ai_engine.agents.observability import PipelineMetrics
from ai_engine.agents.workflow_runtime import (
    WorkflowEventStore,
    WorkflowState,
    execute_stage,
    skip_stage,
    reconstruct_state,
    get_stage_artifacts,
)

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
    # Human-in-the-loop: stages that require approval before proceeding.
    # If a callback is registered, the pipeline will pause and call it
    # with stage results. The callback returns True to continue or False
    # to abort.
    require_human_approval_after: tuple[str, ...] = ()

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
        always_check = {"cv_generation", "cover_letter", "personal_statement", "portfolio"}
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
POLICY_STRICT = PipelinePolicy(confidence_threshold=0.90, max_iterations=3)


class AdaptivePolicyTracker:
    """Tracks pipeline outcomes and adjusts policy thresholds over time.

    Maintains a rolling window of recent quality scores per pipeline.
    When enough data accumulates, adjusts confidence_threshold:
      - If outputs are consistently high-quality → raise threshold (higher bar)
      - If outputs are consistently low-quality → lower threshold (allow more revisions)
    """

    # Class-level shared state (singleton per process, like _lock_manager)
    _history: dict[str, list[float]] = {}  # pipeline_name → [avg_scores]
    _window_size: int = 20

    @classmethod
    def record_outcome(cls, pipeline_name: str, avg_quality_score: float) -> None:
        """Record a pipeline quality outcome."""
        if pipeline_name not in cls._history:
            cls._history[pipeline_name] = []
        cls._history[pipeline_name].append(avg_quality_score)
        # Keep only recent history
        if len(cls._history[pipeline_name]) > cls._window_size:
            cls._history[pipeline_name] = cls._history[pipeline_name][-cls._window_size:]

    @classmethod
    def get_adjusted_threshold(
        cls, pipeline_name: str, base_threshold: float,
    ) -> float:
        """Return an adjusted confidence threshold based on historical outcomes.

        Returns the base threshold if not enough data (< 5 runs).
        """
        history = cls._history.get(pipeline_name, [])
        if len(history) < 5:
            return base_threshold

        avg = sum(history) / len(history)
        # avg is 0-100 scale; threshold is 0-1 scale
        normalized_avg = avg / 100.0

        if normalized_avg > 0.85:
            # Consistently high quality → raise bar slightly
            adjusted = min(base_threshold + 0.03, 0.95)
        elif normalized_avg < 0.60:
            # Consistently struggling → lower bar to allow more revision passes
            adjusted = max(base_threshold - 0.05, 0.70)
        else:
            adjusted = base_threshold

        return round(adjusted, 3)

    @classmethod
    def reset(cls) -> None:
        """Clear all history (useful for testing)."""
        cls._history.clear()


# Map pipeline names to default policies — calibrated per pipeline type
DEFAULT_POLICIES: dict[str, PipelinePolicy] = {
    "resume_parse": PipelinePolicy(skip_critique=True, skip_fact_check=True, max_iterations=1),
    "benchmark": POLICY_FULL,
    "gap_analysis": PipelinePolicy(skip_research=True, max_iterations=1),
    "cv_generation": POLICY_STRICT,                # Highest quality bar
    "cover_letter": POLICY_STRICT,                 # Highest quality bar
    "personal_statement": PipelinePolicy(          # High bar, no research needed
        skip_research=True, skip_fact_check=False,
        confidence_threshold=0.88, max_iterations=2,
    ),
    "portfolio": PipelinePolicy(skip_research=True, skip_critique=False, max_iterations=2),
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
    evidence_ledger: Optional[dict] = None      # v3: serialised EvidenceLedger
    citations: Optional[list[dict]] = None      # v3: claim→evidence links
    workflow_state: Optional[dict] = None        # v3: durable stage checkpoints
    validation_report: Optional[dict] = None     # v3.2: validator output envelope
    final_analysis_report: Optional[dict] = None # v7: optimizer final analysis
    escalation: Optional[dict] = None            # v8: human review escalation metadata
    iteration_deltas: Optional[list] = None      # v8: score deltas per revision iteration
    citation_coverage: Optional[float] = None    # v9: fraction of claims linked to >=1 evidence id (0.0-1.0)


def _compute_citation_coverage(citations: Optional[list[dict]]) -> Optional[float]:
    """Return the fraction of claims that were linked to >= 1 evidence item.

    1.0 = every claim is grounded.  0.0 = no claim could be linked.
    None = no citations were produced at all (fact-check skipped or no claims).

    This metric makes silent citation-link degradation observable: a drop
    here means the orchestrator's _rebuild_citations_from_fact_check is
    failing to match fact-checker source references against the ledger.
    """
    if not citations:
        return None
    grounded = sum(1 for c in citations if c.get("evidence_ids"))
    return round(grounded / len(citations), 3)


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
    # Safety check: when many claims are flagged (>5) AND removal would strip
    # >50% of content, the fact-checker is likely being overly aggressive
    # with resume-sourced data — skip the removal in that case.
    fabricated = fact_check_content.get("fabricated_claims", [])
    if fabricated and "html" in merged:
        html = merged["html"]
        original_len = len(html)
        for claim in fabricated:
            text = claim.get("text", "")
            if text and text in html:
                html = html.replace(text, "")
        if original_len > 0 and (len(fabricated) <= 5 or len(html) / original_len >= 0.5):
            merged["html"] = html
        # else: too many claims stripped too much — keep original content

    return merged


class AgentPipeline:
    """Policy-driven orchestrator for multi-stage agent execution.

    v3 additions:
    - Optional WorkflowEventStore for durable, event-sourced execution
    - EvidenceLedger populated by researcher and passed through all stages
    - Per-stage timeout, heartbeat, and retry via execute_stage()
    - Backward compatible: works without event store (falls back to v2 behavior)
    """

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
        on_approval_request: Optional[Callable] = None,
        ai_client: Any = None,
        db: Any = None,
        max_iterations: int = 2,
        policy: Optional[PipelinePolicy] = None,
        event_store: Optional[WorkflowEventStore] = None,
        tables: Optional[dict[str, str]] = None,
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
        self.on_approval_request = on_approval_request  # Human-in-the-loop callback
        self._ai_client = ai_client  # For LLM-driven reflection/routing decisions
        self.db = db  # Supabase client for trace persistence
        self.max_iterations = max(1, max_iterations)
        self.policy = policy or DEFAULT_POLICIES.get(name, POLICY_FULL)
        self.memory: Optional[AgentMemory] = None
        # v3: durable execution — create store from db+tables if not passed
        if event_store:
            self.event_store: Optional[WorkflowEventStore] = event_store
        elif db and tables:
            self.event_store = WorkflowEventStore(db, tables)
        else:
            self.event_store = None

    async def execute(self, context: dict) -> PipelineResult:
        pipeline_id = str(uuid4())
        user_id = context.get("user_id", "unknown")
        job_id = context.get("job_id", "")
        application_id = context.get("application_id", "")
        policy = self.policy
        tracer = AgentTracer(pipeline_id, self.name, user_id)
        # v6: pipeline-level observability metrics
        metrics = PipelineMetrics(pipeline_id, self.name, user_id)
        metrics.snapshot_cost_start()

        # v3: Initialize evidence ledger
        ledger = EvidenceLedger()

        # Populate ledger from available context
        user_profile = context.get("user_profile", {})
        if user_profile:
            populate_from_profile(ledger, user_profile)

        company_intel = context.get("company_intel", {})
        if company_intel:
            populate_from_company_intel(ledger, company_intel)

        # v3: Initialize workflow state for durable execution
        wf_state: Optional[WorkflowState] = None
        store = self.event_store
        if store and job_id:
            wf_state = WorkflowState(
                workflow_id=pipeline_id,
                pipeline_name=self.name,
                user_id=user_id,
                job_id=job_id,
                application_id=application_id,
            )
            await store.emit(
                wf_state,
                event_name="workflow_start",
                message=f"Starting {self.name} pipeline",
                payload={
                    "workflow_id": pipeline_id,
                    "pipeline_name": self.name,
                    "evidence_count": len(ledger),
                },
            )

        async with self.lock_manager.acquire(user_id, self.name, pipeline_id):
            # Initialize variables used in finally for partial persistence
            critic_result = optimizer_result = fact_check_result = None
            draft = None
            validation = None
            citations: list[dict] = []
            iterations_used = 0

            try:
                return await self._execute_pipeline_stages(
                    context=context,
                    pipeline_id=pipeline_id,
                    user_id=user_id,
                    job_id=job_id,
                    application_id=application_id,
                    policy=policy,
                    tracer=tracer,
                    ledger=ledger,
                    wf_state=wf_state,
                    store=store,
                    metrics=metrics,
                )
            except Exception:
                # Persist partial evidence/citations on failure so forensic
                # inspection and future resume have real state.
                if wf_state and store:
                    try:
                        await store.emit(
                            wf_state,
                            event_name="workflow_failed",
                            message=f"{self.name} pipeline failed",
                            payload={"evidence_count": len(ledger)},
                        )
                        await store.persist_evidence(
                            job_id, user_id,
                            [item.to_dict() for item in ledger.items],
                        )
                        if self._partial_citations:
                            await store.persist_citations(
                                job_id, user_id, self._partial_citations,
                            )
                    except Exception as persist_err:
                        logger.warning(
                            "partial_evidence_persist_failed",
                            pipeline=self.name,
                            error=str(persist_err),
                        )
                raise

    async def _execute_pipeline_stages(
        self,
        *,
        context: dict,
        pipeline_id: str,
        user_id: str,
        job_id: str,
        application_id: str,
        policy: PipelinePolicy,
        tracer: AgentTracer,
        ledger: EvidenceLedger,
        wf_state: Optional[WorkflowState],
        store: Optional[WorkflowEventStore],
        metrics: PipelineMetrics,
    ) -> PipelineResult:
        """Core pipeline stage execution — extracted for clean error handling."""
        self._partial_citations: list[dict] = []

        enriched_context = dict(context)
        enriched_context.setdefault("pipeline", self.name)
        enriched_context.setdefault("pipeline_name", self.name)

        # ── Cost optimization: inject application brief if available ──
        # When an ApplicationBrief is present, agents use its compact
        # to_prompt_context() (~1.5-3K tokens) instead of raw JD/resume/profile
        # (~10-25K tokens). This saves ~80% input tokens per call.
        application_brief = context.get("application_brief")
        if application_brief is not None:
            enriched_context["application_brief"] = application_brief
            # Provide the compact prompt context for all agents
            if hasattr(application_brief, "to_prompt_context"):
                enriched_context["brief_context"] = application_brief.to_prompt_context()
            logger.info(
                "pipeline_brief_injected",
                pipeline=self.name,
                brief_hash=getattr(application_brief, "brief_hash", "?"),
                match_score=getattr(application_brief, "match_score", 0),
            )

        # v3: resume support — determine which stages to skip
        _STAGE_ORDER = ["researcher", "drafter", "critic", "optimizer", "fact_checker", "optimizer_final_analysis", "validator"]
        resume_from = context.get("resume_from_stage")
        resume_skip: set[str] = set()
        # v3.1: rehydrated artifacts from prior pipeline run
        _rehydrated_artifacts: dict[str, dict] = {}
        if resume_from and resume_from in _STAGE_ORDER:
            idx = _STAGE_ORDER.index(resume_from)
            resume_skip = set(_STAGE_ORDER[:idx])
            logger.info("pipeline_resume", pipeline=self.name, resume_from=resume_from, skipping=list(resume_skip))

            # v3.1: rehydrate artifacts from persisted events
            if store and job_id:
                try:
                    pipeline_events = await store.load_events_for_pipeline(job_id, self.name)
                    if pipeline_events:
                        prior_state = reconstruct_state(pipeline_events, job_id)
                        _rehydrated_artifacts = get_stage_artifacts(prior_state)
                        logger.info(
                            "pipeline_artifacts_rehydrated",
                            pipeline=self.name,
                            artifacts=list(_rehydrated_artifacts.keys()),
                        )
                except Exception as e:
                    logger.warning("pipeline_artifact_rehydration_failed", error=str(e))

        # v3: inject evidence ledger into context for all agents
        enriched_context["evidence_ledger"] = ledger

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

        def _rebuild_citations_from_fact_check(
            fact_result: Optional[AgentResult],
        ) -> list[dict]:
            """Rebuild citations from the current fact-check result and ledger state."""
            rebuilt: list[dict] = []
            tier_rank = {
                EvidenceTier.VERBATIM: 0,
                EvidenceTier.DERIVED: 1,
                EvidenceTier.INFERRED: 2,
                EvidenceTier.USER_STATED: 3,
            }

            if not fact_result:
                self._partial_citations = rebuilt
                return rebuilt

            for claim in fact_result.content.get("claims", []):
                classification = claim.get("classification", "")
                if classification in ("verified", "supported"):
                    ledger.add(
                        tier=(
                            EvidenceTier.VERBATIM
                            if classification == "verified"
                            else EvidenceTier.DERIVED
                        ),
                        source=EvidenceSource.TOOL,
                        source_field=f"fact_checker.claim.{classification}",
                        text=claim.get("text", ""),
                        metadata={
                            "confidence": claim.get("confidence", 0),
                            "method": claim.get("method", "unknown"),
                        },
                    )

                matched_ids: list[str] = []

                ev_sources = claim.get("evidence_sources") or []
                for src in ev_sources:
                    src_str = str(src)
                    if ":" in src_str:
                        pool_val = src_str.split(":", 1)[1]
                        pool_val = pool_val.split("(")[0].strip()
                        if pool_val:
                            matches = ledger.find_by_text(pool_val)
                            for match in matches[:2]:
                                if match.id not in matched_ids:
                                    matched_ids.append(match.id)

                if not matched_ids:
                    source_ref = claim.get("source_reference", "")
                    if source_ref:
                        for ref_part in source_ref.split(","):
                            ref_part = ref_part.strip()
                            if ":" in ref_part:
                                ref_part = ref_part.split(":", 1)[1].split("(")[0].strip()
                            if ref_part and len(ref_part) > 2:
                                matches = ledger.find_by_text(ref_part)
                                for match in matches[:2]:
                                    if match.id not in matched_ids:
                                        matched_ids.append(match.id)

                evidence_tiers = [
                    item.tier
                    for item in (ledger.get(evidence_id) for evidence_id in matched_ids)
                    if item is not None
                ]
                weakest_tier = ""
                if evidence_tiers:
                    weakest_tier = max(
                        evidence_tiers,
                        key=lambda value: tier_rank[value],
                    ).value

                rebuilt.append({
                    "claim_text": claim.get("text", ""),
                    "evidence_ids": matched_ids,
                    "classification": classification,
                    "confidence": claim.get("confidence", 0),
                    "tier": weakest_tier,
                })

            self._partial_citations = rebuilt
            return rebuilt

        # Stage 1: Research (policy-gated, resume-aware)
        run_research = (
            self.researcher
            and policy.should_research(self.name, enriched_context)
            and "researcher" not in resume_skip
        )
        if run_research:
            if wf_state and store:
                research = await execute_stage(
                    "researcher",
                    lambda: self.researcher.run(enriched_context),
                    wf_state, store,
                    on_progress=self.on_stage_update,
                )
            else:
                await self._emit("researcher", "running")
                research = await self.researcher.run(enriched_context)
                await self._emit("researcher", "completed", research.latency_ms)
            tracer.record_stage("researcher", research.latency_ms, "completed")
            enriched_context["research"] = research.content

            # v4: validate researcher contract
            researcher_issues = validate_stage_output("researcher", research.content)
            if researcher_issues:
                logger.warning("researcher_contract_drift", issues=researcher_issues, pipeline=self.name)
            metrics.record_contract_issues("researcher", researcher_issues)
            metrics.record_stage_latency("researcher", research.latency_ms)

            # v3: populate ledger from researcher's tool results
            tool_results = research.content.get("tool_results", {})
            if not tool_results:
                tool_results = research.metadata.get("tool_results", {})
            # v4: normalize tool output keys before evidence ingestion
            tool_results = normalize_all_tool_results(tool_results)
            for tool_name, tool_result in tool_results.items():
                if isinstance(tool_result, dict):
                    populate_from_tool_result(ledger, tool_name, tool_result)
            jd_parsed = tool_results.get("parse_jd", {})
            if jd_parsed:
                populate_from_jd(ledger, jd_parsed)

            # v3.1: persist researcher artifact for resume
            if wf_state and store:
                await store.persist_artifact(wf_state, "researcher", {
                    "content": research.content,
                    "metadata": research.metadata,
                    "latency_ms": research.latency_ms,
                })

        elif self.researcher:
            skip_reason = "Resume: already completed" if "researcher" in resume_skip else "Policy: skipped"
            if wf_state and store:
                await skip_stage("researcher", wf_state, skip_reason, store)
            else:
                await self._emit("researcher", "skipped", message=skip_reason)
            tracer.record_stage("researcher", 0, "skipped")
            # v3.1: rehydrate researcher artifact on resume
            if "researcher" in resume_skip and "researcher" in _rehydrated_artifacts:
                art = _rehydrated_artifacts["researcher"]
                enriched_context["research"] = art.get("content", {})
                logger.info("researcher_artifact_rehydrated", pipeline=self.name)

        # v3: inject ledger prompt context for drafter
        enriched_context["evidence_ledger_prompt"] = ledger.to_prompt_context()
        enriched_context["evidence_ledger_data"] = ledger.to_dict()

        # Stage 2: Draft (always runs unless resumed past)
        if "drafter" in resume_skip:
            if wf_state and store:
                await skip_stage("drafter", wf_state, "Resume: already completed", store)
            tracer.record_stage("drafter", 0, "skipped")
            # v3.1: rehydrate drafter artifact — use real content, not empty placeholder
            from ai_engine.agents.base import AgentResult as _AR
            rehydrated_draft = _rehydrated_artifacts.get("drafter", {})
            draft = _AR(
                content=rehydrated_draft.get("content", {}),
                quality_scores=rehydrated_draft.get("quality_scores", {}),
                flags=rehydrated_draft.get("flags", []),
                latency_ms=rehydrated_draft.get("latency_ms", 0),
                metadata=rehydrated_draft.get("metadata", {}),
            )
            if rehydrated_draft:
                logger.info("drafter_artifact_rehydrated", pipeline=self.name, has_content=bool(draft.content))
        elif wf_state and store:
            draft = await execute_stage(
                "drafter",
                lambda: self.drafter.run(enriched_context),
                wf_state, store,
                on_progress=self.on_stage_update,
            )
        else:
            await self._emit("drafter", "running")
            draft = await self.drafter.run(enriched_context)
        if "drafter" not in resume_skip:
            tracer.record_stage("drafter", draft.latency_ms, "completed")
            await self._emit("drafter", "completed", draft.latency_ms)
            # v3.1: persist drafter artifact for resume
            if wf_state and store:
                await store.persist_artifact(wf_state, "drafter", {
                    "content": draft.content,
                    "quality_scores": draft.quality_scores if hasattr(draft, "quality_scores") else {},
                    "flags": draft.flags if hasattr(draft, "flags") else [],
                    "latency_ms": draft.latency_ms,
                    "metadata": draft.metadata if hasattr(draft, "metadata") else {},
                })

        # v4: validate drafter contract
        drafter_issues = validate_stage_output("drafter", draft.content)
        if drafter_issues:
            logger.warning("drafter_contract_drift", issues=drafter_issues, pipeline=self.name)
        metrics.record_contract_issues("drafter", drafter_issues)
        metrics.record_stage_latency("drafter", draft.latency_ms)

        # ── Human-in-the-loop gate: after drafter ──
        if not await self._request_approval("drafter", draft, enriched_context):
            return PipelineResult(
                content=draft.content,
                quality_scores={},
                optimization_report={},
                fact_check_report={},
                iterations_used=0,
                total_latency_ms=sum(s["latency_ms"] for s in tracer.stages),
                trace_id=pipeline_id,
                evidence_ledger=ledger.to_dict(),
                citations=[],
                validation_report={"status": "aborted", "reason": "Human review rejected after drafter"},
            )

        # Stage 3: Parallel evaluation agents (policy-gated)
        # v3: inject evidence ledger into eval agent contexts
        # v3: also kick off drafter sub-agents (tone/keyword) in parallel with evaluation
        drafter_sub_task = None
        if hasattr(self.drafter, "run_with_sub_agents") and enriched_context.get("jd_text"):
            drafter_sub_task = asyncio.ensure_future(
                self.drafter.run_with_sub_agents(enriched_context, draft)
            )

        parallel_agents = []
        parallel_names = []

        run_critic = self.critic and policy.should_critique(self.name) and "critic" not in resume_skip
        run_optimizer = self.optimizer is not None and "optimizer" not in resume_skip
        run_fact_check = (
            self.fact_checker
            and policy.should_fact_check(self.name, draft.content)
            and "fact_checker" not in resume_skip
        )

        if run_critic:
            critic_ctx = {
                "draft": draft.content,
                "original_context": enriched_context,
                "agent_memories": recalled_memories,
                "evidence_ledger": ledger,
            }
            parallel_agents.append(self.critic.run(critic_ctx))
            parallel_names.append("critic")
        elif self.critic:
            tracer.record_stage("critic", 0, "skipped")
            if wf_state and store:
                await skip_stage("critic", wf_state, "Policy: skipped", store)

        if run_optimizer:
            optimizer_ctx = {
                "draft": draft.content,
                "original_context": enriched_context,
                "evidence_ledger": ledger,
            }
            parallel_agents.append(self.optimizer.run(optimizer_ctx))
            parallel_names.append("optimizer")

        if run_fact_check:
            fact_check_ctx = {
                "draft": draft.content,
                "source": context,
                "evidence_ledger": ledger,
            }
            parallel_agents.append(self.fact_checker.run(fact_check_ctx))
            parallel_names.append("fact_checker")
        elif self.fact_checker:
            tracer.record_stage("fact_checker", 0, "skipped")
            if wf_state and store:
                await skip_stage("fact_checker", wf_state, "Policy: skipped", store)

        for name in parallel_names:
            await self._emit(name, "running")

        # v3: Also schedule sub-agent parallel evaluations alongside main evaluations
        sub_agent_tasks: list[asyncio.Task] = []
        sub_agent_labels: list[str] = []
        if run_critic and self.critic and hasattr(self.critic, "run_parallel_evaluation"):
            coro = self.critic.run_parallel_evaluation({
                "content": draft.content,
                "original_context": enriched_context,
            })
            sub_agent_tasks.append(asyncio.ensure_future(coro))
            sub_agent_labels.append("critic_sub_agents")
        if run_optimizer and self.optimizer and hasattr(self.optimizer, "run_parallel_evaluation"):
            coro = self.optimizer.run_parallel_evaluation({
                "content": draft.content,
                "original_context": enriched_context,
            })
            sub_agent_tasks.append(asyncio.ensure_future(coro))
            sub_agent_labels.append("optimizer_sub_agents")

        parallel_results = (
            await asyncio.gather(*parallel_agents, return_exceptions=True)
            if parallel_agents
            else []
        )

        # Collect sub-agent results (non-blocking, ignore failures)
        sub_agent_data: dict = {}
        if sub_agent_tasks:
            sub_results = await asyncio.gather(*sub_agent_tasks, return_exceptions=True)
            for label, res in zip(sub_agent_labels, sub_results):
                if not isinstance(res, Exception):
                    sub_agent_data[label] = res
                else:
                    logger.debug("sub_agent_eval_failed", label=label, error=str(res))

        # Collect drafter sub-agent results (tone calibrator + keyword strategist)
        if drafter_sub_task is not None:
            try:
                drafter_sub_data = await drafter_sub_task
                sub_agent_data["drafter_sub_agents"] = drafter_sub_data
            except Exception as exc:
                logger.debug("drafter_sub_agents_failed", error=str(exc))

        # Map results back to named variables
        critic_result = optimizer_result = fact_check_result = None
        for name, result in zip(parallel_names, parallel_results):
            if isinstance(result, Exception):
                logger.warning("parallel_agent_failed", agent=name, error=str(result))
                tracer.record_stage(name, 0, "failed")
                await self._emit(name, "failed", message=str(result))
                if wf_state:
                    from ai_engine.agents.workflow_runtime import StageCheckpoint as _SC, StageStatus as _SS
                    wf_state.stages[name] = _SC(
                        stage_name=name, status=_SS.FAILED, error=str(result),
                    )
                continue
            tracer.record_stage(name, result.latency_ms, "completed")
            await self._emit(name, "completed", result.latency_ms)
            if name == "critic":
                critic_result = result
                # v4: validate critic contract
                critic_issues = validate_stage_output("critic", result.content)
                if critic_issues:
                    logger.warning("critic_contract_drift", issues=critic_issues, pipeline=self.name)
                metrics.record_contract_issues("critic", critic_issues)
                metrics.record_stage_latency("critic", result.latency_ms)
            elif name == "optimizer":
                optimizer_result = result
                # v4: validate optimizer contract
                opt_issues = validate_stage_output("optimizer", result.content)
                if opt_issues:
                    logger.warning("optimizer_contract_drift", issues=opt_issues, pipeline=self.name)
                metrics.record_contract_issues("optimizer", opt_issues)
                metrics.record_stage_latency("optimizer", result.latency_ms)
            elif name == "fact_checker":
                fact_check_result = result
                # v4: validate fact_checker contract
                fc_issues = validate_stage_output("fact_checker", result.content)
                if fc_issues:
                    logger.warning("fact_checker_contract_drift", issues=fc_issues, pipeline=self.name)
                metrics.record_contract_issues("fact_checker", fc_issues)
                metrics.record_stage_latency("fact_checker", result.latency_ms)

        # ── Human-in-the-loop gate: after critic evaluation ──
        if critic_result and not await self._request_approval("critic", critic_result, enriched_context):
            return PipelineResult(
                content=draft.content,
                quality_scores=critic_result.quality_scores if critic_result else {},
                optimization_report=optimizer_result.content if optimizer_result else {},
                fact_check_report=fact_check_result.content if fact_check_result else {},
                iterations_used=0,
                total_latency_ms=sum(s["latency_ms"] for s in tracer.stages),
                trace_id=pipeline_id,
                evidence_ledger=ledger.to_dict(),
                citations=[],
                validation_report={"status": "aborted", "reason": "Human review rejected after critic"},
            )

        citations = _rebuild_citations_from_fact_check(fact_check_result)

        # ═══════════════════════════════════════════════════════════════
        #  LLM-driven reflection: ASK the LLM what the pipeline should
        #  do next, based on evaluation results.  The LLM chooses from:
        #    "accept"               — skip revision, go to validation
        #    "revise"               — standard full revision loop
        #    "revise_targeted"      — revise only specific dimensions/issues
        #    "re_research"          — redo ALL research + re-draft
        #    "re_research_targeted" — re-research specific claim categories
        #    "escalate"             — flag for human review, skip revision
        #  Falls back to rule-based logic if LLM reflection fails.
        # ═══════════════════════════════════════════════════════════════
        reflection = await self._reflect_on_evaluation(
            critic_result=critic_result,
            optimizer_result=optimizer_result,
            fact_check_result=fact_check_result,
            draft_content=draft.content,
            pipeline_name=self.name,
        )
        llm_decision = reflection["decision"]

        # ── Dynamic re-routing: re-research on high fabrication count ──
        # Fires if LLM says "re_research"/"re_research_targeted" OR rule-based fallback triggers.
        _did_reroute_research = False
        need_re_research = llm_decision in ("re_research", "re_research_targeted")
        if not need_re_research and fact_check_result:
            # Rule-based fallback: ≥5 fabricated claims
            fc_summary = fact_check_result.content.get("summary", {})
            need_re_research = fc_summary.get("fabricated", 0) >= 5

        if need_re_research and self.researcher and not _did_reroute_research:
            _did_reroute_research = True
            fc_summary = fact_check_result.content.get("summary", {}) if fact_check_result else {}
            fabricated_count = fc_summary.get("fabricated", 0)
            logger.warning(
                "dynamic_reroute_re_research",
                fabricated=fabricated_count,
                decision_source=llm_decision,
                pipeline=self.name,
            )
            await self._emit("researcher", "running", message="Re-researching: evidence quality insufficient")

            reroute_ctx = dict(enriched_context)
            reroute_ctx["_reroute_reason"] = (
                f"Re-research triggered (LLM decision: {llm_decision}, fabricated: {fabricated_count}). "
                "Gather stronger evidence and verify all profile claims."
            )
            if fact_check_result:
                reroute_ctx["_fabricated_claims"] = fact_check_result.content.get("claims", [])

            # For targeted re-research, pass specific categories so researcher can focus
            if llm_decision == "re_research_targeted":
                research_targets = reflection.get("research_targets", {})
                reroute_ctx["_research_targets"] = research_targets
                reroute_ctx["_reroute_reason"] = (
                    f"Targeted re-research (categories: {research_targets.get('categories', [])}). "
                    "Focus on verifying claims in these specific areas."
                )

            try:
                re_research = await self.researcher.run(reroute_ctx)
                tracer.record_stage("researcher_reroute", re_research.latency_ms, "completed")
                enriched_context["research"] = re_research.content
                await self._emit("researcher", "completed", re_research.latency_ms, message="Re-research complete")

                # Re-populate evidence ledger
                tool_results = re_research.content.get("tool_results", {})
                tool_results = normalize_all_tool_results(tool_results)
                for tool_name, tool_result in tool_results.items():
                    if isinstance(tool_result, dict):
                        populate_from_tool_result(ledger, tool_name, tool_result)

                enriched_context["evidence_ledger_prompt"] = ledger.to_prompt_context()
                enriched_context["evidence_ledger_data"] = ledger.to_dict()

                # Re-draft with improved context
                await self._emit("drafter", "running", message="Re-drafting with improved research")
                draft = await self.drafter.run(enriched_context)
                tracer.record_stage("drafter_reroute", draft.latency_ms, "completed")
                await self._emit("drafter", "completed", draft.latency_ms)
            except Exception as e:
                logger.warning("reroute_re_research_failed", error=str(e))

        # Stage 4: Iterative revision loop (policy-controlled)
        # Adaptive policy: adjust threshold based on historical outcomes
        adjusted_threshold = AdaptivePolicyTracker.get_adjusted_threshold(
            self.name, policy.confidence_threshold,
        )
        if adjusted_threshold != policy.confidence_threshold:
            logger.info(
                "adaptive_threshold_adjustment",
                pipeline=self.name,
                base=policy.confidence_threshold,
                adjusted=adjusted_threshold,
            )
            policy = dataclasses.replace(policy, confidence_threshold=adjusted_threshold)

        max_iter = policy.effective_max_iterations(self.max_iterations)
        iterations_used = 0

        # Determine if revision is needed: LLM decision + critic + policy
        critic_confidence = (
            critic_result.content.get("confidence", 0.5)
            if critic_result
            else 1.0
        )

        # LLM reflection took priority: "accept"/"escalate" means skip revision entirely
        if llm_decision == "accept":
            should_revise = False
            logger.info("llm_reflection_accept", pipeline=self.name)
        elif llm_decision == "escalate":
            should_revise = False
            logger.warning(
                "llm_reflection_escalate",
                pipeline=self.name,
                reasoning=reflection.get("reasoning", "")[:200],
            )
            # Attach escalation metadata so callers know this needs human review
            if not hasattr(self, "_escalation"):
                self._escalation = {
                    "escalated": True,
                    "reasoning": reflection.get("reasoning", ""),
                    "quality_scores": critic_result.quality_scores if critic_result else {},
                }
        else:
            should_revise = (
                critic_result
                and critic_result.needs_revision
                and policy.should_revise(critic_confidence)
                and hasattr(self.drafter, "revise")
            )
            # LLM said "revise"/"revise_targeted" — override policy if LLM actually decided
            if llm_decision in ("revise", "revise_targeted") and self._ai_client and hasattr(self.drafter, "revise") and critic_result:
                should_revise = True

        # Build revision_scope for targeted revisions
        _revision_scope = None
        if llm_decision == "revise_targeted":
            _revision_scope = reflection.get("revision_scope", {})

        # ── Dynamic re-routing: skip revision if all scores already pass ──
        if should_revise and critic_result and critic_result.quality_scores:
            qs = critic_result.quality_scores
            pass_threshold = policy.confidence_threshold * 100  # scale to 0-100
            all_pass = all(
                qs.get(dim, 0) >= pass_threshold
                for dim in ("impact", "clarity", "tone_match", "completeness")
            )
            if all_pass:
                logger.info(
                    "dynamic_skip_revision",
                    scores=qs,
                    threshold=pass_threshold,
                    pipeline=self.name,
                )
                should_revise = False

        # Track score deltas across iterations for observability
        iteration_deltas: list[dict] = []

        while should_revise and iterations_used < max_iter:
            iterations_used += 1
            scores_before = dict(critic_result.quality_scores) if critic_result and critic_result.quality_scores else {}
            revision_feedback = {
                "critic": critic_result.feedback or {},
                "optimizer": optimizer_result.content if optimizer_result else {},
                "fact_check": fact_check_result.flags if fact_check_result else [],
                "evidence_ledger_prompt": ledger.to_prompt_context(),
                "citations": citations,
            }

            # v3: merge sub-agent evaluation insights into revision feedback
            if sub_agent_data.get("critic_sub_agents"):
                sa = sub_agent_data["critic_sub_agents"]
                revision_feedback["sub_agent_scores"] = sa.get("sub_agent_scores", {})
                revision_feedback["sub_agent_issues"] = sa.get("sub_agent_issues", [])
            if sub_agent_data.get("optimizer_sub_agents"):
                revision_feedback["optimizer_sub_agents"] = sub_agent_data["optimizer_sub_agents"]
            if sub_agent_data.get("drafter_sub_agents"):
                drafter_sa = sub_agent_data["drafter_sub_agents"]
                if drafter_sa.get("tone_calibration"):
                    revision_feedback["tone_calibration"] = drafter_sa["tone_calibration"]
                if drafter_sa.get("keyword_strategy"):
                    revision_feedback["keyword_strategy"] = drafter_sa["keyword_strategy"]

            stage_name = f"drafter_revision_{iterations_used}"
            if wf_state and store:
                draft = await execute_stage(
                    stage_name,
                    lambda: self.drafter.revise(draft, feedback=revision_feedback, revision_scope=_revision_scope),
                    wf_state, store,
                    on_progress=self.on_stage_update,
                )
            else:
                await self._emit(
                    "drafter", "running",
                    message=f"Revision {iterations_used}/{max_iter}...",
                )
                draft = await self.drafter.revise(draft, feedback=revision_feedback, revision_scope=_revision_scope)
                await self._emit("drafter", "completed", draft.latency_ms)
            tracer.record_stage(stage_name, draft.latency_ms, "completed")
            revision_issues = validate_stage_output(stage_name, draft.content)
            if revision_issues:
                logger.warning(
                    "drafter_contract_drift",
                    stage=stage_name,
                    issues=revision_issues,
                    pipeline=self.name,
                )
            metrics.record_contract_issues(stage_name, revision_issues)
            metrics.record_stage_latency(stage_name, draft.latency_ms)

            # Re-critique the revision if we have iterations left
            if self.critic and run_critic and iterations_used < max_iter:
                re_eval_name = f"critic_re_eval_{iterations_used}"
                previous_quality_scores = critic_result.quality_scores if critic_result else {}
                critic_ctx = {
                    "draft": draft.content,
                    "original_context": enriched_context,
                    "agent_memories": recalled_memories,
                    "evidence_ledger": ledger,
                    "previous_quality_scores": previous_quality_scores,
                }
                if wf_state and store:
                    critic_result = await execute_stage(
                        re_eval_name,
                        lambda: self.critic.run(critic_ctx),
                        wf_state, store,
                        on_progress=self.on_stage_update,
                    )
                else:
                    await self._emit("critic", "running", message="Re-evaluating revision...")
                    critic_result = await self.critic.run(critic_ctx)
                    await self._emit("critic", "completed", critic_result.latency_ms)
                tracer.record_stage(re_eval_name, critic_result.latency_ms, "completed")
                re_eval_issues = validate_stage_output(re_eval_name, critic_result.content)
                if re_eval_issues:
                    logger.warning(
                        "critic_contract_drift",
                        stage=re_eval_name,
                        issues=re_eval_issues,
                        pipeline=self.name,
                    )
                metrics.record_contract_issues(re_eval_name, re_eval_issues)
                metrics.record_stage_latency(re_eval_name, critic_result.latency_ms)

                # Re-check if revision is still needed
                critic_confidence = critic_result.content.get("confidence", 0.5)
                should_revise = (
                    critic_result.needs_revision
                    and policy.should_revise(critic_confidence)
                )

                # Record iteration delta
                scores_after = dict(critic_result.quality_scores) if critic_result.quality_scores else {}
                iteration_deltas.append({
                    "iteration": iterations_used,
                    "scores_before": scores_before,
                    "scores_after": scores_after,
                    "delta": {
                        k: scores_after.get(k, 0) - scores_before.get(k, 0)
                        for k in set(list(scores_before.keys()) + list(scores_after.keys()))
                    },
                })
            else:
                break

        if iterations_used > 0 and self.fact_checker and run_fact_check:
            final_fact_check_name = "fact_checker_final"
            final_fact_check_ctx = {
                "draft": draft.content,
                "source": context,
                "evidence_ledger": ledger,
            }
            if wf_state and store:
                fact_check_result = await execute_stage(
                    final_fact_check_name,
                    lambda: self.fact_checker.run(final_fact_check_ctx),
                    wf_state,
                    store,
                    on_progress=self.on_stage_update,
                )
            else:
                await self._emit(
                    "fact_checker",
                    "running",
                    message="Re-checking revised claims...",
                )
                fact_check_result = await self.fact_checker.run(final_fact_check_ctx)
                await self._emit("fact_checker", "completed", fact_check_result.latency_ms)
            tracer.record_stage(final_fact_check_name, fact_check_result.latency_ms, "completed")
            final_fact_check_issues = validate_stage_output(final_fact_check_name, fact_check_result.content)
            if final_fact_check_issues:
                logger.warning(
                    "fact_checker_contract_drift",
                    stage=final_fact_check_name,
                    issues=final_fact_check_issues,
                    pipeline=self.name,
                )
            metrics.record_contract_issues(final_fact_check_name, final_fact_check_issues)
            metrics.record_stage_latency(final_fact_check_name, fact_check_result.latency_ms)
            citations = _rebuild_citations_from_fact_check(fact_check_result)

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
                metadata={**(draft.metadata or {}), "pipeline": self.name},
            )

        # ── Stage 4b: Optimizer Final Analysis (analysis-only, no mutations) ──
        # Runs after all content changes and fact-check are complete.
        # Produces residual quality report comparing initial vs final scores.
        final_analysis_result = None
        if self.optimizer and hasattr(self.optimizer, "run_final_analysis"):
            initial_ats = (
                optimizer_result.content.get("ats_score", 0)
                if optimizer_result
                else 0.0
            )
            initial_readability = (
                optimizer_result.content.get("readability_score", 0)
                if optimizer_result
                else 0.0
            )
            final_analysis_ctx = {
                "draft": draft.content,
                "original_context": enriched_context,
            }
            final_analysis_name = "optimizer_final_analysis"
            await self._emit(final_analysis_name, "running")
            if wf_state and store:
                final_analysis_result = await execute_stage(
                    final_analysis_name,
                    lambda: self.optimizer.run_final_analysis(
                        final_analysis_ctx,
                        initial_ats_score=initial_ats,
                        initial_readability=initial_readability,
                    ),
                    wf_state, store,
                    on_progress=self.on_stage_update,
                )
            else:
                final_analysis_result = await self.optimizer.run_final_analysis(
                    final_analysis_ctx,
                    initial_ats_score=initial_ats,
                    initial_readability=initial_readability,
                )
            await self._emit(final_analysis_name, "completed", final_analysis_result.latency_ms)
            tracer.record_stage(final_analysis_name, final_analysis_result.latency_ms, "completed")

            fa_issues = validate_stage_output(final_analysis_name, final_analysis_result.content)
            if fa_issues:
                logger.warning(
                    "optimizer_final_analysis_contract_drift",
                    issues=fa_issues,
                    pipeline=self.name,
                )
            metrics.record_contract_issues(final_analysis_name, fa_issues)
            metrics.record_stage_latency(final_analysis_name, final_analysis_result.latency_ms)

            fa = final_analysis_result.content
            metrics.record_final_analysis(
                initial_ats_score=fa.get("initial_ats_score", 0),
                final_ats_score=fa.get("final_ats_score", 0),
                keyword_gap_delta=fa.get("keyword_gap_delta", 0),
                readability_delta=fa.get("readability_delta", 0),
                residual_issue_count=fa.get("residual_issue_count", 0),
            )

        # Stage 5: Validate (v3: inject evidence ledger for enforcement)
        if self.validator:
            draft_metadata = {**(draft.metadata or {}), "pipeline": self.name}
            validator_ctx = {
                "draft": draft.content,
                "metadata": draft_metadata,
                "evidence_ledger": ledger,
                "citations": citations,
                "final_analysis": final_analysis_result.content if final_analysis_result else None,
            }
            if wf_state and store:
                validation = await execute_stage(
                    "validator",
                    lambda: self.validator.run(validator_ctx),
                    wf_state, store,
                    on_progress=self.on_stage_update,
                )
            else:
                await self._emit("validator", "running")
                validation = await self.validator.run(validator_ctx)
                await self._emit("validator", "completed", validation.latency_ms)
            tracer.record_stage("validator", validation.latency_ms, "completed")
            # v4: validate validator contract
            validator_issues = validate_stage_output("validator", validation.content)
            if validator_issues:
                logger.warning("validator_contract_drift", issues=validator_issues, pipeline=self.name)
            metrics.record_contract_issues("validator", validator_issues)
            metrics.record_stage_latency("validator", validation.latency_ms)
        else:
            validation = draft

        total_latency = sum(s["latency_ms"] for s in tracer.stages)

        if self.db:
            tracer.persist(self.db)

        # v3: emit workflow_complete event
        if wf_state and store:
            await store.emit(
                wf_state,
                event_name="workflow_complete",
                message=f"{self.name} pipeline completed",
                payload={
                    "iterations_used": iterations_used,
                    "total_latency_ms": total_latency,
                    "evidence_count": len(ledger),
                    "citation_count": len(citations),
                },
            )
            await store.update_job(job_id, {"status": "succeeded"})
            # Clear resume_from_stage after successful completion
            if resume_from:
                await store.update_job(job_id, {"resume_from_stage": None})

            # v3: persist evidence ledger and citations to DB
            await store.persist_evidence(
                job_id, user_id,
                [item.to_dict() for item in ledger.items],
            )
            await store.persist_citations(job_id, user_id, citations)

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

                # v8: automatic memory feedback — rate recalled memories as
                # useful/useless based on pipeline outcome quality scores.
                if recalled_memories and critic_result and critic_result.quality_scores:
                    avg_score = sum(
                        critic_result.quality_scores.get(d, 0)
                        for d in ("impact", "clarity", "tone_match", "completeness")
                    ) / 4.0
                    was_useful = avg_score >= 70  # above passing threshold
                    for mem in recalled_memories:
                        mem_id = mem.get("id")
                        if mem_id:
                            try:
                                await self.memory.afeedback(mem_id, was_useful)
                            except Exception:
                                pass  # best-effort, don't fail pipeline

            except Exception as e:
                logger.warning("memory_writeback_failed", error=str(e))

        final_content = draft.content
        validation_report = validation.content if self.validator else None
        if isinstance(validation_report, dict):
            nested_content = validation_report.get("content")
            if isinstance(nested_content, dict):
                final_content = nested_content

        # v4: validate final pipeline result
        pipeline_issues = validate_pipeline_result(final_content)
        if pipeline_issues:
            logger.warning("pipeline_result_contract_drift", issues=pipeline_issues, pipeline=self.name)
        metrics.record_contract_issues("pipeline_result", pipeline_issues)

        # v6: record evidence and quality stats, then emit summary
        cited_ids = {eid for c in citations for eid in c.get("evidence_ids", [])}
        tier_dist: dict[str, int] = {}
        for item in ledger.items:
            tier_dist[item.tier] = tier_dist.get(item.tier, 0) + 1
        metrics.record_evidence_stats(
            total_items=len(ledger),
            cited_count=len(cited_ids),
            tier_distribution=tier_dist,
        )
        if critic_result and critic_result.quality_scores:
            metrics.record_quality_scores(critic_result.quality_scores)
        metrics.snapshot_cost_end()
        metrics.emit()

        # Adaptive policy: record outcome for future threshold adjustments
        if critic_result and critic_result.quality_scores:
            qs = critic_result.quality_scores
            avg_q = sum(
                qs.get(d, 0)
                for d in ("impact", "clarity", "tone_match", "completeness")
            ) / 4.0
            AdaptivePolicyTracker.record_outcome(self.name, avg_q)

        # ── Pipeline Telemetry — persist cost, token, and quality data ─
        try:
            if self.db and user_id and user_id != "unknown":
                from app.services.career_analytics import PipelineTelemetryService
                telemetry_svc = PipelineTelemetryService()
                token_data = {}
                cost_cents = 0
                cascade_count = 0
                if self._ai_client:
                    tu = self._ai_client.token_usage
                    token_data = {
                        "prompt_tokens": tu.get("prompt_tokens", 0),
                        "completion_tokens": tu.get("completion_tokens", 0),
                        "total_tokens": tu.get("total_tokens", 0),
                        "call_count": tu.get("call_count", 0),
                    }
                    cost_cents = tu.get("estimated_cost_usd_cents", 0)
                stage_lat = {s["stage"]: s["latency_ms"] for s in tracer.stages}
                q_scores = critic_result.quality_scores if critic_result else {}
                ev_stats = {
                    "total_items": len(ledger),
                    "cited_count": len(cited_ids),
                    "tier_distribution": tier_dist,
                }
                _job = job_id or pipeline_id
                await telemetry_svc.record_telemetry(
                    user_id=user_id,
                    job_id=_job,
                    pipeline_name=self.name,
                    model_used=getattr(self._ai_client, "model", "") if self._ai_client else "",
                    research_depth=str(getattr(self.policy, "research_depth", "")),
                    iterations_used=iterations_used,
                    total_latency_ms=total_latency,
                    stage_latencies=stage_lat,
                    token_usage=token_data,
                    quality_scores=q_scores,
                    evidence_stats=ev_stats,
                    cost_usd_cents=cost_cents,
                    cascade_failovers=cascade_count,
                    pipeline_config={
                        "skip_research": self.policy.skip_research,
                        "skip_critique": self.policy.skip_critique,
                        "skip_fact_check": self.policy.skip_fact_check,
                        "confidence_threshold": self.policy.confidence_threshold,
                        "max_iterations": self.policy.max_iterations or self.max_iterations,
                    },
                )
        except Exception as tel_err:
            logger.warning("pipeline_telemetry_failed", error=str(tel_err)[:200])

        # ── Smart Cost Optimizer — feed quality data to model router ──
        try:
            if critic_result and critic_result.quality_scores:
                from ai_engine.model_router import record_quality_observation
                qs = critic_result.quality_scores
                avg_q = sum(
                    qs.get(d, 0)
                    for d in ("impact", "clarity", "tone_match", "completeness")
                ) / 4.0
                # Record for all task types this pipeline used
                model_used = getattr(self._ai_client, "model", "gemini-2.5-pro") if self._ai_client else "gemini-2.5-pro"
                for task_type in ("drafting", "critique", "research", "reasoning"):
                    record_quality_observation(task_type, model_used, avg_q)
        except Exception:
            pass  # best-effort, never crash pipeline

        # ── Outcome-Aware Memory — write pipeline success patterns ────
        try:
            if self.memory and user_id and user_id != "unknown":
                model_name = getattr(self._ai_client, "model", "") if self._ai_client else ""
                avg_quality = 0.0
                if critic_result and critic_result.quality_scores:
                    qs = critic_result.quality_scores
                    avg_quality = sum(
                        qs.get(d, 0)
                        for d in ("impact", "clarity", "tone_match", "completeness")
                    ) / 4.0
                if avg_quality >= 75:
                    await self.memory.astore(
                        user_id, "pipeline_strategy",
                        f"winning_config:{self.name}",
                        {
                            "pipeline": self.name,
                            "model": model_name,
                            "iterations": iterations_used,
                            "quality": round(avg_quality, 1),
                            "evidence_count": len(ledger),
                            "pattern": "high_quality_run",
                        },
                    )
        except Exception:
            pass  # best-effort

        return PipelineResult(
            content=final_content,
            quality_scores=critic_result.quality_scores if critic_result else {},
            optimization_report=optimizer_result.content if optimizer_result else {},
            fact_check_report=fact_check_result.content if fact_check_result else {},
            iterations_used=iterations_used,
            total_latency_ms=total_latency,
            trace_id=pipeline_id,
            evidence_ledger=ledger.to_dict(),
            citations=[c for c in citations],
            workflow_state={
                "stages": {
                    name: {"status": cp.status.value, "latency_ms": cp.latency_ms}
                    for name, cp in wf_state.stages.items()
                }
            } if wf_state else None,
            validation_report=validation_report,
            final_analysis_report=final_analysis_result.content if final_analysis_result else None,
            escalation=getattr(self, "_escalation", None),
            iteration_deltas=iteration_deltas if iteration_deltas else None,
            citation_coverage=_compute_citation_coverage(citations),
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

    async def _request_approval(
        self, stage: str, stage_result: Any, context: dict,
    ) -> bool:
        """Request human approval after a stage if policy requires it.

        Returns True if approved (or no callback registered), False to abort.
        """
        if stage not in self.policy.require_human_approval_after:
            return True
        if not self.on_approval_request:
            # No callback registered — auto-approve but log it
            logger.info("human_approval_auto_approved", stage=stage, reason="no callback")
            return True

        try:
            result_summary = {}
            if hasattr(stage_result, "content"):
                result_summary["content_keys"] = list(stage_result.content.keys()) if isinstance(stage_result.content, dict) else []
            if hasattr(stage_result, "quality_scores"):
                result_summary["quality_scores"] = stage_result.quality_scores
            if hasattr(stage_result, "flags"):
                result_summary["flags"] = stage_result.flags

            await self._emit(stage, "awaiting_approval", message="Waiting for human review")

            approved = await self.on_approval_request({
                "pipeline_name": self.name,
                "stage": stage,
                "result_summary": result_summary,
                "context": {k: v for k, v in context.items() if isinstance(v, (str, int, float, bool))},
            })

            if not approved:
                logger.warning("human_approval_rejected", stage=stage, pipeline=self.name)
                await self._emit(stage, "rejected", message="Human review rejected continuation")
            return bool(approved)
        except Exception as e:
            logger.warning("human_approval_callback_failed", stage=stage, error=str(e))
            return True  # fail-open: proceed if callback errors

    async def _reflect_on_evaluation(
        self,
        critic_result: Optional[AgentResult],
        optimizer_result: Optional[AgentResult],
        fact_check_result: Optional[AgentResult],
        draft_content: dict,
        pipeline_name: str,
    ) -> dict:
        """LLM-driven reflection: decide what the pipeline should do next.

        Returns a dict with keys:
          - decision: one of "accept", "revise", "revise_targeted",
                      "re_research", "re_research_targeted", "escalate"
          - reasoning: str
          - revision_scope: optional dict with {dimensions, issues} for targeted revise
          - research_targets: optional dict with {categories, claims} for targeted re-research
        Falls back to {"decision": "revise"} if LLM is unavailable or errors.
        """
        _VALID_DECISIONS = (
            "accept", "revise", "revise_targeted",
            "re_research", "re_research_targeted", "escalate",
        )

        if not self._ai_client:
            return {"decision": "revise", "reasoning": "no_ai_client"}

        # Build evaluation summary for the LLM
        quality_scores = critic_result.quality_scores if critic_result else {}
        critic_feedback = critic_result.feedback if critic_result and critic_result.feedback else {}
        fc_summary = fact_check_result.content.get("summary", {}) if fact_check_result else {}
        opt_suggestions = optimizer_result.content.get("suggestions", []) if optimizer_result else []
        needs_revision = critic_result.needs_revision if critic_result else False

        # Rich context: ranked issues from critic, claim categories from fact-checker,
        # draft confidence from drafter metadata
        ranked_issues = []
        if critic_result and critic_result.content:
            ranked_issues = critic_result.content.get("ranked_issues", [])
        claim_categories = []
        if fact_check_result and fact_check_result.content:
            claim_categories = fact_check_result.content.get("claim_categories", [])
        draft_confidence = 0.5
        if draft_content and isinstance(draft_content, dict):
            draft_confidence = draft_content.get("_metadata", {}).get("draft_confidence", 0.5)

        reflection_prompt = (
            "You are an AI pipeline orchestrator. Based on the evaluation results below, "
            "decide the BEST next action for quality.\n\n"
            f"## Pipeline: {pipeline_name}\n\n"
            f"## Quality Scores\n{json.dumps(quality_scores, indent=2)}\n\n"
            f"## Critic Feedback\n{json.dumps({k: str(v)[:200] for k, v in critic_feedback.items()}, indent=2) if isinstance(critic_feedback, dict) and critic_feedback else json.dumps(critic_feedback, indent=2, default=str) if critic_feedback else 'None'}\n\n"
            f"## Ranked Issues (by severity)\n{json.dumps(ranked_issues[:5], indent=2, default=str) if ranked_issues else 'None'}\n\n"
            f"## Fact-Check Summary\n{json.dumps(fc_summary, indent=2)}\n\n"
            f"## Fabrication Categories\n{json.dumps(claim_categories) if claim_categories else 'None'}\n\n"
            f"## Optimizer Suggestions Count: {len(opt_suggestions)}\n\n"
            f"## Critic Says Revision Needed: {needs_revision}\n"
            f"## Draft Confidence: {draft_confidence:.2f}\n\n"
            "Choose ONE action and explain your reasoning:\n"
            '- "accept" — Quality is high enough, skip revision and go to validation\n'
            '- "revise" — Broad quality issues, run full revision loop\n'
            '- "revise_targeted" — Only 1-2 dimensions need fixing; provide which dimensions and issues to address\n'
            '- "re_research" — Evidence is fundamentally weak, redo ALL research\n'
            '- "re_research_targeted" — Only specific claim categories have fabrication issues; provide which categories\n'
            '- "escalate" — Quality is unsalvageable within iteration budget; flag for human review\n\n'
            "Respond with JSON:\n"
            "{\n"
            '  "decision": "<one of the 6 actions>",\n'
            '  "reasoning": "...",\n'
            '  "target_dimensions": ["dimension1", ...],  // only for revise_targeted\n'
            '  "target_issues": ["issue1", ...],           // only for revise_targeted\n'
            '  "target_categories": ["category1", ...]     // only for re_research_targeted\n'
            "}"
        )

        try:
            result = await self._ai_client.complete_json(
                prompt=reflection_prompt,
                system="You are a pipeline quality orchestrator. Be decisive and concise.",
                max_tokens=300,
                temperature=0.1,
                task_type="structured_output",
            )
            decision = result.get("decision", "revise")
            reasoning = result.get("reasoning", "")

            if decision not in _VALID_DECISIONS:
                decision = "revise"

            reflection_result = {"decision": decision, "reasoning": reasoning}

            # Attach scope data for targeted decisions
            if decision == "revise_targeted":
                reflection_result["revision_scope"] = {
                    "dimensions": result.get("target_dimensions", []),
                    "issues": result.get("target_issues", []),
                }
            elif decision == "re_research_targeted":
                reflection_result["research_targets"] = {
                    "categories": result.get("target_categories", claim_categories),
                    "claims": (
                        fact_check_result.content.get("claims", [])
                        if fact_check_result else []
                    ),
                }

            logger.info(
                "llm_reflection_decision",
                decision=decision,
                reasoning=reasoning[:200],
                pipeline=pipeline_name,
                quality_scores=quality_scores,
            )
            await self._emit("orchestrator", "reflection", message=f"Decision: {decision} — {reasoning[:100]}")
            return reflection_result
        except Exception as e:
            logger.warning("llm_reflection_failed", error=str(e), pipeline=pipeline_name)
            return {"decision": "revise", "reasoning": f"reflection_error: {e}"}
