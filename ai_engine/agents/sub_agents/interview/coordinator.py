"""
InterviewCoordinator — orchestrates the interview-simulator sub-agent swarm.

Two-phase architecture (mirrors CareerCoordinator):
  Phase 1 (parallel, deterministic — no LLM):
    • QuestionFrameworkBuilder  — category/difficulty distribution
    • RoleContextExtractor      — key skills, seniority, domains
    • CandidateGapProber        — weak spots to probe
    • PrepTipGenerator          — preparation tips

  Phase 2 (single LLM call):
    • QuestionSynthesizer — generates the actual interview questions

Returns a dict compatible with the legacy
InterviewSimulatorChain.generate_questions() output.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import logging

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.interview.question_framework_builder import QuestionFrameworkBuilder
from ai_engine.agents.sub_agents.interview.role_context_extractor import RoleContextExtractor
from ai_engine.agents.sub_agents.interview.candidate_gap_prober import CandidateGapProber
from ai_engine.agents.sub_agents.interview.prep_tip_generator import PrepTipGenerator
from ai_engine.agents.sub_agents.interview.question_synthesizer import QuestionSynthesizer
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class InterviewCoordinator:
    """Two-phase interview-question sub-agent coordinator."""

    PHASE1_TIMEOUT = 15

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    async def generate_questions(
        self,
        job_title: str,
        company: str = "",
        jd_summary: str = "",
        profile_summary: str = "",
        interview_type: str = "mixed",
        question_count: int = 10,
    ) -> dict[str, Any]:
        """Run the full interview-question swarm and return legacy-compatible results."""
        start = time.monotonic()

        base_context: dict[str, Any] = {
            "job_title": job_title,
            "company": company,
            "jd_summary": jd_summary,
            "profile_summary": profile_summary,
            "interview_type": interview_type,
            "question_count": question_count,
        }

        # ── PHASE 1: Parallel deterministic agents ────────────
        phase1_agents = [
            QuestionFrameworkBuilder(),
            RoleContextExtractor(),
            CandidateGapProber(),
            PrepTipGenerator(),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            phase1_results = await asyncio.wait_for(
                coordinator.gather(base_context),
                timeout=self.PHASE1_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("interview_phase1_timeout")
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
                logger.warning("interview_agent_failed", agent=result.agent_name, error=result.error)

        phase1_time = time.monotonic() - start
        logger.info(
            "interview_phase1_complete",
            agents_ok=len(phase1_data),
            agents_total=len(phase1_agents),
            elapsed_s=round(phase1_time, 2),
        )

        # ── PHASE 2: LLM Synthesis ───────────────────────────
        synthesis_context: dict[str, Any] = {
            "phase1_results": phase1_data,
            "job_title": job_title,
            "company": company,
        }

        synthesizer = QuestionSynthesizer(ai_client=self.ai_client)
        synthesis_result = await synthesizer.safe_run(synthesis_context)
        agent_latencies[synthesis_result.agent_name] = synthesis_result.latency_ms

        total_time = time.monotonic() - start

        if synthesis_result.ok:
            merged = synthesis_result.data
        else:
            logger.warning("interview_synthesis_failed", error=synthesis_result.error)
            merged = self._build_fallback(phase1_data, job_title, question_count)

        # Attach prep tips from Phase 1
        prep = phase1_data.get("prep_tip_generator", {})
        merged.setdefault("preparation_tips", prep.get("preparation_tips", []))

        # Attach diagnostics
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
    def _build_fallback(
        phase1_data: dict[str, dict],
        job_title: str,
        question_count: int,
    ) -> dict[str, Any]:
        """Build basic questions from Phase 1 templates only."""
        framework = phase1_data.get("question_framework_builder", {})
        role_ctx = phase1_data.get("role_context_extractor", {})
        gap_data = phase1_data.get("candidate_gap_prober", {})

        cat_dist = framework.get("category_distribution", {"mixed": question_count})
        missing = gap_data.get("missing_skills", [])
        jd_skills = role_ctx.get("jd_skills", [])

        questions: list[dict[str, Any]] = []
        q_idx = 0

        # Generate a template question per category
        for category, count in cat_dist.items():
            for _ in range(count):
                q_idx += 1
                q: dict[str, Any] = {
                    "id": f"q{q_idx}",
                    "category": category,
                    "difficulty": "medium",
                    "question": f"Tell me about your experience with {category.replace('_', ' ')} as it relates to the {job_title} role.",
                    "what_we_assess": category.replace("_", " "),
                    "ideal_answer_hints": [],
                    "follow_ups": [],
                }
                # Enrich with gap probes if skill gaps exist
                if missing and q_idx <= len(missing):
                    skill = missing[q_idx - 1]
                    q["question"] = f"Can you describe a project where you used {skill}? What challenges did you face?"
                    q["what_we_assess"] = f"Depth of experience with {skill}"
                questions.append(q)
                if len(questions) >= question_count:
                    break
            if len(questions) >= question_count:
                break

        return {
            "questions": questions[:question_count],
            "interview_focus": f"{job_title} interview preparation",
        }
