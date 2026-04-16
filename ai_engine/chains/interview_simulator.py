"""
Interview Simulator Chain
Generates interview questions and evaluates candidate answers
"""
from typing import Dict, Any

from ai_engine.client import AIClient


INTERVIEW_SYSTEM = """You are an expert interview coach and senior hiring manager.
You conduct realistic, role-specific interview simulations that prepare candidates
for real interviews at top companies.

Generate questions that test:
- Technical depth and breadth
- Behavioral competencies (STAR method)
- Cultural fit and motivation
- Problem-solving approach
- Communication and leadership

Provide constructive, specific feedback on answers."""


QUESTIONS_PROMPT = """Generate interview questions for this role and candidate profile.

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION SUMMARY: {jd_summary}
CANDIDATE PROFILE SUMMARY: {profile_summary}
INTERVIEW TYPE: {interview_type}
QUESTION COUNT: {question_count}

Return ONLY valid MINIFIED JSON (no markdown, no code fences).
Hard limit: questions max {question_count}.
"""

QUESTIONS_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "difficulty": {"type": "STRING"},
                    "question": {"type": "STRING"},
                    "what_we_assess": {"type": "STRING"},
                    "ideal_answer_hints": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "follow_ups": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
        "interview_focus": {"type": "STRING"},
        "preparation_tips": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["questions"],
}

EVALUATE_PROMPT = """Evaluate this interview answer.

QUESTION: {question}
CANDIDATE ANSWER: {answer}
ROLE CONTEXT: {role_context}

Return ONLY valid MINIFIED JSON (no markdown, no code fences).
"""

EVALUATE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "score": {"type": "INTEGER"},
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "improvements": {"type": "ARRAY", "items": {"type": "STRING"}},
        "model_answer": {"type": "STRING"},
        "follow_up_suggestion": {"type": "STRING"},
        "overall_feedback": {"type": "STRING"},
    },
    "required": ["score", "overall_feedback"],
}


class InterviewSimulatorChain:
    """Chain for interview simulation.

    v2.0.0 — delegates generate_questions to InterviewCoordinator
    (5-agent swarm) with automatic fallback to legacy single-LLM.
    evaluate_answer remains a direct LLM call.
    """

    VERSION = "2.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def generate_questions(
        self,
        job_title: str,
        company: str = "",
        jd_summary: str = "",
        profile_summary: str = "",
        interview_type: str = "mixed",
        question_count: int = 10,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate interview questions via sub-agent swarm."""
        import logging

        logger = logging.getLogger(__name__)

        try:
            from ai_engine.agents.sub_agents.interview.coordinator import InterviewCoordinator

            coordinator = InterviewCoordinator(ai_client=self.ai_client)
            result = await coordinator.generate_questions(
                job_title=job_title,
                company=company,
                jd_summary=jd_summary,
                profile_summary=profile_summary,
                interview_type=interview_type,
                question_count=question_count,
            )
            logger.info("interview_v2_ok", diagnostics=result.get("_diagnostics"))
            return self._validate_questions(result)

        except Exception as exc:
            logger.warning("interview_v2_fallback reason=%s", exc)
            return await self._legacy_generate_questions(
                job_title, company, jd_summary, profile_summary,
                interview_type, question_count,
            )

    async def _legacy_generate_questions(
        self,
        job_title: str,
        company: str,
        jd_summary: str,
        profile_summary: str,
        interview_type: str,
        question_count: int,
    ) -> Dict[str, Any]:
        """Legacy single-LLM question generation (v1 fallback)."""
        prompt = QUESTIONS_PROMPT.format(
            job_title=job_title,
            company=company or "the company",
            jd_summary=jd_summary[:3000],
            profile_summary=profile_summary[:2000],
            interview_type=interview_type,
            question_count=question_count,
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=INTERVIEW_SYSTEM,
            temperature=0.3,
            max_tokens=3000,
            schema=QUESTIONS_SCHEMA,
            task_type="creative",
        )

        return self._validate_questions(result)

    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        role_context: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Evaluate a candidate's answer to an interview question."""
        prompt = EVALUATE_PROMPT.format(
            question=question,
            answer=answer[:3000],
            role_context=role_context[:1000],
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=INTERVIEW_SYSTEM,
            temperature=0.0,
            max_tokens=1500,
            schema=EVALUATE_SCHEMA,
            task_type="reasoning",
        )

        if "score" in result:
            result["score"] = max(0, min(100, result["score"]))
        return result

    def _validate_questions(self, result: Dict[str, Any]) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "questions": [],
            "interview_focus": "",
            "preparation_tips": [],
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default
        return result
