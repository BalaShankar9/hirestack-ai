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
]
