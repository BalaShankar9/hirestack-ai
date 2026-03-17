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
    on_stage_update: Optional[Callable] = None,
    ai_client: Optional[AIClient] = None,
    db: Any = None,
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
        lock_manager=_lock_manager,
        on_stage_update=on_stage_update,
        db=db,
    )


def resume_parse_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import RoleProfilerChain
    chain = RoleProfilerChain(client)
    return create_pipeline(
        "resume_parse", chain, "parse_resume",
        use_optimizer=False,
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

        ai_client=client, on_stage_update=on_stage_update,
    )


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


# Tone constants for A/B Lab variants
CONSERVATIVE_TONE = "Use formal language, traditional structure, quantified achievements, no personality flair"
BALANCED_TONE = "Professional but approachable, mix of quantified and narrative, moderate personality"
CREATIVE_TONE = "Bold opening, storytelling elements, unique framing, personality-forward"


def ab_lab_pipeline(
    ai_client: Optional[AIClient] = None,
    on_stage_update: Optional[Callable] = None,
) -> AgentPipeline:
    client = ai_client or get_ai_client()
    from ai_engine.chains import DocumentVariantChain
    chain = DocumentVariantChain(client)
    return create_pipeline(
        "ab_lab", chain, "generate_variant",
        use_researcher=False, use_fact_checker=False, max_iterations=1,
        ai_client=client, on_stage_update=on_stage_update,
    )


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
        use_fact_checker=False,
        ai_client=client, on_stage_update=on_stage_update,
    )
