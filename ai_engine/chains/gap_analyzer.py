"""
Gap Analyzer Chain
Compares user profiles against benchmarks and identifies gaps
"""
from typing import Dict, Any

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


GAP_ANALYSIS_PROMPT = """Perform a gap analysis comparing this candidate to the ideal benchmark.

CANDIDATE_PROFILE_JSON:
{user_profile}

IDEAL_BENCHMARK_JSON:
{benchmark}

ROLE: {job_title} at {company}

Return ONLY valid MINIFIED JSON that matches the provided response schema exactly.
Constraints:
- Single-line JSON (no unescaped newlines).
- No markdown, no code fences, no trailing commas, no extra commentary.
- Keep strings short (aim <180 chars each).
- Hard limits on list sizes:
  - skill_gaps: max 12
  - experience_gaps: max 6
  - strengths: max 8
  - recommendations: max 10
  - quick_wins: max 8
  - interview_readiness.preparation_needed: max 8
  - interview_readiness.potential_questions: max 8
  - interview_readiness.talking_points: max 8
  - recommendations.action_items: max 5
"""

GAP_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "compatibility_score": {"type": "INTEGER"},
        "readiness_level": {
            "type": "STRING",
            "enum": ["needs-work", "competitive", "strong-match", "not-ready"],
        },
        "executive_summary": {"type": "STRING"},
        "category_scores": {
            "type": "OBJECT",
            "properties": {
                "technical_skills": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "experience": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "education": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "certifications": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "soft_skills": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
                "projects_portfolio": {
                    "type": "OBJECT",
                    "properties": {
                        "score": {"type": "INTEGER"},
                        "weight": {"type": "NUMBER"},
                        "weighted_score": {"type": "NUMBER"},
                        "summary": {"type": "STRING"},
                    },
                },
            },
        },
        "skill_gaps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "skill": {"type": "STRING"},
                    "required_level": {
                        "type": "STRING",
                        "enum": ["expert", "advanced", "intermediate", "beginner"],
                    },
                    "current_level": {
                        "type": "STRING",
                        "enum": ["expert", "advanced", "intermediate", "beginner", "none"],
                    },
                    "gap_severity": {
                        "type": "STRING",
                        "enum": ["critical", "major", "moderate", "minor"],
                    },
                    "importance_for_role": {
                        "type": "STRING",
                        "enum": ["critical", "important", "preferred"],
                    },
                    "recommendation": {"type": "STRING"},
                    "estimated_time_to_close": {"type": "STRING"},
                },
            },
        },
        "experience_gaps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "area": {"type": "STRING"},
                    "required": {"type": "STRING"},
                    "current": {"type": "STRING"},
                    "gap_severity": {
                        "type": "STRING",
                        "enum": ["critical", "major", "moderate", "minor"],
                    },
                    "recommendation": {"type": "STRING"},
                    "alternatives": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
        "strengths": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "area": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "competitive_advantage": {"type": "STRING"},
                    "how_to_leverage": {"type": "STRING"},
                },
            },
        },
        "recommendations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "priority": {"type": "INTEGER"},
                    "category": {
                        "type": "STRING",
                        "enum": ["skills", "experience", "certification", "project", "other"],
                    },
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "action_items": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "estimated_effort": {"type": "STRING"},
                    "impact": {"type": "STRING"},
                },
            },
        },
        "quick_wins": {"type": "ARRAY", "items": {"type": "STRING"}},
        "interview_readiness": {
            "type": "OBJECT",
            "properties": {
                "ready_to_interview": {"type": "BOOLEAN"},
                "preparation_needed": {"type": "ARRAY", "items": {"type": "STRING"}},
                "potential_questions": {"type": "ARRAY", "items": {"type": "STRING"}},
                "talking_points": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        },
    },
    "required": ["compatibility_score", "readiness_level", "executive_summary"],
}


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

        # Keep prompts compact to avoid shrinking the model's available output budget
        # (large prompts can cause MAX_TOKENS truncation and invalid JSON).
        compact_user = {
            "name": user_profile.get("name"),
            "title": user_profile.get("title"),
            "summary": user_profile.get("summary"),
            "skills": (user_profile.get("skills") or [])[:30],
            "experience": (user_profile.get("experience") or [])[:10],
            "education": (user_profile.get("education") or [])[:5],
            "certifications": (user_profile.get("certifications") or [])[:10],
            "projects": (user_profile.get("projects") or [])[:10],
        }
        compact_benchmark = {
            "ideal_profile": benchmark.get("ideal_profile"),
            "ideal_skills": (benchmark.get("ideal_skills") or [])[:25],
            "ideal_experience": (benchmark.get("ideal_experience") or [])[:10],
            "ideal_education": (benchmark.get("ideal_education") or [])[:5],
            "ideal_certifications": (benchmark.get("ideal_certifications") or [])[:10],
            "soft_skills": (benchmark.get("soft_skills") or [])[:12],
            "industry_knowledge": (benchmark.get("industry_knowledge") or [])[:8],
            "scoring_weights": benchmark.get("scoring_weights") or {},
        }

        user_str = json.dumps(compact_user, separators=(",", ":"), ensure_ascii=False)[:8000]
        benchmark_str = json.dumps(compact_benchmark, separators=(",", ":"), ensure_ascii=False)[:8000]

        prompt = GAP_ANALYSIS_PROMPT.format(
            user_profile=user_str,
            benchmark=benchmark_str,
            job_title=job_title,
            company=company,
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=GAP_ANALYZER_SYSTEM,
            temperature=0.0,
            max_tokens=3000,
            schema=GAP_ANALYSIS_SCHEMA,
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
            # Handle case where LLM returns strings instead of dicts
            result["recommendations"] = [
                r for r in result["recommendations"] if isinstance(r, dict)
            ]
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
