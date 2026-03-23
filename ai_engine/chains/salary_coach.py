"""
Salary Coach Chain
Analyzes compensation data and coaches negotiation strategy
"""
from typing import Dict, Any

from ai_engine.client import AIClient


SALARY_COACH_SYSTEM = """You are an expert compensation analyst and salary negotiation coach.
You have deep knowledge of market rates across industries, roles, and geographies.

You help candidates:
- Understand their market value based on skills and experience
- Build a compelling compensation case
- Develop negotiation strategies
- Evaluate job offers comprehensively (salary, equity, benefits, growth)
- Handle counter-offers and multiple competing offers

Always provide specific, data-informed ranges and practical negotiation scripts."""


SALARY_ANALYSIS_PROMPT = """Analyze the compensation situation and provide coaching.

ROLE: {job_title}
COMPANY: {company}
LOCATION: {location}
CANDIDATE EXPERIENCE: {years_experience} years
CANDIDATE SKILLS: {skills_summary}
CURRENT SALARY: {current_salary}
TARGET SALARY: {target_salary}
OFFER DETAILS: {offer_details}
INDUSTRY: {industry}

Return ONLY valid MINIFIED JSON (no markdown, no code fences).
Hard limits: negotiation_scripts max 5, talking_points max 8, red_flags max 8.
"""

SALARY_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "market_analysis": {
            "type": "OBJECT",
            "properties": {
                "low": {"type": "INTEGER"},
                "median": {"type": "INTEGER"},
                "high": {"type": "INTEGER"},
                "currency": {"type": "STRING"},
                "percentile_estimate": {"type": "STRING"},
                "data_notes": {"type": "STRING"},
            },
        },
        "candidate_value_assessment": {
            "type": "OBJECT",
            "properties": {
                "estimated_range_low": {"type": "INTEGER"},
                "estimated_range_high": {"type": "INTEGER"},
                "key_value_drivers": {"type": "ARRAY", "items": {"type": "STRING"}},
                "value_detractors": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        },
        "negotiation_strategy": {
            "type": "OBJECT",
            "properties": {
                "recommended_ask": {"type": "INTEGER"},
                "walk_away_point": {"type": "INTEGER"},
                "opening_position": {"type": "INTEGER"},
                "approach": {"type": "STRING"},
                "timing": {"type": "STRING"},
            },
        },
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
        "red_flags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "total_compensation_tips": {"type": "ARRAY", "items": {"type": "STRING"}},
        "overall_assessment": {"type": "STRING"},
    },
    "required": ["market_analysis", "negotiation_strategy", "overall_assessment"],
}


class SalaryCoachChain:
    """Chain for salary analysis and negotiation coaching."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
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
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Analyze compensation and provide negotiation coaching."""
        prompt = SALARY_ANALYSIS_PROMPT.format(
            job_title=job_title,
            company=company or "the company",
            location=location or "not specified",
            years_experience=years_experience,
            skills_summary=skills_summary[:2000],
            current_salary=current_salary,
            target_salary=target_salary,
            offer_details=offer_details[:2000],
            industry=industry or "general",
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=SALARY_COACH_SYSTEM,
            temperature=0.1,
            max_tokens=3000,
            schema=SALARY_ANALYSIS_SCHEMA,
            task_type="reasoning",
        )

        return self._validate_result(result)

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "market_analysis": {},
            "candidate_value_assessment": {},
            "negotiation_strategy": {},
            "negotiation_scripts": [],
            "talking_points": [],
            "red_flags": [],
            "total_compensation_tips": [],
            "overall_assessment": "",
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default
        return result
