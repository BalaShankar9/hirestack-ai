"""HireStack AI Agent Swarm Framework."""
from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.drafter import DrafterAgent
from ai_engine.agents.critic import CriticAgent
from ai_engine.agents.optimizer import OptimizerAgent
from ai_engine.agents.fact_checker import FactCheckerAgent
from ai_engine.agents.researcher import ResearcherAgent
from ai_engine.agents.schema_validator import ValidatorAgent
from ai_engine.agents.memory import AgentMemory
from ai_engine.agents.trace import AgentTracer
from ai_engine.agents.lock import PipelineLockManager
from ai_engine.agents.orchestrator import (
    AgentPipeline,
    PipelinePolicy,
    PipelineResult,
    DEFAULT_POLICIES,
    POLICY_FULL,
    POLICY_LIGHT,
    POLICY_STRICT,
)
from ai_engine.agents.tools import (
    AgentTool,
    ToolRegistry,
    build_researcher_tools,
    build_fact_checker_tools,
    build_optimizer_tools,
)
from ai_engine.agents.schemas import (
    RESEARCHER_SCHEMA,
    CRITIC_SCHEMA,
    OPTIMIZER_SCHEMA,
    FACT_CHECKER_SCHEMA,
    VALIDATOR_SCHEMA,
)
from ai_engine.agents.pipelines import (
    create_pipeline,
    resume_parse_pipeline,
    benchmark_pipeline,
    gap_analysis_pipeline,
    cv_generation_pipeline,
    cover_letter_pipeline,
    personal_statement_pipeline,
    portfolio_pipeline,
    ats_scanner_pipeline,
    interview_pipeline,
    career_roadmap_pipeline,
    ab_lab_pipeline,
    salary_coach_pipeline,
    learning_pipeline,
    CONSERVATIVE_TONE,
    BALANCED_TONE,
    CREATIVE_TONE,
)

__all__ = [
    "BaseAgent",
    "AgentResult",
    "DrafterAgent",
    "CriticAgent",
    "OptimizerAgent",
    "FactCheckerAgent",
    "ResearcherAgent",
    "ValidatorAgent",
    "AgentMemory",
    "AgentTracer",
    "PipelineLockManager",
    "AgentPipeline",
    "PipelinePolicy",
    "PipelineResult",
    "DEFAULT_POLICIES",
    "POLICY_FULL",
    "POLICY_LIGHT",
    "POLICY_STRICT",
    "AgentTool",
    "ToolRegistry",
    "build_researcher_tools",
    "build_fact_checker_tools",
    "build_optimizer_tools",
    "RESEARCHER_SCHEMA",
    "CRITIC_SCHEMA",
    "OPTIMIZER_SCHEMA",
    "FACT_CHECKER_SCHEMA",
    "VALIDATOR_SCHEMA",
    "create_pipeline",
    "resume_parse_pipeline",
    "benchmark_pipeline",
    "gap_analysis_pipeline",
    "cv_generation_pipeline",
    "cover_letter_pipeline",
    "personal_statement_pipeline",
    "portfolio_pipeline",
    "ats_scanner_pipeline",
    "interview_pipeline",
    "career_roadmap_pipeline",
    "ab_lab_pipeline",
    "salary_coach_pipeline",
    "learning_pipeline",
    "CONSERVATIVE_TONE",
    "BALANCED_TONE",
    "CREATIVE_TONE",
]
