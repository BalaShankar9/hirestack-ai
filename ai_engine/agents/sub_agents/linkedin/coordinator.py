"""
LinkedInCoordinator — orchestrates the LinkedIn-advisor sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel, deterministic — no LLM):
    • ProfileScorer      — completeness score and tips
    • SkillGapFinder     — missing high-demand skills
    • ExperienceCritic   — experience entry fitness
    • KeywordExtractor   — keyword density analysis

  Phase 2 (single LLM call):
    • LinkedInSynthesizer — headline, summary, skills, improvements

Returns a dict compatible with the legacy
LinkedInAdvisorChain.analyze() output.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional
import logging

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.linkedin.profile_scorer import ProfileScorer
from ai_engine.agents.sub_agents.linkedin.skill_gap_finder import SkillGapFinder
from ai_engine.agents.sub_agents.linkedin.experience_critic import ExperienceCritic
from ai_engine.agents.sub_agents.linkedin.keyword_extractor import KeywordExtractor
from ai_engine.agents.sub_agents.linkedin.linkedin_synthesizer import LinkedInSynthesizer
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class LinkedInCoordinator:
    """Two-phase LinkedIn-advisor sub-agent coordinator."""

    PHASE1_TIMEOUT = 15

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    async def analyze(self, profile_data: dict[str, Any]) -> dict[str, Any]:
        """Run the full LinkedIn-advisor swarm and return legacy-compatible results."""
        start = time.monotonic()

        base_context: dict[str, Any] = {"profile_data": profile_data}

        # ── PHASE 1: Parallel deterministic agents ────────────
        phase1_agents = [
            ProfileScorer(),
            SkillGapFinder(),
            ExperienceCritic(),
            KeywordExtractor(),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            phase1_results = await asyncio.wait_for(
                coordinator.gather(base_context),
                timeout=self.PHASE1_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("linkedin_phase1_timeout")
            phase1_results = [
                SubAgentResult(agent_name=a.name, error="Phase 1 timeout")
                for a in phase1_agents
            ]

        phase1_data: dict[str, dict] = {}
        agent_latencies: dict[str, int] = {}
        for result in phase1_results:
            agent_latencies[result.agent_name] = result.latency_ms
            if result.ok:
                phase1_data[result.agent_name] = result.data
            else:
                logger.warning("linkedin_agent_failed", agent=result.agent_name, error=result.error)

        phase1_time = time.monotonic() - start
        logger.info(
            "linkedin_phase1_complete",
            agents_ok=len(phase1_data),
            agents_total=len(phase1_agents),
            elapsed_s=round(phase1_time, 2),
        )

        # ── PHASE 2: LLM Synthesis ───────────────────────────
        synthesis_context: dict[str, Any] = {
            "phase1_results": phase1_data,
            "profile_data": profile_data,
        }

        synthesizer = LinkedInSynthesizer(ai_client=self.ai_client)
        synthesis_result = await synthesizer.safe_run(synthesis_context)
        agent_latencies[synthesis_result.agent_name] = synthesis_result.latency_ms

        total_time = time.monotonic() - start

        if synthesis_result.ok:
            merged = synthesis_result.data
        else:
            logger.warning("linkedin_synthesis_failed", error=synthesis_result.error)
            merged = self._build_fallback(phase1_data)

        # Overlay Phase 1 structured data (more reliable than LLM numbers)
        scorer = phase1_data.get("profile_scorer", {})
        gaps = phase1_data.get("skill_gap_finder", {})

        merged["overall_score"] = scorer.get("overall_score", merged.get("overall_score", 50))
        merged["profile_completeness_tips"] = scorer.get("completeness_tips", merged.get("profile_completeness_tips", []))

        # Supplement skills_to_add with Phase 1 gaps
        existing_to_add = set(s.lower() for s in merged.get("skills_to_add", []))
        for skill in gaps.get("missing_high_demand_skills", []):
            if skill.lower() not in existing_to_add and len(merged.get("skills_to_add", [])) < 12:
                merged.setdefault("skills_to_add", []).append(skill)

        merged["_diagnostics"] = {
            "agent_latencies": agent_latencies,
            "phase1_agents_ok": len(phase1_data),
            "phase1_agents_total": len(phase1_agents),
            "synthesis_ok": synthesis_result.ok,
            "total_seconds": round(total_time, 2),
        }

        return merged

    # ── Fallback (no LLM) ────────────────────────────────────
    @staticmethod
    def _build_fallback(phase1_data: dict[str, dict]) -> dict[str, Any]:
        """Build basic LinkedIn advice from Phase 1 outputs only."""
        scorer = phase1_data.get("profile_scorer", {})
        gaps = phase1_data.get("skill_gap_finder", {})
        critic = phase1_data.get("experience_critic", {})

        return {
            "headline_suggestions": [
                "Consider a headline like: [Your Role] | [Key Skill] | Helping [Who] achieve [What]",
            ],
            "summary_rewrite": "We couldn't generate a full rewrite, but focus on: a strong opening hook, your key career narrative, measurable achievements, and a call-to-action.",
            "skills_to_add": gaps.get("missing_high_demand_skills", [])[:10],
            "experience_improvements": [
                {
                    "role": c.get("role", ""),
                    "current_style": f"Score: {c.get('score', 0)}/100",
                    "linkedin_suggestion": "; ".join(c.get("issues", ["Add metrics and action verbs"])),
                }
                for c in critic.get("experience_critiques", [])[:4]
            ],
            "overall_score": scorer.get("overall_score", 50),
            "profile_completeness_tips": scorer.get("completeness_tips", []),
            "priority_actions": [
                "Upgrade your headline with role + value proposition + key skill",
                "Add quantified achievements to your top 2 experience entries",
                "Add at least 15 skills relevant to your target role",
            ],
        }
