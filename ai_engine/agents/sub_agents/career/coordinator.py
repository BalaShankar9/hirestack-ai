"""
CareerCoordinator — orchestrates the full career-consultant sub-agent swarm.

Two-phase architecture (mirrors GapAnalysisCoordinator):
  Phase 1 (parallel, deterministic — no LLM):
    • SkillPrioritizer       — ranks gaps, learning order, time estimates
    • MilestoneScheduler     — 12-week 4-phase milestone skeleton
    • QuickWinExtractor      — immediately actionable items
    • ProjectIdeaGenerator   — portfolio projects matching skill gaps

  Phase 2 (single LLM call):
    • RoadmapSynthesizer — merges Phase 1 into a polished career roadmap

Returns a dict that is 1:1 compatible with the legacy
CareerConsultantChain.generate_roadmap() output.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import logging

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.career.skill_prioritizer import SkillPrioritizer
from ai_engine.agents.sub_agents.career.milestone_scheduler import MilestoneScheduler
from ai_engine.agents.sub_agents.career.quick_win_extractor import QuickWinExtractor
from ai_engine.agents.sub_agents.career.project_idea_generator import ProjectIdeaGenerator
from ai_engine.agents.sub_agents.career.roadmap_synthesizer import RoadmapSynthesizer
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class CareerCoordinator:
    """
    Two-phase career-roadmap sub-agent coordinator.

    Phase 1 — parallel deterministic (all at once, no LLM):
      • SkillPrioritizer  • MilestoneScheduler
      • QuickWinExtractor • ProjectIdeaGenerator

    Phase 2 — LLM synthesis (after Phase 1):
      • RoadmapSynthesizer → final polished roadmap

    Returns a legacy-compatible dict matching
    CareerConsultantChain.generate_roadmap() output.
    """

    PHASE1_TIMEOUT = 15  # deterministic agents should finish <1s

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    async def generate_roadmap(
        self,
        gap_analysis: dict[str, Any],
        user_profile: dict[str, Any],
        job_title: str,
        company: str,
    ) -> dict[str, Any]:
        """Run the full career-roadmap swarm and return legacy-compatible results."""
        start = time.monotonic()

        base_context: dict[str, Any] = {
            "gap_analysis": gap_analysis,
            "user_profile": user_profile,
            "job_title": job_title,
            "company": company,
            "benchmark": gap_analysis.get("benchmark", {}),
        }

        # ── PHASE 1: Parallel deterministic agents ────────────────
        phase1_agents = [
            SkillPrioritizer(),
            MilestoneScheduler(),
            QuickWinExtractor(),
            ProjectIdeaGenerator(),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            phase1_results = await asyncio.wait_for(
                coordinator.gather(base_context),
                timeout=self.PHASE1_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("career_phase1_timeout", agents=[a.name for a in phase1_agents])
            phase1_results = [
                SubAgentResult(agent_name=a.name, error="Phase 1 timeout")
                for a in phase1_agents
            ]

        # Collect Phase 1 data by agent name
        phase1_data: dict[str, dict] = {}
        agent_latencies: dict[str, int] = {}

        for result in phase1_results:
            agent_latencies[result.agent_name] = result.latency_ms
            if result.ok:
                phase1_data[result.agent_name] = result.data
            else:
                logger.warning("career_agent_failed", agent=result.agent_name, error=result.error)

        phase1_time = time.monotonic() - start
        logger.info(
            "career_phase1_complete",
            agents_ok=len(phase1_data),
            agents_total=len(phase1_agents),
            elapsed_s=round(phase1_time, 2),
        )

        # ── PHASE 2: LLM Synthesis ───────────────────────────────
        synthesis_context = {
            "phase1_results": phase1_data,
            "user_profile": user_profile,
            "job_title": job_title,
            "company": company,
        }

        synthesizer = RoadmapSynthesizer(ai_client=self.ai_client)
        synthesis_result = await synthesizer.safe_run(synthesis_context)
        agent_latencies[synthesis_result.agent_name] = synthesis_result.latency_ms

        total_time = time.monotonic() - start

        if synthesis_result.ok:
            merged = synthesis_result.data
        else:
            # Fallback: build roadmap from Phase 1 outputs only (no LLM)
            logger.warning("career_synthesis_failed", error=synthesis_result.error)
            merged = self._build_fallback(phase1_data, job_title, company)

        # Attach diagnostics
        merged["_diagnostics"] = {
            "agent_latencies": agent_latencies,
            "phase1_agents_ok": len(phase1_data),
            "phase1_agents_total": len(phase1_agents),
            "synthesis_ok": synthesis_result.ok,
            "total_seconds": round(total_time, 2),
        }

        return merged

    # ── Fallback (Phase 1 only, no LLM) ─────────────────────────
    def _build_fallback(
        self,
        phase1_data: dict[str, dict],
        job_title: str,
        company: str,
    ) -> dict[str, Any]:
        """Build a basic roadmap from Phase 1 deterministic outputs only."""
        skills = phase1_data.get("skill_prioritizer", {})
        milestones_data = phase1_data.get("milestone_scheduler", {})
        quick_data = phase1_data.get("quick_win_extractor", {})
        project_data = phase1_data.get("project_idea_generator", {})

        # Build milestones list
        milestones = []
        for m in milestones_data.get("milestones", []):
            milestones.append({
                "week": m.get("week", 1),
                "title": m.get("title", "Milestone"),
                "description": m.get("description", ""),
                "tasks": m.get("tasks", []),
                "skills_gained": m.get("skills_gained", []),
            })

        # Build skill_development from prioritised skills
        skill_dev = []
        for s in (skills.get("prioritized_skills") or [])[:5]:
            skill_dev.append({
                "skill": s.get("skill", ""),
                "current_level": s.get("current_level", "beginner"),
                "target_level": s.get("target_level", "intermediate"),
                "timeline": f"{s.get('estimated_weeks', 4)} weeks",
                "resources": [],
                "practice_projects": [],
            })

        # Build project_recommendations
        project_recs = []
        for p in (project_data.get("projects") or [])[:3]:
            project_recs.append({
                "title": p.get("title", ""),
                "description": p.get("description", ""),
                "skills_demonstrated": p.get("skills_demonstrated", []),
                "timeline": p.get("timeline", "2 weeks"),
            })

        return {
            "roadmap": {
                "title": f"Your Path to {job_title}",
                "overview": f"A {milestones_data.get('total_duration', '12-week')} plan to prepare for the {job_title} role at {company}.",
                "total_duration": milestones_data.get("total_duration", "12 weeks"),
                "expected_outcome": f"Interview-ready for {job_title} at {company}",
                "milestones": milestones[:6],
                "skill_development": skill_dev[:5],
                "project_recommendations": project_recs[:3],
            },
            "learning_resources": [],
            "quick_wins": (quick_data.get("quick_win_strings") or [])[:8],
            "motivation_tips": [
                "Focus on progress, not perfection.",
                "Celebrate small wins along the way.",
                "Connect with others on the same journey.",
            ],
            "tools_recommended": [],
            "common_pitfalls": [
                "Trying to learn everything at once — focus on the top 3 skills first.",
                "Skipping hands-on projects — doing beats reading.",
            ],
        }
