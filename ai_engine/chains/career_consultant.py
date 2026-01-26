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


ROADMAP_PROMPT = """Create a comprehensive career improvement roadmap based on this gap analysis:

GAP ANALYSIS:
{gap_analysis}

USER PROFILE:
{user_profile}

TARGET ROLE: {job_title} at {company}

Create a detailed 12-week improvement plan. Return ONLY valid JSON:

```json
{{
  "roadmap": {{
    "title": "Your Path to {job_title}",
    "overview": "High-level summary of the roadmap",
    "total_duration": "12 weeks",
    "expected_outcome": "What the candidate will achieve",
    "commitment_required": "10-15 hours/week",

    "milestones": [
      {{
        "id": "M1",
        "week": 1,
        "title": "Milestone title",
        "description": "What will be achieved",
        "tasks": ["Task 1", "Task 2"],
        "deliverables": ["Deliverable 1"],
        "success_criteria": ["How to know it's done"],
        "skills_gained": ["Skills developed"]
      }}
    ],

    "weekly_plans": [
      {{
        "week": 1,
        "theme": "Foundation Building",
        "goals": ["Goal 1", "Goal 2"],
        "hours_required": 12,
        "activities": [
          {{
            "activity": "What to do",
            "duration": "2 hours",
            "purpose": "Why it matters",
            "resources": ["Resource links/names"]
          }}
        ],
        "checkpoint": "How to verify progress"
      }}
    ],

    "skill_development": [
      {{
        "skill": "Skill to develop",
        "current_level": "intermediate",
        "target_level": "advanced",
        "timeline": "4 weeks",
        "learning_path": [
          {{
            "step": 1,
            "activity": "What to do",
            "resource": "Course/book name",
            "duration": "1 week"
          }}
        ],
        "practice_projects": ["Project ideas to apply the skill"],
        "assessment": "How to verify skill level"
      }}
    ],

    "certification_path": [
      {{
        "certification": "Certification name",
        "priority": "high|medium|low",
        "timeline": "6 weeks",
        "study_plan": [
          {{
            "week": "1-2",
            "focus": "Topic focus",
            "resources": ["Study materials"]
          }}
        ],
        "exam_tips": ["Preparation tips"],
        "cost": "Approximate cost"
      }}
    ],

    "project_recommendations": [
      {{
        "title": "Project name",
        "type": "personal|contribution|portfolio",
        "description": "What to build",
        "skills_demonstrated": ["Skills this shows"],
        "timeline": "2 weeks",
        "implementation_steps": [
          "Step 1: Setup",
          "Step 2: Core features",
          "Step 3: Polish"
        ],
        "presentation_tips": ["How to showcase this"]
      }}
    ],

    "networking_plan": {{
      "weekly_activities": ["Networking tasks"],
      "communities_to_join": ["Relevant communities"],
      "people_to_connect_with": ["Types of professionals"],
      "events_to_attend": ["Event types"]
    }},

    "interview_prep": {{
      "start_week": 8,
      "focus_areas": ["Technical", "Behavioral"],
      "mock_interview_schedule": "How often to practice",
      "resources": ["Prep resources"],
      "common_questions": ["Questions to prepare for"]
    }},

    "progress_tracking": {{
      "weekly_review": "What to review each week",
      "metrics_to_track": ["Measurable progress indicators"],
      "adjustment_triggers": ["When to modify the plan"]
    }}
  }},

  "learning_resources": [
    {{
      "title": "Resource name",
      "type": "course|book|tutorial|documentation|video",
      "url": "URL if available",
      "provider": "Platform/Author",
      "skill_covered": "What it teaches",
      "duration": "How long it takes",
      "cost": "free|$amount",
      "priority": "required|recommended|optional",
      "notes": "Why this resource"
    }}
  ],

  "tools_recommended": [
    {{
      "tool": "Tool name",
      "purpose": "What it's for",
      "skill_level": "beginner-friendly|intermediate|advanced",
      "free_tier": true/false,
      "alternatives": ["Alternative tools"]
    }}
  ],

  "motivation_tips": [
    "Tips to stay motivated during the journey"
  ],

  "common_pitfalls": [
    {{
      "pitfall": "Common mistake",
      "how_to_avoid": "Prevention strategy"
    }}
  ]
}}
```

Create a realistic, achievable plan that maximizes improvement in the given timeframe."""


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

        prompt = ROADMAP_PROMPT.format(
            gap_analysis=json.dumps(gap_analysis, indent=2),
            user_profile=json.dumps(user_profile, indent=2),
            job_title=job_title,
            company=company
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=CAREER_CONSULTANT_SYSTEM,
            temperature=0.5,
            max_tokens=8000
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
