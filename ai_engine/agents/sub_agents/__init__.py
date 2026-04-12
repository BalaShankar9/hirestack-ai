"""
Sub-agent framework for HireStack AI.

Provides lightweight specialist workers that run in parallel under a
coordinator agent. Each SubAgent focuses on a single research or analysis
dimension and returns a SubAgentResult.
"""
from __future__ import annotations

from .base import SubAgent, SubAgentResult, SubAgentCoordinator
# Researcher sub-agents
from .jd_analyst import JDAnalystSubAgent
from .company_intel_agent import CompanyIntelSubAgent
from .profile_match_agent import ProfileMatchSubAgent
from .market_intel_agent import MarketIntelSubAgent
from .history_agent import HistorySubAgent
# Drafter sub-agents
from .section_drafter import SectionDrafterSubAgent
from .tone_calibrator import ToneCalibratorSubAgent
from .keyword_strategist import KeywordStrategistSubAgent
# Critic sub-agents
from .critic_specialists import (
    ImpactCriticSubAgent,
    ClarityCriticSubAgent,
    ToneMatchCriticSubAgent,
    CompletenessCriticSubAgent,
)
# FactChecker sub-agents
from .fact_checker_specialists import (
    ClaimExtractorSubAgent,
    EvidenceMatcherSubAgent,
    CrossRefCheckerSubAgent,
)
# Optimizer sub-agents
from .optimizer_specialists import (
    ATSOptimizerSubAgent,
    ReadabilityOptimizerSubAgent,
)

__all__ = [
    "SubAgent",
    "SubAgentResult",
    "SubAgentCoordinator",
    # Researcher
    "JDAnalystSubAgent",
    "CompanyIntelSubAgent",
    "ProfileMatchSubAgent",
    "MarketIntelSubAgent",
    "HistorySubAgent",
    # Drafter
    "SectionDrafterSubAgent",
    "ToneCalibratorSubAgent",
    "KeywordStrategistSubAgent",
    # Critic
    "ImpactCriticSubAgent",
    "ClarityCriticSubAgent",
    "ToneMatchCriticSubAgent",
    "CompletenessCriticSubAgent",
    # FactChecker
    "ClaimExtractorSubAgent",
    "EvidenceMatcherSubAgent",
    "CrossRefCheckerSubAgent",
    # Optimizer
    "ATSOptimizerSubAgent",
    "ReadabilityOptimizerSubAgent",
]
