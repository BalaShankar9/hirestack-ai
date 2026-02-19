"""
Career Consultant Chain
Generates personalized career roadmaps and improvement recommendations
"""
from typing import Dict, Any, List

from ai_engine.client import AIClient


CAREER_CONSULTANT_SYSTEM = """You are a world-class career coach and professional development expert.

Your expertise includes:
- Career transition strategies and planning
- Skills development and learning paths
- Professional certification guidance
- Portfolio and project development
- Personal branding and positioning
- Interview preparation and coaching

Create detailed, actionable, and realistic roadmaps that help candidates close their gaps and achieve their career goals.
Be specific with timelines, resources, and expected outcomes. Focus on practical steps they can take immediately."""


ROADMAP_PROMPT = """Create a career improvement roadmap based on this gap analysis:

GAP ANALYSIS:
{gap_analysis}

USER PROFILE:
{user_profile}

TARGET ROLE: {job_title} at {company}

Create a detailed 12-week improvement plan.

Return ONLY valid JSON (no markdown, no code fences). Requirements:
- Return MINIFIED JSON on a single line (no pretty-printing, no extra whitespace/newlines).
- Keep all strings SINGLE-LINE (no unescaped newline characters).
- Do NOT include trailing commas.
- Keep the overall response concise (aim for < 12k characters).
- Hard limits on list sizes:
  - roadmap.milestones: max 6
  - roadmap.skill_development: max 5
  - roadmap.project_recommendations: max 3
  - learning_resources: max 6
  - quick_wins: max 8
  - motivation_tips: max 8

JSON shape (keys required; omit any extra commentary):

{{
  "roadmap": {{
    "title": "Your Path to {job_title}",
    "overview": "High-level summary",
    "total_duration": "12 weeks",
    "expected_outcome": "What the candidate will achieve",
    "milestones": [
      {{
        "week": 1,
        "title": "Milestone title",
        "description": "What will be achieved",
        "tasks": ["Task 1", "Task 2"],
        "skills_gained": ["Skills developed"]
      }}
    ],
    "skill_development": [
      {{
        "skill": "Skill to develop",
        "current_level": "intermediate",
        "target_level": "advanced",
        "timeline": "4 weeks",
        "resources": ["Course/book name"],
        "practice_projects": ["Project ideas"]
      }}
    ],
    "project_recommendations": [
      {{
        "title": "Project name",
        "description": "What to build",
        "skills_demonstrated": ["Skills this shows"],
        "timeline": "2 weeks"
      }}
    ]
  }},
  "learning_resources": [
    {{
      "title": "Resource name",
      "type": "course|book|tutorial",
      "provider": "Platform/Author",
      "skill_covered": "What it teaches",
      "priority": "required|recommended|optional"
    }}
  ],
  "quick_wins": ["Things candidate can do immediately"],
  "motivation_tips": ["Tips to stay motivated"]
}}

Include 4-6 milestones, 3-5 skills, 2-3 projects, and 4-6 learning resources. Be specific and realistic."""

ROADMAP_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "roadmap": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "overview": {"type": "STRING"},
                "total_duration": {"type": "STRING"},
                "expected_outcome": {"type": "STRING"},
                "milestones": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "week": {"type": "INTEGER"},
                            "title": {"type": "STRING"},
                            "description": {"type": "STRING"},
                            "tasks": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "skills_gained": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    },
                },
                "skill_development": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "skill": {"type": "STRING"},
                            "current_level": {
                                "type": "STRING",
                                "enum": ["beginner", "intermediate", "advanced", "expert"],
                            },
                            "target_level": {
                                "type": "STRING",
                                "enum": ["beginner", "intermediate", "advanced", "expert"],
                            },
                            "timeline": {"type": "STRING"},
                            "resources": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "practice_projects": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    },
                },
                "project_recommendations": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "title": {"type": "STRING"},
                            "description": {"type": "STRING"},
                            "skills_demonstrated": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "timeline": {"type": "STRING"},
                        },
                    },
                },
            },
        },
        "learning_resources": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "type": {"type": "STRING", "enum": ["course", "book", "tutorial", "article", "video"]},
                    "provider": {"type": "STRING"},
                    "skill_covered": {"type": "STRING"},
                    "priority": {"type": "STRING", "enum": ["required", "recommended", "optional"]},
                    "url": {"type": "STRING"},
                    "duration": {"type": "STRING"},
                },
            },
        },
        "quick_wins": {"type": "ARRAY", "items": {"type": "STRING"}},
        "motivation_tips": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tools_recommended": {"type": "ARRAY", "items": {"type": "STRING"}},
        "common_pitfalls": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["roadmap"],
}


class CareerConsultantChain:
    """Chain for generating career improvement roadmaps."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def generate_roadmap(
        self,
        gap_analysis: Dict[str, Any],
        user_profile: Dict[str, Any],
        job_title: str,
        company: str
    ) -> Dict[str, Any]:
        """Generate a comprehensive career improvement roadmap."""
        import json

        # Truncate large inputs to keep prompt size reasonable
        gap_str = json.dumps(gap_analysis, indent=2)[:3000]
        profile_str = json.dumps(user_profile, indent=2)[:2000]

        prompt = ROADMAP_PROMPT.format(
            gap_analysis=gap_str,
            user_profile=profile_str,
            job_title=job_title,
            company=company
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=CAREER_CONSULTANT_SYSTEM,
            temperature=0.2,
            max_tokens=6000,
            schema=ROADMAP_SCHEMA,
        )

        return self._validate_result(result)

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize the roadmap result."""
        defaults = {
            "roadmap": {},
            "learning_resources": [],
            "tools_recommended": [],
            "motivation_tips": [],
            "common_pitfalls": []
        }

        for key, default in defaults.items():
            if key not in result:
                result[key] = default

        return result

    async def generate_quick_tips(
        self,
        gap_analysis: Dict[str, Any]
    ) -> List[str]:
        """Generate quick improvement tips based on gap analysis."""
        quick_wins = gap_analysis.get("quick_wins", [])
        recommendations = gap_analysis.get("recommendations", [])

        tips = quick_wins[:5]

        # Add top recommendations as tips
        for rec in recommendations[:3]:
            if rec.get("title"):
                tips.append(f"{rec['title']}: {rec.get('description', '')[:100]}")

        return tips

    async def suggest_projects(
        self,
        skill_gaps: List[Dict[str, Any]],
        job_title: str
    ) -> List[Dict[str, Any]]:
        """Suggest specific projects to close skill gaps."""
        prompt = f"""Suggest 3 practical projects that would help close these skill gaps for a {job_title} role:

SKILL GAPS:
{skill_gaps}

Return ONLY valid JSON:
```json
{{
  "projects": [
    {{
      "title": "Project name",
      "description": "What to build",
      "skills_addressed": ["Gaps this closes"],
      "difficulty": "beginner|intermediate|advanced",
      "estimated_time": "2 weeks",
      "tech_stack": ["Technologies to use"],
      "steps": ["Implementation steps"],
      "portfolio_value": "Why this impresses recruiters"
    }}
  ]
}}
```"""

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=CAREER_CONSULTANT_SYSTEM,
            temperature=0.6,
            max_tokens=2000
        )

        return result.get("projects", [])
