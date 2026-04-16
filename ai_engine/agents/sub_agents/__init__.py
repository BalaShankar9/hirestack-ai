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
# Intel sub-agent swarm (v2)
from .intel import (
    IntelCoordinator,
    WebsiteIntelAgent,
    GitHubIntelAgent,
    CareersIntelAgent,
    JDIntelAgent,
    CompanyProfileAgent,
    MarketPositionAgent,
    ApplicationStrategyAgent,
)
# Gap Analysis sub-agent swarm (v2)
from .gap_analysis import (
    GapAnalysisCoordinator,
    TechnicalSkillAnalyst,
    ExperienceAnalyst,
    EducationCertAnalyst,
    SoftSkillCultureAnalyst,
    StrengthMapper,
    GapSynthesizer,
)
# Career Consultant sub-agent swarm (v2)
from .career import (
    CareerCoordinator,
    SkillPrioritizer,
    MilestoneScheduler,
    QuickWinExtractor,
    ProjectIdeaGenerator,
    RoadmapSynthesizer,
)
# Interview Simulator sub-agent swarm (v2)
from .interview import (
    InterviewCoordinator,
    QuestionFrameworkBuilder,
    RoleContextExtractor,
    CandidateGapProber,
    PrepTipGenerator,
    QuestionSynthesizer,
)
# Market Intelligence sub-agent swarm (v2)
from .market_intel import (
    MarketIntelCoordinator,
    LocationNormalizer,
    SkillDemandMapper,
    ExperienceLevelClassifier,
    TrendMapper,
    MarketSynthesizer,
)
# Salary Coach sub-agent swarm (v2)
from .salary import (
    SalaryCoordinator,
    MarketRangeEstimator,
    ValueDriverAnalyzer,
    OfferAnalyzer,
    NegotiationFrameworkBuilder,
    SalarySynthesizer,
)
# LinkedIn Advisor sub-agent swarm (v2)
from .linkedin import (
    LinkedInCoordinator,
    ProfileScorer,
    SkillGapFinder,
    ExperienceCritic,
    KeywordExtractor,
    LinkedInSynthesizer,
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
    # Intel swarm (v2)
    "IntelCoordinator",
    "WebsiteIntelAgent",
    "GitHubIntelAgent",
    "CareersIntelAgent",
    "JDIntelAgent",
    "CompanyProfileAgent",
    "MarketPositionAgent",
    "ApplicationStrategyAgent",
    # Gap Analysis swarm (v2)
    "GapAnalysisCoordinator",
    "TechnicalSkillAnalyst",
    "ExperienceAnalyst",
    "EducationCertAnalyst",
    "SoftSkillCultureAnalyst",
    "StrengthMapper",
    "GapSynthesizer",
    # Career Consultant swarm (v2)
    "CareerCoordinator",
    "SkillPrioritizer",
    "MilestoneScheduler",
    "QuickWinExtractor",
    "ProjectIdeaGenerator",
    "RoadmapSynthesizer",
    # Interview Simulator swarm (v2)
    "InterviewCoordinator",
    "QuestionFrameworkBuilder",
    "RoleContextExtractor",
    "CandidateGapProber",
    "PrepTipGenerator",
    "QuestionSynthesizer",
    # Market Intelligence swarm (v2)
    "MarketIntelCoordinator",
    "LocationNormalizer",
    "SkillDemandMapper",
    "ExperienceLevelClassifier",
    "TrendMapper",
    "MarketSynthesizer",
    # Salary Coach swarm (v2)
    "SalaryCoordinator",
    "MarketRangeEstimator",
    "ValueDriverAnalyzer",
    "OfferAnalyzer",
    "NegotiationFrameworkBuilder",
    "SalarySynthesizer",
    # LinkedIn Advisor swarm (v2)
    "LinkedInCoordinator",
    "ProfileScorer",
    "SkillGapFinder",
    "ExperienceCritic",
    "KeywordExtractor",
    "LinkedInSynthesizer",
]
