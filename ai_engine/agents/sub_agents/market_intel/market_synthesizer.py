"""
MarketSynthesizer — Phase 2 LLM agent.

Receives structured context from Phase 1 agents and generates a polished
market intelligence report with salary insights and opportunity suggestions.
"""
from __future__ import annotations

from typing import Any

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

SYNTHESIS_SYSTEM = """You are a senior labor market analyst. Produce a location-specific,
data-driven market intelligence report. Include concrete salary ranges, demand percentages,
and actionable recommendations. Return ONLY valid JSON."""

SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "market_overview": {
            "type": "OBJECT",
            "properties": {
                "location": {"type": "STRING"},
                "country": {"type": "STRING"},
                "temperature": {"type": "STRING"},
                "summary": {"type": "STRING"},
            },
        },
        "salary_insights": {
            "type": "OBJECT",
            "properties": {
                "currency": {"type": "STRING"},
                "range_low": {"type": "INTEGER"},
                "range_median": {"type": "INTEGER"},
                "range_high": {"type": "INTEGER"},
                "remote_adjustment": {"type": "STRING"},
                "factors": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        },
        "opportunity_suggestions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "match_reason": {"type": "STRING"},
                    "estimated_salary": {"type": "STRING"},
                    "demand": {"type": "STRING"},
                },
            },
        },
        "skill_gaps_to_market": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "skill": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                    "urgency": {"type": "STRING"},
                },
            },
        },
    },
    "required": ["market_overview", "salary_insights"],
}


class MarketSynthesizer(SubAgent):
    """LLM-backed synthesizer that produces the full market intelligence report."""

    def __init__(self, ai_client=None):
        super().__init__(name="market_synthesizer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        phase1: dict[str, dict] = context.get("phase1_results", {})
        title: str = context.get("title", "Software Developer")
        location: str = context.get("location", "")

        loc_data = phase1.get("location_normalizer", {})
        skill_data = phase1.get("skill_demand_mapper", {})
        level_data = phase1.get("experience_level_classifier", {})
        trend_data = phase1.get("trend_mapper", {})

        prompt = self._build_prompt(title, location, loc_data, skill_data, level_data, trend_data)

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=SYNTHESIS_SYSTEM,
            temperature=0.5,
            max_tokens=4000,
            schema=SYNTHESIS_SCHEMA,
            task_type="reasoning",
        )

        # Carry forward skills_demand and trends from Phase 1 (deterministic, more reliable)
        result.setdefault("skills_demand", skill_data.get("skills_demand", []))
        result.setdefault("emerging_trends", [
            {k: v for k, v in t.items() if k != "matching_skills"}
            for t in trend_data.get("emerging_trends", [])
        ])

        return SubAgentResult(
            agent_name=self.name,
            data=result,
            confidence=0.85,
        )

    @staticmethod
    def _build_prompt(
        title: str,
        location: str,
        loc_data: dict,
        skill_data: dict,
        level_data: dict,
        trend_data: dict,
    ) -> str:
        lines = [
            "Generate a market intelligence report.",
            f"\nROLE: {title}",
            f"LOCATION: {loc_data.get('normalized_location', location)}",
            f"COUNTRY: {loc_data.get('country', 'US')}",
            f"CURRENCY: {loc_data.get('currency', 'USD')}",
            f"COST_OF_LIVING_TIER: {loc_data.get('col_tier', 'medium')}",
            f"\nSENIORITY: {level_data.get('classified_level', 'mid')}",
            f"SALARY_MULTIPLIER: {level_data.get('salary_multiplier', 1.0)}",
            f"BAND: {level_data.get('band_label', 'Mid-Level')}",
        ]

        skills_demand = skill_data.get("skills_demand", [])
        if skills_demand:
            lines.append("\nSKILL DEMAND DATA:")
            for s in skills_demand[:10]:
                lines.append(f"  - {s['skill']}: demand={s['demand_level']}, trend={s['trend']}, premium={s['salary_premium']}")

        trends = trend_data.get("emerging_trends", [])
        if trends:
            lines.append("\nTREND DATA:")
            for t in trends[:5]:
                lines.append(f"  - {t['trend']} (relevance={t['relevance']}): {t['description']}")

        lines.append("\nProvide 3-5 opportunity_suggestions and 3-6 skill_gaps_to_market.")
        lines.append("Return ONLY valid MINIFIED JSON.")
        return "\n".join(lines)
