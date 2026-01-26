"""
Gap Analyzer Chain
Compares user profiles against benchmarks and identifies gaps
"""
from typing import Dict, Any, List

from ai_engine.client import AIClient


GAP_ANALYZER_SYSTEM = """You are an expert career analyst and talent assessment specialist.

Your task is to objectively compare a candidate's profile against an ideal benchmark for a specific role.
Provide honest, constructive feedback that helps the candidate understand:
1. Where they stand relative to the ideal
2. Their specific gaps and how to close them
3. Their strengths they can leverage
4. Actionable steps to improve their candidacy

Be specific, realistic, and supportive. Use data-driven comparisons where possible.
Scores should be fair and reflect actual gaps, not inflated to make the candidate feel good."""


GAP_ANALYSIS_PROMPT = """Perform a comprehensive gap analysis comparing this candidate to the ideal benchmark.

CANDIDATE PROFILE:
{user_profile}

IDEAL BENCHMARK:
{benchmark}

TARGET ROLE: {job_title} at {company}

Analyze every aspect and return ONLY valid JSON:

```json
{{
  "compatibility_score": 72,
  "readiness_level": "needs-work|competitive|strong-match|not-ready",
  "executive_summary": "2-3 sentence overview of the candidate's fit",

  "category_scores": {{
    "technical_skills": {{
      "score": 75,
      "weight": 0.30,
      "weighted_score": 22.5,
      "summary": "Brief assessment"
    }},
    "experience": {{
      "score": 65,
      "weight": 0.25,
      "weighted_score": 16.25,
      "summary": "Brief assessment"
    }},
    "education": {{
      "score": 80,
      "weight": 0.10,
      "weighted_score": 8.0,
      "summary": "Brief assessment"
    }},
    "certifications": {{
      "score": 40,
      "weight": 0.10,
      "weighted_score": 4.0,
      "summary": "Brief assessment"
    }},
    "soft_skills": {{
      "score": 70,
      "weight": 0.15,
      "weighted_score": 10.5,
      "summary": "Brief assessment"
    }},
    "projects_portfolio": {{
      "score": 60,
      "weight": 0.10,
      "weighted_score": 6.0,
      "summary": "Brief assessment"
    }}
  }},

  "skill_gaps": [
    {{
      "skill": "Skill name",
      "required_level": "expert",
      "current_level": "intermediate",
      "gap_severity": "critical|major|moderate|minor",
      "importance_for_role": "critical|important|preferred",
      "recommendation": "Specific steps to close the gap",
      "resources": ["Course/book/resource suggestions"],
      "estimated_time_to_close": "3-6 months"
    }}
  ],

  "experience_gaps": [
    {{
      "area": "Leadership experience",
      "required": "3+ years leading teams of 5+",
      "current": "1 year leading team of 2",
      "gap_severity": "major",
      "recommendation": "How to gain this experience",
      "alternatives": ["Ways to demonstrate this without direct experience"]
    }}
  ],

  "education_gaps": [
    {{
      "requirement": "What's required",
      "current_status": "What candidate has",
      "gap_severity": "minor|moderate|major",
      "recommendation": "How to address",
      "alternatives": ["Alternative qualifications that could help"]
    }}
  ],

  "certification_gaps": [
    {{
      "certification": "AWS Solutions Architect",
      "importance": "required|highly_recommended|nice_to_have",
      "recommendation": "Study path",
      "estimated_time": "2-3 months",
      "resources": ["Study resources"]
    }}
  ],

  "project_gaps": [
    {{
      "project_type": "Type of project needed",
      "importance": "critical|important|preferred",
      "current_status": "What candidate has",
      "recommendation": "Project idea to fill the gap",
      "skills_demonstrated": ["Skills this would show"]
    }}
  ],

  "strengths": [
    {{
      "area": "Strength area",
      "description": "What makes this a strength",
      "competitive_advantage": "How this helps the candidate stand out",
      "how_to_leverage": "How to emphasize this in applications"
    }}
  ],

  "recommendations": [
    {{
      "priority": 1,
      "category": "skills|experience|certification|project|other",
      "title": "Recommendation title",
      "description": "Detailed recommendation",
      "action_items": ["Step 1", "Step 2", "Step 3"],
      "estimated_effort": "2 weeks|1 month|3 months",
      "impact": "How much this will improve candidacy"
    }}
  ],

  "quick_wins": [
    "Things candidate can do immediately to improve"
  ],

  "long_term_investments": [
    "Longer-term improvements to consider"
  ],

  "interview_readiness": {{
    "ready_to_interview": true/false,
    "preparation_needed": ["Areas to prepare"],
    "potential_questions": ["Likely interview questions based on gaps"],
    "talking_points": ["Strengths to emphasize"]
  }}
}}
```

Be thorough and honest. The candidate needs accurate feedback to improve."""


class GapAnalyzerChain:
    """Chain for analyzing gaps between user profiles and benchmarks."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def analyze_gaps(
        self,
        user_profile: Dict[str, Any],
        benchmark: Dict[str, Any],
        job_title: str,
        company: str
    ) -> Dict[str, Any]:
        """Perform comprehensive gap analysis."""
        import json

        prompt = GAP_ANALYSIS_PROMPT.format(
            user_profile=json.dumps(user_profile, indent=2),
            benchmark=json.dumps(benchmark, indent=2),
            job_title=job_title,
            company=company
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=GAP_ANALYZER_SYSTEM,
            temperature=0.3,
            max_tokens=6000
        )

        return self._validate_result(result)

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize the gap analysis result."""
        # Ensure compatibility score is in valid range
        if "compatibility_score" in result:
            result["compatibility_score"] = max(0, min(100, result["compatibility_score"]))

        # Ensure all required fields exist
        defaults = {
            "compatibility_score": 50,
            "readiness_level": "needs-work",
            "executive_summary": "",
            "category_scores": {},
            "skill_gaps": [],
            "experience_gaps": [],
            "education_gaps": [],
            "certification_gaps": [],
            "project_gaps": [],
            "strengths": [],
            "recommendations": [],
            "quick_wins": [],
            "long_term_investments": [],
            "interview_readiness": {}
        }

        for key, default in defaults.items():
            if key not in result:
                result[key] = default

        # Sort recommendations by priority
        if result.get("recommendations"):
            result["recommendations"] = sorted(
                result["recommendations"],
                key=lambda x: x.get("priority", 99)
            )

        return result

    async def calculate_compatibility_score(
        self,
        user_profile: Dict[str, Any],
        benchmark: Dict[str, Any]
    ) -> int:
        """Calculate a quick compatibility score without full analysis."""
        # Quick scoring based on key metrics
        score = 50  # Base score

        user_skills = set(s.get("name", "").lower() for s in user_profile.get("skills", []))
        required_skills = set(s.get("name", "").lower() for s in benchmark.get("ideal_skills", []))

        if required_skills:
            skill_match = len(user_skills & required_skills) / len(required_skills)
            score += int(skill_match * 25)

        # Experience matching
        user_exp_years = sum(
            self._parse_duration(e.get("duration", "0"))
            for e in user_profile.get("experience", [])
        )
        required_years = benchmark.get("ideal_profile", {}).get("years_experience", 5)

        exp_ratio = min(user_exp_years / max(required_years, 1), 1.0)
        score += int(exp_ratio * 25)

        return min(100, max(0, score))

    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string to years."""
        import re
        duration_str = str(duration_str).lower()

        years = 0
        # Match patterns like "3 years", "2.5 years", etc.
        year_match = re.search(r'(\d+\.?\d*)\s*year', duration_str)
        if year_match:
            years += float(year_match.group(1))

        # Match months
        month_match = re.search(r'(\d+)\s*month', duration_str)
        if month_match:
            years += float(month_match.group(1)) / 12

        return years
