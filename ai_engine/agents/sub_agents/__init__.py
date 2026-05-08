"""
Sub-agent framework for HireStack AI.

The package root is a compatibility surface for specialist classes and
coordinators. Production pipeline composition lives in
``ai_engine.agents.sub_agents.live_registry`` so the hot path is explicit
instead of treating every exported sub-agent as equally active.
"""
from __future__ import annotations

from importlib import import_module

from .base import SubAgent, SubAgentResult, SubAgentCoordinator

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # Researcher
    "JDAnalystSubAgent": (".jd_analyst", "JDAnalystSubAgent"),
    "CompanyIntelSubAgent": (".company_intel_agent", "CompanyIntelSubAgent"),
    "ProfileMatchSubAgent": (".profile_match_agent", "ProfileMatchSubAgent"),
    "MarketIntelSubAgent": (".market_intel_agent", "MarketIntelSubAgent"),
    "HistorySubAgent": (".history_agent", "HistorySubAgent"),
    # Drafter
    "SectionDrafterSubAgent": (".section_drafter", "SectionDrafterSubAgent"),
    "ToneCalibratorSubAgent": (".tone_calibrator", "ToneCalibratorSubAgent"),
    "KeywordStrategistSubAgent": (".keyword_strategist", "KeywordStrategistSubAgent"),
    # Critic
    "ImpactCriticSubAgent": (".critic_specialists", "ImpactCriticSubAgent"),
    "ClarityCriticSubAgent": (".critic_specialists", "ClarityCriticSubAgent"),
    "ToneMatchCriticSubAgent": (".critic_specialists", "ToneMatchCriticSubAgent"),
    "CompletenessCriticSubAgent": (".critic_specialists", "CompletenessCriticSubAgent"),
    # Fact checker
    "ClaimExtractorSubAgent": (".fact_checker_specialists", "ClaimExtractorSubAgent"),
    "EvidenceMatcherSubAgent": (".fact_checker_specialists", "EvidenceMatcherSubAgent"),
    "CrossRefCheckerSubAgent": (".fact_checker_specialists", "CrossRefCheckerSubAgent"),
    # Optimizer
    "ATSOptimizerSubAgent": (".optimizer_specialists", "ATSOptimizerSubAgent"),
    "ReadabilityOptimizerSubAgent": (".optimizer_specialists", "ReadabilityOptimizerSubAgent"),
    # Explicit hot-path helpers
    "PIPELINE_RESEARCH_SUB_AGENT_NAMES": (
        ".live_registry",
        "PIPELINE_RESEARCH_SUB_AGENT_NAMES",
    ),
    "BENCHMARK_PIPELINE_RESEARCH_SUB_AGENT_NAMES": (
        ".live_registry",
        "BENCHMARK_PIPELINE_RESEARCH_SUB_AGENT_NAMES",
    ),
    "build_default_research_sub_agents": (
        ".live_registry",
        "build_default_research_sub_agents",
    ),
    "build_benchmark_research_sub_agents": (
        ".live_registry",
        "build_benchmark_research_sub_agents",
    ),
    # Intel swarm (v2)
    "IntelCoordinator": (".intel", "IntelCoordinator"),
    "WebsiteIntelAgent": (".intel", "WebsiteIntelAgent"),
    "GitHubIntelAgent": (".intel", "GitHubIntelAgent"),
    "CareersIntelAgent": (".intel", "CareersIntelAgent"),
    "JDIntelAgent": (".intel", "JDIntelAgent"),
    "CompanyProfileAgent": (".intel", "CompanyProfileAgent"),
    "MarketPositionAgent": (".intel", "MarketPositionAgent"),
    "ApplicationStrategyAgent": (".intel", "ApplicationStrategyAgent"),
    # Gap analysis swarm (v2)
    "GapAnalysisCoordinator": (".gap_analysis", "GapAnalysisCoordinator"),
    "TechnicalSkillAnalyst": (".gap_analysis", "TechnicalSkillAnalyst"),
    "ExperienceAnalyst": (".gap_analysis", "ExperienceAnalyst"),
    "EducationCertAnalyst": (".gap_analysis", "EducationCertAnalyst"),
    "SoftSkillCultureAnalyst": (".gap_analysis", "SoftSkillCultureAnalyst"),
    "StrengthMapper": (".gap_analysis", "StrengthMapper"),
    "GapSynthesizer": (".gap_analysis", "GapSynthesizer"),
    # Career consultant swarm (v2)
    "CareerCoordinator": (".career", "CareerCoordinator"),
    "SkillPrioritizer": (".career", "SkillPrioritizer"),
    "MilestoneScheduler": (".career", "MilestoneScheduler"),
    "QuickWinExtractor": (".career", "QuickWinExtractor"),
    "ProjectIdeaGenerator": (".career", "ProjectIdeaGenerator"),
    "RoadmapSynthesizer": (".career", "RoadmapSynthesizer"),
    # Interview simulator swarm (v2)
    "InterviewCoordinator": (".interview", "InterviewCoordinator"),
    "QuestionFrameworkBuilder": (".interview", "QuestionFrameworkBuilder"),
    "RoleContextExtractor": (".interview", "RoleContextExtractor"),
    "CandidateGapProber": (".interview", "CandidateGapProber"),
    "PrepTipGenerator": (".interview", "PrepTipGenerator"),
    "QuestionSynthesizer": (".interview", "QuestionSynthesizer"),
    # Market intelligence swarm (v2)
    "MarketIntelCoordinator": (".market_intel", "MarketIntelCoordinator"),
    "LocationNormalizer": (".market_intel", "LocationNormalizer"),
    "SkillDemandMapper": (".market_intel", "SkillDemandMapper"),
    "ExperienceLevelClassifier": (".market_intel", "ExperienceLevelClassifier"),
    "TrendMapper": (".market_intel", "TrendMapper"),
    "MarketSynthesizer": (".market_intel", "MarketSynthesizer"),
    # Salary coach swarm (v2)
    "SalaryCoordinator": (".salary", "SalaryCoordinator"),
    "MarketRangeEstimator": (".salary", "MarketRangeEstimator"),
    "ValueDriverAnalyzer": (".salary", "ValueDriverAnalyzer"),
    "OfferAnalyzer": (".salary", "OfferAnalyzer"),
    "NegotiationFrameworkBuilder": (".salary", "NegotiationFrameworkBuilder"),
    "SalarySynthesizer": (".salary", "SalarySynthesizer"),
    # LinkedIn advisor swarm (v2)
    "LinkedInCoordinator": (".linkedin", "LinkedInCoordinator"),
    "ProfileScorer": (".linkedin", "ProfileScorer"),
    "SkillGapFinder": (".linkedin", "SkillGapFinder"),
    "ExperienceCritic": (".linkedin", "ExperienceCritic"),
    "KeywordExtractor": (".linkedin", "KeywordExtractor"),
    "LinkedInSynthesizer": (".linkedin", "LinkedInSynthesizer"),
}

__all__ = [
    "SubAgent",
    "SubAgentResult",
    "SubAgentCoordinator",
    *_LAZY_EXPORTS.keys(),
]


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
