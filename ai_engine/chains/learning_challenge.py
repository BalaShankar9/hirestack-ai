"""
Learning Challenge Chain
Generates personalized learning challenges and skill-building exercises
"""
from typing import Dict, Any

from ai_engine.client import AIClient


LEARNING_SYSTEM = """You are an expert learning designer and skill development coach.
You create engaging, practical learning challenges that help professionals rapidly develop
new skills for career advancement.

Your challenges are:
- Concrete and actionable (not just "read about X")
- Time-boxed with clear deliverables
- Progressive in difficulty
- Directly tied to job market demands
- Measurable with clear success criteria"""


CHALLENGE_PROMPT = """Generate a learning challenge for this skill gap.

SKILL TO DEVELOP: {skill_name}
CURRENT LEVEL: {current_level}
TARGET LEVEL: {target_level}
DIFFICULTY: {difficulty}
TIME AVAILABLE: {time_available}
CONTEXT: {context}

Return ONLY valid MINIFIED JSON (no markdown, no code fences).
Hard limits: steps max 8, resources max 6, success_criteria max 6.
"""

CHALLENGE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "difficulty": {"type": "STRING"},
        "estimated_hours": {"type": "NUMBER"},
        "skill": {"type": "STRING"},
        "learning_objectives": {"type": "ARRAY", "items": {"type": "STRING"}},
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "step_number": {"type": "INTEGER"},
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "deliverable": {"type": "STRING"},
                    "estimated_hours": {"type": "NUMBER"},
                },
            },
        },
        "resources": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "type": {"type": "STRING"},
                    "url": {"type": "STRING"},
                    "is_free": {"type": "BOOLEAN"},
                },
            },
        },
        "success_criteria": {"type": "ARRAY", "items": {"type": "STRING"}},
        "portfolio_output": {"type": "STRING"},
        "next_challenge": {"type": "STRING"},
    },
    "required": ["title", "description", "difficulty", "steps", "success_criteria"],
}


class LearningChallengeChain:
    """Chain for generating learning challenges."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def generate_challenge(
        self,
        skill_name: str,
        current_level: str = "beginner",
        target_level: str = "intermediate",
        difficulty: str = "intermediate",
        time_available: str = "1 week",
        context: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a learning challenge for a specific skill."""
        prompt = CHALLENGE_PROMPT.format(
            skill_name=skill_name,
            current_level=current_level,
            target_level=target_level,
            difficulty=difficulty,
            time_available=time_available,
            context=context[:1000],
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=LEARNING_SYSTEM,
            temperature=0.3,
            max_tokens=2000,
            schema=CHALLENGE_SCHEMA,
        )

        return self._validate_result(result)

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "title": "",
            "description": "",
            "difficulty": "intermediate",
            "estimated_hours": 8.0,
            "skill": "",
            "learning_objectives": [],
            "steps": [],
            "resources": [],
            "success_criteria": [],
            "portfolio_output": "",
            "next_challenge": "",
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default
        return result
