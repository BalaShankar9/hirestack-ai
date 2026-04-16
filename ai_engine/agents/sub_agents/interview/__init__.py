"""
Interview Simulator sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel, deterministic — no LLM):
    • QuestionFrameworkBuilder — category/difficulty distribution matrix
    • RoleContextExtractor     — keyword/skill extraction from JD + profile
    • CandidateGapProber       — identifies weak spots to probe
    • PrepTipGenerator         — rule-based preparation tips

  Phase 2 (single LLM):
    • QuestionSynthesizer      — generates actual interview questions

Re-exports all agents + coordinator for convenience.
"""
from ai_engine.agents.sub_agents.interview.question_framework_builder import QuestionFrameworkBuilder
from ai_engine.agents.sub_agents.interview.role_context_extractor import RoleContextExtractor
from ai_engine.agents.sub_agents.interview.candidate_gap_prober import CandidateGapProber
from ai_engine.agents.sub_agents.interview.prep_tip_generator import PrepTipGenerator
from ai_engine.agents.sub_agents.interview.question_synthesizer import QuestionSynthesizer
from ai_engine.agents.sub_agents.interview.coordinator import InterviewCoordinator

__all__ = [
    "QuestionFrameworkBuilder",
    "RoleContextExtractor",
    "CandidateGapProber",
    "PrepTipGenerator",
    "QuestionSynthesizer",
    "InterviewCoordinator",
]
