"""
SalaryCoordinator — orchestrates the salary-coach sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel, deterministic — no LLM):
    • MarketRangeEstimator        — salary range estimate
    • ValueDriverAnalyzer         — candidate value drivers / detractors
    • OfferAnalyzer               — offer parsing and red flags
    • NegotiationFrameworkBuilder — strategy skeleton

  Phase 2 (single LLM call):
    • SalarySynthesizer — negotiation scripts and assessment

Returns a dict compatible with the legacy
SalaryCoachChain.analyze_salary() output.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import logging

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.salary.market_range_estimator import MarketRangeEstimator
from ai_engine.agents.sub_agents.salary.value_driver_analyzer import ValueDriverAnalyzer
from ai_engine.agents.sub_agents.salary.offer_analyzer import OfferAnalyzer
from ai_engine.agents.sub_agents.salary.negotiation_framework_builder import NegotiationFrameworkBuilder
from ai_engine.agents.sub_agents.salary.salary_synthesizer import SalarySynthesizer
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class SalaryCoordinator:
    """Two-phase salary-coaching sub-agent coordinator."""

    PHASE1_TIMEOUT = 15

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    async def analyze_salary(
        self,
        job_title: str,
        company: str = "",
        location: str = "",
        years_experience: int = 0,
        skills_summary: str = "",
        current_salary: str = "not disclosed",
        target_salary: str = "not specified",
        offer_details: str = "no offer yet",
        industry: str = "",
    ) -> dict[str, Any]:
        """Run the full salary-coach swarm and return legacy-compatible results."""
        start = time.monotonic()

        base_context: dict[str, Any] = {
            "job_title": job_title,
            "company": company,
            "location": location,
            "years_experience": years_experience,
            "skills_summary": skills_summary,
            "current_salary": current_salary,
            "target_salary": target_salary,
            "offer_details": offer_details,
            "industry": industry,
        }

        # ── PHASE 1: Parallel deterministic agents ────────────
        phase1_agents = [
            MarketRangeEstimator(),
            ValueDriverAnalyzer(),
            OfferAnalyzer(),
            NegotiationFrameworkBuilder(),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            phase1_results = await asyncio.wait_for(
                coordinator.gather(base_context),
                timeout=self.PHASE1_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("salary_phase1_timeout")
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
                logger.warning("salary_agent_failed", agent=result.agent_name, error=result.error)

        phase1_time = time.monotonic() - start
        logger.info(
            "salary_phase1_complete",
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

        synthesizer = SalarySynthesizer(ai_client=self.ai_client)
        synthesis_result = await synthesizer.safe_run(synthesis_context)
        agent_latencies[synthesis_result.agent_name] = synthesis_result.latency_ms

        total_time = time.monotonic() - start

        if synthesis_result.ok:
            merged = synthesis_result.data
        else:
            logger.warning("salary_synthesis_failed", error=synthesis_result.error)
            merged = self._build_fallback(phase1_data)

        # Overlay Phase 1 structured data (more reliable than LLM estimates)
        market = phase1_data.get("market_range_estimator", {})
        value = phase1_data.get("value_driver_analyzer", {})
        offer = phase1_data.get("offer_analyzer", {})
        framework = phase1_data.get("negotiation_framework_builder", {})

        merged["market_analysis"] = {
            "low": market.get("low", 0),
            "median": market.get("median", 0),
            "high": market.get("high", 0),
            "currency": market.get("currency", "USD"),
            "percentile_estimate": market.get("percentile_estimate", ""),
            "data_notes": f"Heuristic estimate for {market.get('seniority', 'mid')}-level in {market.get('col_tier', 'medium')} COL market",
        }

        merged["candidate_value_assessment"] = {
            "estimated_range_low": market.get("low", 0),
            "estimated_range_high": market.get("high", 0),
            "key_value_drivers": value.get("key_value_drivers", []),
            "value_detractors": value.get("value_detractors", []),
        }

        merged["negotiation_strategy"] = {
            "recommended_ask": framework.get("recommended_ask", 0),
            "walk_away_point": framework.get("walk_away_point", 0),
            "opening_position": framework.get("opening_position", 0),
            "approach": framework.get("approach_description", ""),
            "timing": framework.get("timing", ""),
        }

        merged.setdefault("red_flags", offer.get("red_flags", []))

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
        """Build basic salary coaching from Phase 1 outputs only."""
        framework = phase1_data.get("negotiation_framework_builder", {})
        value = phase1_data.get("value_driver_analyzer", {})

        return {
            "negotiation_scripts": [
                {
                    "scenario": "Initial salary discussion",
                    "script": f"Based on my research and experience, I'm targeting a compensation of {framework.get('recommended_ask', 0):,}. I'm confident this reflects the value I'd bring to the role.",
                },
            ],
            "talking_points": value.get("key_value_drivers", ["Highlight your key achievements and skills."]),
            "total_compensation_tips": [
                "Consider base salary, bonus, equity, benefits, and PTO as a package.",
                "Ask about signing bonus if base salary is firm.",
                "Negotiate review timeline — a 6-month review can accelerate raises.",
            ],
            "overall_assessment": f"Strategy: {framework.get('approach_description', 'Present your value clearly.')}",
        }
