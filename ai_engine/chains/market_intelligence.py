"""
Market Intelligence Chain
Analyzes job market conditions based on user's location, skills, and experience level.
"""
from typing import Dict, Any, List


MARKET_INTEL_SYSTEM = """You are a senior labor market analyst with deep expertise in global tech hiring trends,
salary benchmarking, and career strategy. You have access to comprehensive market data across all industries
and geographies.

Your analysis must be:
- Specific to the user's location and skill set
- Data-driven with concrete numbers (salary ranges, demand percentages)
- Actionable with clear recommendations
- Current and forward-looking (emerging trends)

Return ONLY valid JSON. No markdown, no code fences."""

MARKET_INTEL_PROMPT = """Analyze the job market for this professional based on their location and skills.

LOCATION: {location}
CURRENT TITLE: {title}
YEARS OF EXPERIENCE: {years_experience}
TOP SKILLS: {skills}

Return a JSON object with exactly these fields:
{{
  "market_overview": {{
    "location": "Normalized location name",
    "country": "Country code (e.g., GB, US, IN)",
    "temperature": "hot|warm|cool|cold",
    "summary": "2-3 sentence market overview for this role/location"
  }},
  "skills_demand": [
    {{
      "skill": "Skill name",
      "demand_level": "high|medium|low",
      "trend": "rising|stable|declining",
      "salary_premium": "+12%",
      "note": "Brief context"
    }}
  ],
  "emerging_trends": [
    {{
      "trend": "Trend name",
      "relevance": "high|medium|low",
      "description": "1-2 sentence description",
      "timeframe": "6-12 months"
    }}
  ],
  "salary_insights": {{
    "currency": "GBP",
    "range_low": 35000,
    "range_median": 50000,
    "range_high": 75000,
    "remote_adjustment": "+5%",
    "factors": ["Key factors affecting salary in this market"]
  }},
  "opportunity_suggestions": [
    {{
      "title": "Suggested role title",
      "match_reason": "Why this fits their skills",
      "estimated_salary": "£50,000-65,000",
      "demand": "high|medium"
    }}
  ],
  "skill_gaps_to_market": [
    {{
      "skill": "Missing skill name",
      "reason": "Why this skill matters in this market",
      "urgency": "high|medium|low"
    }}
  ]
}}

Include 6-10 items in skills_demand, 3-5 in emerging_trends, 3-5 in opportunity_suggestions, 3-6 in skill_gaps_to_market.
Base salary ranges on the specific location and role level."""


class MarketIntelligenceChain:
    """Generates location-based market intelligence for career planning."""

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def analyze(
        self,
        location: str,
        title: str,
        skills: List[str],
        years_experience: int = 0,
    ) -> Dict[str, Any]:
        """Analyze job market conditions for the given profile."""
        skills_text = ", ".join(skills[:20]) if skills else "Not specified"

        prompt = MARKET_INTEL_PROMPT.format(
            location=location or "Not specified",
            title=title or "Software Developer",
            years_experience=years_experience,
            skills=skills_text,
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=MARKET_INTEL_SYSTEM,
            max_tokens=4000,
            temperature=0.5,
            task_type="reasoning",
        )

        # Validate and set defaults
        result.setdefault("market_overview", {"location": location, "temperature": "warm", "summary": ""})
        result.setdefault("skills_demand", [])
        result.setdefault("emerging_trends", [])
        result.setdefault("salary_insights", {"currency": "USD", "range_low": 0, "range_median": 0, "range_high": 0})
        result.setdefault("opportunity_suggestions", [])
        result.setdefault("skill_gaps_to_market", [])

        return result
