"""
MarketIntelCoordinator — orchestrates the market-intelligence sub-agent swarm.

Two-phase architecture:
  Phase 1 (parallel, deterministic — no LLM):
    • LocationNormalizer        — country, currency, COL tier
    • SkillDemandMapper         — skill demand levels and trends
    • ExperienceLevelClassifier — seniority level and salary band
    • TrendMapper               — emerging industry trends

  Phase 2 (single LLM call):
    • MarketSynthesizer — full market intelligence report

Returns a dict compatible with the legacy
MarketIntelligenceChain.analyze() output.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import logging

from ai_engine.agents.sub_agents.base import SubAgentCoordinator, SubAgentResult
from ai_engine.agents.sub_agents.market_intel.location_normalizer import LocationNormalizer
from ai_engine.agents.sub_agents.market_intel.skill_demand_mapper import SkillDemandMapper
from ai_engine.agents.sub_agents.market_intel.experience_level_classifier import ExperienceLevelClassifier
from ai_engine.agents.sub_agents.market_intel.trend_mapper import TrendMapper
from ai_engine.agents.sub_agents.market_intel.market_synthesizer import MarketSynthesizer
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class MarketIntelCoordinator:
    """Two-phase market-intelligence sub-agent coordinator."""

    PHASE1_TIMEOUT = 15

    def __init__(self, ai_client: Optional[AIClient] = None):
        if ai_client is None:
            from ai_engine.client import get_ai_client
            ai_client = get_ai_client()
        self.ai_client = ai_client

    async def analyze(
        self,
        location: str,
        title: str,
        skills: list[str],
        years_experience: int = 0,
    ) -> dict[str, Any]:
        """Run the full market-intel swarm and return legacy-compatible results."""
        start = time.monotonic()

        base_context: dict[str, Any] = {
            "location": location,
            "title": title,
            "skills": skills,
            "years_experience": years_experience,
        }

        # ── PHASE 1: Parallel deterministic agents ────────────
        phase1_agents = [
            LocationNormalizer(),
            SkillDemandMapper(),
            ExperienceLevelClassifier(),
            TrendMapper(),
        ]

        coordinator = SubAgentCoordinator(phase1_agents)
        try:
            phase1_results = await asyncio.wait_for(
                coordinator.gather(base_context),
                timeout=self.PHASE1_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("market_intel_phase1_timeout")
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
                logger.warning("market_intel_agent_failed", agent=result.agent_name, error=result.error)

        phase1_time = time.monotonic() - start
        logger.info(
            "market_intel_phase1_complete",
            agents_ok=len(phase1_data),
            agents_total=len(phase1_agents),
            elapsed_s=round(phase1_time, 2),
        )

        # ── PHASE 2: LLM Synthesis ───────────────────────────
        synthesis_context: dict[str, Any] = {
            "phase1_results": phase1_data,
            "title": title,
            "location": location,
        }

        synthesizer = MarketSynthesizer(ai_client=self.ai_client)
        synthesis_result = await synthesizer.safe_run(synthesis_context)
        agent_latencies[synthesis_result.agent_name] = synthesis_result.latency_ms

        total_time = time.monotonic() - start

        if synthesis_result.ok:
            merged = synthesis_result.data
        else:
            logger.warning("market_intel_synthesis_failed", error=synthesis_result.error)
            merged = self._build_fallback(phase1_data, location, title)

        merged["_diagnostics"] = {
            "agent_latencies": agent_latencies,
            "phase1_agents_ok": len(phase1_data),
            "phase1_agents_total": len(phase1_agents),
            "synthesis_ok": synthesis_result.ok,
            "total_seconds": round(total_time, 2),
        }

        return merged

    # ── Fallback (Phase 1 only) ──────────────────────────────
    @staticmethod
    def _build_fallback(
        phase1_data: dict[str, dict],
        location: str,
        title: str,
    ) -> dict[str, Any]:
        """Build a basic market report from Phase 1 outputs only."""
        loc = phase1_data.get("location_normalizer", {})
        skills = phase1_data.get("skill_demand_mapper", {})
        level = phase1_data.get("experience_level_classifier", {})
        trends = phase1_data.get("trend_mapper", {})

        currency = loc.get("currency", "USD")
        multiplier = level.get("salary_multiplier", 1.0)

        # Base median by COL tier (in USD equivalent)
        col_medians = {"very_high": 150000, "high": 110000, "medium": 80000, "low": 40000}
        base = col_medians.get(loc.get("col_tier", "medium"), 80000)
        median = int(base * multiplier)

        return {
            "market_overview": {
                "location": loc.get("normalized_location", location),
                "country": loc.get("country", "US"),
                "temperature": "warm",
                "summary": f"Market conditions for {title} in {loc.get('normalized_location', location)}.",
            },
            "skills_demand": skills.get("skills_demand", []),
            "emerging_trends": [
                {k: v for k, v in t.items() if k != "matching_skills"}
                for t in trends.get("emerging_trends", [])
            ],
            "salary_insights": {
                "currency": currency,
                "range_low": int(median * 0.75),
                "range_median": median,
                "range_high": int(median * 1.40),
                "remote_adjustment": "+5%",
                "factors": [f"Cost-of-living tier: {loc.get('col_tier', 'medium')}"],
            },
            "opportunity_suggestions": [],
            "skill_gaps_to_market": [],
        }
