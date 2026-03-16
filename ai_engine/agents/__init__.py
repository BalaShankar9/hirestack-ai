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
from ai_engine.agents.orchestrator import AgentPipeline, PipelineResult
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
    "PipelineResult",
    "create_pipeline",
    "resume_parse_pipeline",
    "benchmark_pipeline",
    "gap_analysis_pipeline",
    "cv_generation_pipeline",
    "cover_letter_pipeline",
    "personal_statement_pipeline",
    "portfolio_pipeline",
]
