"""Curated production registry for the main sub-agent hot path."""
from __future__ import annotations

from typing import Any, Optional

from ai_engine.client import AIClient

from .base import SubAgent
from .company_intel_agent import CompanyIntelSubAgent
from .history_agent import HistorySubAgent
from .jd_analyst import JDAnalystSubAgent
from .market_intel_agent import MarketIntelSubAgent
from .profile_match_agent import ProfileMatchSubAgent

PIPELINE_RESEARCH_SUB_AGENT_NAMES = (
    "jd_analyst",
    "company_intel",
    "profile_match",
    "market_intel",
    "history",
)

BENCHMARK_PIPELINE_RESEARCH_SUB_AGENT_NAMES = (
    "jd_analyst",
    "profile_match",
    "history",
)


def build_default_research_sub_agents(
    *,
    ai_client: Optional[AIClient] = None,
    db: Any = None,
    user_id: str = "",
) -> list[SubAgent]:
    """Build the default research swarm used by the production pipeline."""
    sub_agents: list[SubAgent] = [
        JDAnalystSubAgent(ai_client=ai_client),
        CompanyIntelSubAgent(ai_client=ai_client),
        ProfileMatchSubAgent(ai_client=ai_client),
        MarketIntelSubAgent(ai_client=ai_client),
        HistorySubAgent(db=db, user_id=user_id, ai_client=ai_client),
    ]
    return sub_agents


def build_benchmark_research_sub_agents(
    *,
    ai_client: Optional[AIClient] = None,
    db: Any = None,
    user_id: str = "",
) -> list[SubAgent]:
    """Build the narrower research swarm used by benchmark profiling."""
    sub_agents: list[SubAgent] = [
        JDAnalystSubAgent(ai_client=ai_client),
        ProfileMatchSubAgent(ai_client=ai_client),
    ]
    if db is not None and user_id:
        sub_agents.append(
            HistorySubAgent(db=db, user_id=user_id, ai_client=ai_client),
        )
    return sub_agents


__all__ = [
    "PIPELINE_RESEARCH_SUB_AGENT_NAMES",
    "BENCHMARK_PIPELINE_RESEARCH_SUB_AGENT_NAMES",
    "build_default_research_sub_agents",
    "build_benchmark_research_sub_agents",
]