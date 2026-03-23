"""
Learning Challenge Chain
Generates micro-learning challenges (quizzes, scenarios, flashcards) for skill building
"""
from typing import Dict, Any, List

from ai_engine.client import AIClient


CHALLENGE_SYSTEM = """You are an expert educational content creator who designs engaging, bite-sized learning challenges.
Each challenge should take 2-5 minutes to complete and test practical, job-relevant knowledge.
Questions must be accurate, unambiguous, and progressively challenging."""

GENERATE_CHALLENGE_PROMPT = """Generate a {challenge_type} challenge for this skill.

SKILL: {skill}
DIFFICULTY: {difficulty}
CONTEXT: The learner is preparing for a {job_context} role.

Return ONLY valid JSON:
```json
{{
    "skill": "{skill}",
    "difficulty": "{difficulty}",
    "challenge_type": "{challenge_type}",
    "question": "The challenge question or scenario (clear and specific)",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "The correct option text",
    "explanation": "Why this is correct and the others aren't (educational, 2-3 sentences)",
    "learning_tip": "A practical tip related to this concept",
    "points": 10
}}
```"""

GENERATE_DAILY_SET_PROMPT = """Generate a set of {count} diverse learning challenges covering these skills.

SKILLS TO COVER: {skills}
DIFFICULTY RANGE: {difficulty}
JOB CONTEXT: {job_context}

Mix challenge types: quiz, scenario, flashcard.
Make each unique and progressively harder.

Return ONLY valid JSON:
```json
{{
    "challenges": [
        {{
            "skill": "skill name",
            "difficulty": "easy|medium|hard",
            "challenge_type": "quiz|scenario|flashcard",
            "question": "The question",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "Correct option text",
            "explanation": "Why correct",
            "learning_tip": "Practical tip",
            "points": 10
        }}
    ],
    "theme": "Today's learning theme",
    "estimated_time_minutes": 15
}}
```"""


class LearningChallengeChain:
    """Generates micro-learning challenges."""

    def __init__(self, ai_client: AIClient):
        self.ai = ai_client

    async def generate_challenge(
        self,
        skill: str,
        difficulty: str = "medium",
        challenge_type: str = "quiz",
        job_context: str = "software engineering",
    ) -> Dict[str, Any]:
        """Generate a single learning challenge."""
        prompt = GENERATE_CHALLENGE_PROMPT.format(
            skill=skill,
            difficulty=difficulty,
            challenge_type=challenge_type,
            job_context=job_context,
        )
        return await self.ai.complete_json(
            prompt=prompt,
            system=CHALLENGE_SYSTEM,
            max_tokens=1024,
            temperature=0.7,
        )

    async def generate_daily_set(
        self,
        skills: List[str],
        difficulty: str = "medium",
        count: int = 5,
        job_context: str = "software engineering",
    ) -> Dict[str, Any]:
        """Generate a daily set of mixed challenges."""
        import json
        prompt = GENERATE_DAILY_SET_PROMPT.format(
            skills=json.dumps(skills),
            difficulty=difficulty,
            count=count,
            job_context=job_context,
        )
        return await self.ai.complete_json(
            prompt=prompt,
            system=CHALLENGE_SYSTEM,
            max_tokens=4096,
            temperature=0.7,
        )
