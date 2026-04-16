"""
Pipeline factory — creates pre-configured pipelines for each feature.

Each pipeline maps to a row in the per-feature configuration table (spec Section 2.9).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from ai_engine.agents.orchestrator import AgentPipeline
from ai_engine.agents.researcher import ResearcherAgent, ResearchDepth
from ai_engine.agents.drafter import DrafterAgent
from ai_engine.agents.critic import CriticAgent
from ai_engine.agents.optimizer import OptimizerAgent
from ai_engine.agents.fact_checker import FactCheckerAgent
from ai_engine.agents.schema_validator import ValidatorAgent
from ai_engine.agents.lock import PipelineLockManager
from ai_engine.agents.memory import AgentMemory
from ai_engine.agents.sub_agents import (
    JDAnalystSubAgent,
    CompanyIntelSubAgent,
    ProfileMatchSubAgent,
    MarketIntelSubAgent,
    HistorySubAgent,
)
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
    on_stage_update: Optional[Callable] = None,
    ai_client: Optional[AIClient] = None,
    db: Any = None,
    max_iterations: int = 2,
    tables: Optional[dict] = None,
    job_id: Optional[str] = None,
    research_depth: ResearchDepth = ResearchDepth.THOROUGH,
    user_id: str = "",
    custom_sub_agents: Optional[list[Any]] = None,
) -> AgentPipeline:
    """Create a configured AgentPipeline for a specific feature.

    Args:
        tables: Table name map (e.g. from TABLES). When provided with db,
                enables durable event-sourced execution via WorkflowEventStore.
        job_id: Not stored here — callers pass job_id via the context dict
                at execute() time. Kept for documentation clarity.
        research_depth: Controls how deep and wide the researcher gathers evidence.
    """
    client = ai_client or get_ai_client()

    researcher = None
    if use_researcher:
        researcher = ResearcherAgent(
            ai_client=client, db=db, research_depth=research_depth,
        )
        # Attach sub-agents for THOROUGH and EXHAUSTIVE depth.
        # Atlas pipelines can provide a tighter, domain-specific list.
        if custom_sub_agents is not None:
            researcher._sub_agents = custom_sub_agents
        elif research_depth in (ResearchDepth.THOROUGH, ResearchDepth.EXHAUSTIVE):
            sub_agents = [
                JDAnalystSubAgent(ai_client=client),
                CompanyIntelSubAgent(ai_client=client),
                ProfileMatchSubAgent(ai_client=client),
                MarketIntelSubAgent(ai_client=client),
                HistorySubAgent(db=db, user_id=user_id, ai_client=client),
            ]
            researcher._sub_agents = sub_agents

    pipeline = AgentPipeline(
        name=name,
        researcher=researcher,
        drafter=DrafterAgent(chain=chain, method_name=method_name, ai_client=client),
        critic=CriticAgent(ai_client=client) if use_critic else None,
        optimizer=OptimizerAgent(ai_client=client) if use_optimizer else None,
        fact_checker=FactCheckerAgent(ai_client=client) if use_fact_checker else None,
        validator=ValidatorAgent(ai_client=client),
        lock_manager=_lock_manager,
        on_stage_update=on_stage_update,
        ai_client=client,
        db=db,
        max_iterations=max_iterations,
        tables=tables,
    )

    # Attach memory if DB is available
    if db is not None:
        try:
            pipeline.memory = AgentMemory(db)
        except Exception:
            pass  # Memory is optional — pipeline works without it

    return pipeline


def resume_parse_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import RoleProfilerChain
    chain = RoleProfilerChain(client)
    return create_pipeline(
        "resume_parse", chain, "parse_resume",
        # Resume parsing is deterministic-first; avoid unrelated researcher fan-out.
        use_researcher=False,
        use_optimizer=False,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def benchmark_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import BenchmarkBuilderChain
    chain = BenchmarkBuilderChain(client)
    atlas_sub_agents: list[Any] = [
        # Atlas benchmarking benefits from JD + optional history context.
        JDAnalystSubAgent(ai_client=client),
        ProfileMatchSubAgent(ai_client=client),
    ]
    if db is not None and user_id:
        atlas_sub_agents.append(HistorySubAgent(db=db, user_id=user_id, ai_client=client))
    return create_pipeline(
        "benchmark", chain, "create_ideal_profile",
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
        custom_sub_agents=atlas_sub_agents,
    )


def gap_analysis_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import GapAnalyzerChain
    chain = GapAnalyzerChain(client)
    return create_pipeline(
        "gap_analysis", chain, "analyze_gaps",
        use_researcher=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def cv_generation_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "cv_generation", chain, "generate_tailored_cv",
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def cover_letter_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "cover_letter", chain, "generate_tailored_cover_letter",
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def personal_statement_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "personal_statement", chain, "generate_tailored_personal_statement",
        use_researcher=False, use_optimizer=False, use_fact_checker=False,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def portfolio_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentGeneratorChain
    chain = DocumentGeneratorChain(client)
    return create_pipeline(
        "portfolio", chain, "generate_tailored_portfolio",
        use_researcher=False, use_critic=False, use_fact_checker=False,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def ats_scanner_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import ATSScannerChain
    chain = ATSScannerChain(client)
    return create_pipeline(
        "ats_scanner", chain, "scan_document",
        use_critic=False, use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def interview_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import InterviewSimulatorChain
    chain = InterviewSimulatorChain(client)
    return create_pipeline(
        "interview", chain, "generate_questions",
        use_optimizer=False, use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def career_roadmap_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import CareerConsultantChain
    chain = CareerConsultantChain(client)
    return create_pipeline(
        "career_roadmap", chain, "generate_roadmap",
        use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


# Tone constants for A/B Lab variants
CONSERVATIVE_TONE = "Use formal language, traditional structure, quantified achievements, no personality flair"
BALANCED_TONE = "Professional but approachable, mix of quantified and narrative, moderate personality"
CREATIVE_TONE = "Bold opening, storytelling elements, unique framing, personality-forward"


def ab_lab_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentVariantChain
    chain = DocumentVariantChain(client)
    return create_pipeline(
        "ab_lab", chain, "generate_variant",
        use_researcher=False, use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def salary_coach_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import SalaryCoachChain
    chain = SalaryCoachChain(client)
    return create_pipeline(
        "salary_coach", chain, "analyze_salary",
        use_critic=False, use_optimizer=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


def learning_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import LearningChallengeChain
    chain = LearningChallengeChain(client)
    return create_pipeline(
        "learning", chain, "generate_challenge",
        use_researcher=False, use_critic=False, use_optimizer=False,
        use_fact_checker=False,
        ai_client=client, on_stage_update=on_stage_update,
        db=db, tables=tables, user_id=user_id,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Universal pipeline builder — name → configured pipeline
# ═══════════════════════════════════════════════════════════════════════

_PIPELINE_FACTORIES: dict[str, Callable[..., AgentPipeline]] = {
    "resume_parse": resume_parse_pipeline,
    "benchmark": benchmark_pipeline,
    "gap_analysis": gap_analysis_pipeline,
    "cv_generation": cv_generation_pipeline,
    "cover_letter": cover_letter_pipeline,
    "personal_statement": personal_statement_pipeline,
    "portfolio": portfolio_pipeline,
    "ats_scanner": ats_scanner_pipeline,
    "interview": interview_pipeline,
    "career_roadmap": career_roadmap_pipeline,
    "ab_lab": ab_lab_pipeline,
    "salary_coach": salary_coach_pipeline,
    "learning": learning_pipeline,
}


def build_pipeline(
    name: str,
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
    db: Any = None,
    tables: Optional[dict] = None,
    user_id: str = "",
) -> AgentPipeline:
    """Build a pre-configured pipeline by name.

    Raises KeyError if the pipeline name is not recognised.
    """
    factory = _PIPELINE_FACTORIES.get(name)
    if not factory:
        raise KeyError(
            f"Unknown pipeline '{name}'. Available: {sorted(_PIPELINE_FACTORIES)}"
        )
    return factory(ai_client=ai_client, on_stage_update=on_stage_update, db=db, tables=tables, user_id=user_id)
