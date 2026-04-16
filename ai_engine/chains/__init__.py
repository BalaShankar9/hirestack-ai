"""
HireStack AI - Prompt Chains
Modular AI processing chains for different tasks
"""
from ai_engine.chains.role_profiler import RoleProfilerChain
from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
from ai_engine.chains.gap_analyzer import GapAnalyzerChain
from ai_engine.chains.career_consultant import CareerConsultantChain
from ai_engine.chains.document_generator import DocumentGeneratorChain
from ai_engine.chains.validator import ValidatorChain
from ai_engine.chains.ats_scanner import ATSScannerChain
from ai_engine.chains.interview_simulator import InterviewSimulatorChain
from ai_engine.chains.doc_variant import DocumentVariantChain
from ai_engine.chains.salary_coach import SalaryCoachChain
from ai_engine.chains.learning_challenge import LearningChallengeChain
from ai_engine.chains.universal_doc_generator import UniversalDocGeneratorChain
from ai_engine.chains.linkedin_advisor import LinkedInAdvisorChain
from ai_engine.chains.market_intelligence import MarketIntelligenceChain
from ai_engine.chains.daily_briefing import DailyBriefingChain
from ai_engine.chains.application_coach import ApplicationCoachChain
from ai_engine.chains.document_discovery import DocumentDiscoveryChain
from ai_engine.chains.adaptive_document import AdaptiveDocumentChain
from ai_engine.chains.company_intel import CompanyIntelChain
from ai_engine.chains.document_pack_planner import DocumentPackPlanner, DocumentPackPlan

__all__ = [
    "RoleProfilerChain",
    "BenchmarkBuilderChain",
    "GapAnalyzerChain",
    "CareerConsultantChain",
    "DocumentGeneratorChain",
    "ValidatorChain",
    "ATSScannerChain",
    "InterviewSimulatorChain",
    "DocumentVariantChain",
    "SalaryCoachChain",
    "LearningChallengeChain",
    "UniversalDocGeneratorChain",
    "LinkedInAdvisorChain",
    "MarketIntelligenceChain",
    "DailyBriefingChain",
    "ApplicationCoachChain",
    "DocumentDiscoveryChain",
    "AdaptiveDocumentChain",
    "CompanyIntelChain",
    "DocumentPackPlanner",
    "DocumentPackPlan",
]
