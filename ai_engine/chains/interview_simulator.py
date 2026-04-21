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
QUESTION CATEGORY: {category}
CANDIDATE ANSWER: {answer}
ROLE CONTEXT: {role_context}

Rules:
- Always include a concise human-readable `feedback` field (2–4 sentences)
  that the candidate can act on immediately. Mirror it into
  `overall_feedback` for backwards compatibility.
- When QUESTION CATEGORY is "behavioral" (or the answer is clearly a
  STAR-style story), populate `star_scores` with integer 0–25 scores for
  Situation, Task, Action, and Result. Skip `star_scores` for purely
  technical / case / coding answers where STAR does not apply.
- `model_answer` must be a single tight paragraph the candidate could
  realistically deliver in 60–90 seconds.

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
        "feedback": {"type": "STRING"},
        "star_scores": {
            "type": "OBJECT",
            "properties": {
                "situation": {"type": "INTEGER"},
                "task": {"type": "INTEGER"},
                "action": {"type": "INTEGER"},
                "result": {"type": "INTEGER"},
            },
        },
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
        """Generate interview questions via sub-agent swarm with safety net.

        Guarantees a non-empty list of well-formed questions even when both
        the v2 swarm and the legacy single-LLM path fail (offline, no API
        key, schema rejection, etc.).  This prevents the route from ever
        returning a 500 for a transient LLM problem and keeps the simulator
        usable in degraded mode.
        """
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
            logger.info("interview_v2_ok", extra={"diagnostics": result.get("_diagnostics")})
            validated = self._validate_questions(result)
            if validated.get("questions"):
                return validated
            logger.warning("interview_v2_empty_questions, falling back")
        except Exception as exc:
            logger.warning("interview_v2_fallback reason=%s", exc)

        try:
            legacy = await self._legacy_generate_questions(
                job_title, company, jd_summary, profile_summary,
                interview_type, question_count,
            )
            if legacy.get("questions"):
                return legacy
            logger.warning("interview_legacy_empty_questions, using template")
        except Exception as exc:
            logger.warning("interview_legacy_failed reason=%s", exc)

        # Last-resort deterministic template so the user always gets a
        # working session even when every LLM call fails.
        return self._template_questions(
            job_title=job_title,
            interview_type=interview_type,
            question_count=question_count,
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
        category: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Evaluate a candidate's answer to an interview question.

        Always resolves to a sensible payload even when the LLM is offline
        — the simulator must never break the user's flow.
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            prompt = EVALUATE_PROMPT.format(
                question=question,
                category=(category or "general"),
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
        except Exception as exc:
            logger.warning("interview_evaluate_failed reason=%s", exc)
            result = {}

        if not isinstance(result, dict):
            result = {}

        # Normalise score
        if "score" not in result or not isinstance(result.get("score"), (int, float)):
            # Heuristic fallback: short answers score lower than long ones,
            # capped so we never inflate a no-answer.
            length = len((answer or "").strip())
            result["score"] = 70 if length > 200 else 55 if length > 60 else 30
        result["score"] = max(0, min(100, int(result["score"])))

        # Always have a feedback string the UI can render
        feedback = (
            (result.get("feedback") or "").strip()
            or (result.get("overall_feedback") or "").strip()
        )
        if not feedback:
            feedback = (
                "Solid attempt. Add a concrete example with measurable outcome and "
                "name the trade-offs you weighed."
            )
        result["feedback"] = feedback
        result.setdefault("overall_feedback", feedback)
        result.setdefault("strengths", [])
        result.setdefault("improvements", [])

        # Sanitise star_scores when present
        ss = result.get("star_scores")
        if isinstance(ss, dict):
            cleaned: Dict[str, int] = {}
            for key in ("situation", "task", "action", "result"):
                val = ss.get(key)
                if isinstance(val, (int, float)):
                    cleaned[key] = max(0, min(25, int(val)))
            if cleaned:
                result["star_scores"] = cleaned
            else:
                result.pop("star_scores", None)
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
        # Make sure every question has a stable id
        normalised = []
        for idx, q in enumerate(result.get("questions") or []):
            if not isinstance(q, dict):
                continue
            q = dict(q)
            if not q.get("id"):
                q["id"] = f"q-{idx + 1}"
            if not q.get("question") and q.get("text"):
                q["question"] = q["text"]
            normalised.append(q)
        result["questions"] = normalised
        return result

    def _template_questions(
        self, job_title: str, interview_type: str, question_count: int
    ) -> Dict[str, Any]:
        """Deterministic, role-aware fallback questions used when every LLM
        call fails. Keeps the simulator usable offline / in degraded mode."""
        role = (job_title or "this role").strip() or "this role"
        itype = (interview_type or "mixed").lower()
        bank = {
            "behavioral": [
                f"Walk me through a recent project for which you'd hire yourself for {role}. What made it hard?",
                "Tell me about a time you disagreed with a teammate. How did you resolve it?",
                "Describe a moment you took ownership of a problem outside your formal scope.",
                "Share a failure you learned the most from. What would you do differently?",
                "Give an example of a deadline you almost missed and how you recovered.",
            ],
            "technical": [
                f"Design a small system that a {role} would own end-to-end. Walk me through the trade-offs.",
                "How would you debug a production issue you've never seen before? Take me through your first 30 minutes.",
                "Explain a non-trivial technical decision you made recently and what you'd change today.",
                "What is a recent piece of tech you adopted, and how did you justify the cost?",
                "How do you decide when to refactor versus rewrite?",
            ],
            "situational": [
                f"You join as a {role} on day one and inherit a failing project. What is your first week?",
                "A senior stakeholder rejects your recommendation. How do you respond?",
                "You discover a teammate cutting corners. What do you do?",
                "You have two weeks to ship something users will love. How do you spend them?",
                "A critical dependency goes down 30 minutes before launch. Walk me through your response.",
            ],
            "case": [
                f"Estimate the impact a {role} could have on revenue in their first quarter. Show your reasoning.",
                "Pick a product you use daily and tell me what you'd change first and why.",
                "Walk me through how you'd diagnose a 20% drop in weekly active users.",
                "How would you decide whether to enter a new market?",
                "Sketch a back-of-envelope unit economics for a SaaS product priced at $20/mo.",
            ],
        }
        mixed = [
            bank["behavioral"][0],
            bank["technical"][0],
            bank["situational"][0],
            bank["behavioral"][1],
            bank["technical"][1],
        ]
        pool = bank.get(itype) or mixed
        chosen = pool[: max(1, min(question_count, len(pool)))]
        questions = []
        for i, text in enumerate(chosen):
            questions.append({
                "id": f"q-{i + 1}",
                "category": itype,
                "difficulty": "intermediate",
                "question": text,
                "what_we_assess": "clarity, ownership, and concrete outcomes",
                "ideal_answer_hints": [
                    "Use the STAR framework where it fits",
                    "Quantify the outcome",
                    "Name the trade-offs you weighed",
                ],
                "follow_ups": ["What would you do differently next time?"],
            })
        return {
            "questions": questions,
            "interview_focus": f"Core competencies for {role}",
            "preparation_tips": [
                "Lead with the result, then the story",
                "Keep each answer under 90 seconds",
                "Bring at least one number to every example",
            ],
            "_fallback": True,
        }
