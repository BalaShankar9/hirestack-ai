"""
SalarySynthesizer — Phase 2 LLM agent.

Receives structured context from Phase 1 agents and generates
negotiation scripts, talking points, and overall assessment.
"""
from __future__ import annotations

from typing import Any

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

SYNTHESIS_SYSTEM = """You are an expert compensation analyst and salary negotiation coach.
Provide specific, data-informed negotiation scripts and strategies.
Return ONLY valid JSON."""

SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "negotiation_scripts": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "scenario": {"type": "STRING"},
                    "script": {"type": "STRING"},
                },
            },
        },
        "talking_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "total_compensation_tips": {"type": "ARRAY", "items": {"type": "STRING"}},
        "overall_assessment": {"type": "STRING"},
    },
    "required": ["negotiation_scripts", "overall_assessment"],
}


class SalarySynthesizer(SubAgent):
    """LLM-backed synthesizer for negotiation coaching output."""

    def __init__(self, ai_client=None):
        super().__init__(name="salary_synthesizer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        phase1: dict[str, dict] = context.get("phase1_results", {})
        job_title: str = context.get("job_title", "")
        company: str = context.get("company", "")

        market = phase1.get("market_range_estimator", {})
        value = phase1.get("value_driver_analyzer", {})
        offer = phase1.get("offer_analyzer", {})
        framework = phase1.get("negotiation_framework_builder", {})

        prompt = self._build_prompt(job_title, company, market, value, offer, framework)

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=SYNTHESIS_SYSTEM,
            temperature=0.15,
            max_tokens=3000,
            schema=SYNTHESIS_SCHEMA,
            task_type="reasoning",
        )

        return SubAgentResult(
            agent_name=self.name,
            data=result,
            confidence=0.85,
        )

    @staticmethod
    def _build_prompt(
        job_title: str,
        company: str,
        market: dict,
        value: dict,
        offer: dict,
        framework: dict,
    ) -> str:
        lines = [
            f"Generate salary negotiation coaching for a {job_title} role at {company or 'the company'}.",
            f"\nMARKET RANGE: {market.get('currency', 'USD')} {market.get('low', 0):,} – {market.get('median', 0):,} – {market.get('high', 0):,}",
            f"SENIORITY: {market.get('seniority', 'mid')}",
            "\nSTRATEGY:",
            f"  Recommended ask: {framework.get('recommended_ask', 0):,}",
            f"  Opening position: {framework.get('opening_position', 0):,}",
            f"  Walk-away point: {framework.get('walk_away_point', 0):,}",
            f"  Approach: {framework.get('approach_description', '')}",
            f"  Timing: {framework.get('timing', '')}",
        ]

        drivers = value.get("key_value_drivers", [])
        if drivers:
            lines.append(f"\nVALUE DRIVERS: {'; '.join(drivers[:5])}")

        detractors = value.get("value_detractors", [])
        if detractors:
            lines.append(f"DETRACTORS: {'; '.join(detractors[:3])}")

        if offer.get("has_offer"):
            lines.append(f"\nOFFER SALARY: {offer.get('offer_salary_extracted', 'unknown')}")
            red_flags = offer.get("red_flags", [])
            if red_flags:
                lines.append(f"RED FLAGS: {'; '.join(red_flags[:4])}")
            positives = offer.get("positive_signals", [])
            if positives:
                lines.append(f"POSITIVES: {'; '.join(positives[:4])}")

        lines.append("\nProvide 3-5 negotiation_scripts, 5-8 talking_points, 3-5 total_compensation_tips.")
        lines.append("Return ONLY valid MINIFIED JSON.")
        return "\n".join(lines)
