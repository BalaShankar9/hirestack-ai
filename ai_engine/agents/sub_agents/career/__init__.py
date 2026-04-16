"""
Career Consultant sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel, deterministic — no LLM):
    • SkillPrioritizer      — ranks gaps, builds learning order, time estimates
    • MilestoneScheduler    — 12-week skeleton with phases
    • QuickWinExtractor     — immediate actionable items
    • ProjectIdeaGenerator  — project templates mapped to skill gaps

  Phase 2 (single LLM):
    • RoadmapSynthesizer    — polished narrative roadmap with resources & motivation

Re-exports all agents + coordinator for convenience.
"""
from ai_engine.agents.sub_agents.career.skill_prioritizer import SkillPrioritizer
from ai_engine.agents.sub_agents.career.milestone_scheduler import MilestoneScheduler
from ai_engine.agents.sub_agents.career.quick_win_extractor import QuickWinExtractor
from ai_engine.agents.sub_agents.career.project_idea_generator import ProjectIdeaGenerator
from ai_engine.agents.sub_agents.career.roadmap_synthesizer import RoadmapSynthesizer
from ai_engine.agents.sub_agents.career.coordinator import CareerCoordinator

__all__ = [
    "SkillPrioritizer",
    "MilestoneScheduler",
    "QuickWinExtractor",
    "ProjectIdeaGenerator",
    "RoadmapSynthesizer",
    "CareerCoordinator",
]
