"""
GapAnalysisCoordinator — orchestrates the full gap-analysis sub-agent swarm.

Two-phase architecture (mirrors IntelCoordinator):
  Phase 1 (parallel, deterministic — no LLM):
    • TechnicalSkillAnalyst  — skill-by-skill comparison
    • ExperienceAnalyst      — years, domain, leadership, trajectory
    • EducationCertAnalyst   — degree + certification matching
    • SoftSkillCultureAnalyst— soft skill & culture-fit scoring
    • StrengthMapper         — competitive advantages & quick wins

  Phase 2 (single LLM call):
    • GapSynthesizer — merges Phase 1 outputs into a unified report
      with executive_summary, recommendations, interview_readiness

Returns a dict that is 1:1 compatible with the legacy GapAnalyzerChain
output, so downstream consumers (CV gen, cover letter gen, career
roadmap, interview prep) work without any changes.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import logging

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.gap_analysis.technical_skill_analyst import TechnicalSkillAnalyst
from ai_engine.agents.sub_agents.gap_analysis.experience_analyst import ExperienceAnalyst
from ai_engine.agents.sub_agents.gap_analysis.education_cert_analyst import EducationCertAnalyst
from ai_engine.agents.sub_agents.gap_analysis.soft_skill_analyst import SoftSkillCultureAnalyst
from ai_engine.agents.sub_agents.gap_analysis.strength_mapper import StrengthMapper
from ai_engine.agents.sub_agents.gap_analysis.gap_synthesizer import GapSynthesizer
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class GapAnalysisCoordinator:
    """
    Two-phase gap-analysis sub-agent coordinator.

    Phase 1 — Parallel deterministic analysis (all at once, no LLM):
      • TechnicalSkillAnalyst
      • ExperienceAnalyst
      • EducationCertAnalyst
      • SoftSkillCultureAnalyst
      • StrengthMapper

    Phase 2 — LLM synthesis (after Phase 1 completes):
      • GapSynthesizer → final merged report

    Returns a legacy-compatible dict matching GapAnalyzerChain.analyze_gaps() output.
    """

    PHASE1_TIMEOUT = 15  # seconds — all Phase 1 agents are deterministic, should finish <1s

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    async def analyze(
        self,
        user_profile: dict[str, Any],
        benchmark: dict[str, Any],
        job_title: str,
        company: str,
    ) -> dict[str, Any]:
        """Run the full gap-analysis swarm and return legacy-compatible results."""
        start = time.monotonic()

        # Build the JD text from benchmark for agents that scan it
        jd_text = benchmark.get("ideal_profile", {}).get("description", "")
        if isinstance(benchmark.get("ideal_profile"), str):
            jd_text = benchmark["ideal_profile"]

        base_context: dict[str, Any] = {
            "user_profile": user_profile,
            "benchmark": benchmark,
            "jd_text": jd_text,
            "job_title": job_title,
            "company": company,
        }

        # ── PHASE 1: Parallel deterministic agents ────────────────
        phase1_agents = [
            TechnicalSkillAnalyst(),
            ExperienceAnalyst(),
            EducationCertAnalyst(),
            SoftSkillCultureAnalyst(),
            StrengthMapper(),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            phase1_results = await asyncio.wait_for(
                coordinator.gather(base_context),
                timeout=self.PHASE1_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("gap_phase1_timeout", agents=[a.name for a in phase1_agents])
            phase1_results = [
                SubAgentResult(agent_name=a.name, error="Phase 1 timeout")
                for a in phase1_agents
            ]

        # Collect Phase 1 data by agent name
        phase1_data: dict[str, dict] = {}
        agent_latencies: dict[str, int] = {}
        phase1_score_inputs: dict[str, float] = {}

        for result in phase1_results:
            agent_latencies[result.agent_name] = result.latency_ms
            if result.ok:
                phase1_data[result.agent_name] = result.data
                # Extract individual scores for fallback scoring
                if "technical_score" in result.data:
                    phase1_score_inputs["technical"] = result.data["technical_score"]
                if "experience_score" in result.data:
                    phase1_score_inputs["experience"] = result.data["experience_score"]
                if "overall_score" in result.data and result.agent_name == "education_cert_analyst":
                    phase1_score_inputs["education"] = result.data["overall_score"]
                if "overall_score" in result.data and result.agent_name == "soft_skill_analyst":
                    phase1_score_inputs["soft_skills"] = result.data["overall_score"]
            else:
                logger.warning("gap_agent_failed", agent=result.agent_name, error=result.error)

        phase1_time = time.monotonic() - start
        logger.info(
            "gap_phase1_complete",
            agents_ok=len(phase1_data),
            agents_total=len(phase1_agents),
            elapsed_s=round(phase1_time, 2),
        )

        # ── PHASE 2: LLM Synthesis ───────────────────────────────
        synthesis_context = {
            "phase1_results": phase1_data,
            "job_title": job_title,
            "company": company,
        }

        synthesizer = GapSynthesizer(ai_client=self.ai_client)
        synthesis_result = await synthesizer.safe_run(synthesis_context)
        agent_latencies[synthesis_result.agent_name] = synthesis_result.latency_ms

        total_time = time.monotonic() - start

        if synthesis_result.ok:
            merged = synthesis_result.data
        else:
            # Fallback: build a basic report from just Phase 1 deterministic scores
            logger.warning("gap_synthesis_failed", error=synthesis_result.error)
            merged = self._build_fallback(phase1_data, phase1_score_inputs, job_title, company)

        # Attach diagnostics (stripped by downstream if not needed)
        merged["_diagnostics"] = {
            "agent_latencies": agent_latencies,
            "phase1_agents_ok": len(phase1_data),
            "phase1_agents_total": len(phase1_agents),
            "synthesis_ok": synthesis_result.ok,
            "total_seconds": round(total_time, 2),
        }

        return merged

    def _build_fallback(
        self,
        phase1_data: dict[str, dict],
        scores: dict[str, float],
        job_title: str,
        company: str,
    ) -> dict[str, Any]:
        """Build a basic gap report from Phase 1 outputs only (no LLM)."""

        # Compute weighted score from deterministic agents
        weights = {
            "technical": 0.30,
            "experience": 0.25,
            "education": 0.10,
            "soft_skills": 0.15,
        }
        total_weight = sum(weights[k] for k in scores if k in weights)
        if total_weight > 0:
            raw = sum(scores.get(k, 0) * weights.get(k, 0) for k in weights)
            compat = int(raw / total_weight)
        else:
            compat = 50

        compat = max(0, min(100, compat))

        if compat >= 75:
            readiness = "strong-match"
        elif compat >= 55:
            readiness = "competitive"
        elif compat >= 35:
            readiness = "needs-work"
        else:
            readiness = "not-ready"

        tech = phase1_data.get("technical_skill_analyst", {})
        strengths_data = phase1_data.get("strength_mapper", {})

        return {
            "compatibility_score": compat,
            "readiness_level": readiness,
            "executive_summary": f"Deterministic analysis scored {compat}/100 for {job_title} at {company}. LLM synthesis unavailable — showing raw data.",
            "category_scores": self._build_category_scores(scores),
            "skill_gaps": tech.get("skill_gaps", [])[:12],
            "experience_gaps": phase1_data.get("experience_analyst", {}).get("experience_gaps", [])[:6],
            "strengths": strengths_data.get("strengths", [])[:8],
            "recommendations": [],
            "quick_wins": strengths_data.get("quick_wins", [])[:8],
            "interview_readiness": {
                "ready_to_interview": compat >= 55,
                "preparation_needed": [],
                "potential_questions": [],
                "talking_points": [],
            },
        }

    def _build_category_scores(self, scores: dict[str, float]) -> dict[str, dict]:
        """Build the category_scores structure from raw deterministic scores."""
        default_weights = {
            "technical_skills": 0.30,
            "experience": 0.25,
            "education": 0.10,
            "certifications": 0.10,
            "soft_skills": 0.15,
            "projects_portfolio": 0.10,
        }
        score_map = {
            "technical_skills": scores.get("technical", 50),
            "experience": scores.get("experience", 50),
            "education": scores.get("education", 50),
            "certifications": scores.get("education", 50),  # shared with education agent
            "soft_skills": scores.get("soft_skills", 50),
            "projects_portfolio": 50,  # not independently scored in Phase 1
        }

        result = {}
        for cat, weight in default_weights.items():
            score = int(score_map.get(cat, 50))
            result[cat] = {
                "score": score,
                "weight": weight,
                "weighted_score": round(score * weight, 1),
                "summary": "",
            }
        return result
