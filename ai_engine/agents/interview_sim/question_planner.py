"""
QuestionPlanner — generates an ordered, calibrated interview question
set for a (role, jd, resume) tuple.

Strategy:
1. Single LLM JSON call with strict schema → 8–12 questions ordered
   behavioral → role-specific → curveball.
2. If the LLM is unavailable, fall back to a deterministic static bank
   so unit tests + offline smoke runs still produce a usable session.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from ai_engine.agents.interview_sim.schemas import InterviewQuestion, QuestionKind

logger = logging.getLogger(__name__)


_QUESTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "kind"],
                "properties": {
                    "text": {"type": "string"},
                    "kind": {"type": "string"},
                    "signal_target": {"type": "string"},
                    "rubric": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


_SYSTEM = (
    "You are an elite interview coach designing realistic practice questions. "
    "Produce a JSON object {questions:[...]} with 8-12 items ordered: "
    "warm-up behavioral → role-specific behavioral → 1-2 technical / situational → "
    "1 curveball/motivational. Each question must include kind ∈ "
    "{behavioral,technical,situational,motivational,curveball}, a signal_target "
    "(the trait being probed: ownership, scope, depth, communication, etc), and "
    "a rubric of 2-4 bullets describing what a great answer covers. "
    "Output JSON only — no prose."
)


_FALLBACK_BANK: List[Dict[str, Any]] = [
    {"text": "Tell me about yourself and what brought you to this role.",
     "kind": "behavioral", "signal_target": "narrative",
     "rubric": ["clear arc", "ties to role", "≤90s"]},
    {"text": "Describe a project you owned end-to-end. What was the impact?",
     "kind": "behavioral", "signal_target": "ownership",
     "rubric": ["scope", "decisions", "measurable outcome"]},
    {"text": "Walk me through how you would approach a problem you've never seen before.",
     "kind": "situational", "signal_target": "first-principles thinking",
     "rubric": ["framing", "trade-offs", "validation"]},
    {"text": "Tell me about a time you disagreed with a teammate. How did you resolve it?",
     "kind": "behavioral", "signal_target": "communication",
     "rubric": ["empathy", "resolution path", "outcome"]},
    {"text": "What's a technical decision you made that you'd revisit today?",
     "kind": "technical", "signal_target": "self-awareness",
     "rubric": ["context", "what changed", "lesson"]},
    {"text": "Describe how you handle ambiguous requirements.",
     "kind": "situational", "signal_target": "execution",
     "rubric": ["clarification", "iteration", "communication"]},
    {"text": "Tell me about a time you missed a deadline. What happened?",
     "kind": "behavioral", "signal_target": "accountability",
     "rubric": ["root cause", "ownership", "what changed"]},
    {"text": "Why this role at this company, and not somewhere else?",
     "kind": "motivational", "signal_target": "fit",
     "rubric": ["specific to company", "ties to your goals", "honest"]},
    {"text": "Where do you want to be in three years?",
     "kind": "motivational", "signal_target": "trajectory",
     "rubric": ["specific", "growth-oriented", "aligned with role"]},
    {"text": "If we hired you tomorrow, what would your first 30 days look like?",
     "kind": "curveball", "signal_target": "initiative",
     "rubric": ["learning plan", "early wins", "stakeholders"]},
]


class QuestionPlanner:
    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self.ai_client = ai_client

    def _get_client(self) -> Any:
        if self.ai_client is not None:
            return self.ai_client
        from ai_engine.client import get_ai_client
        return get_ai_client()

    async def plan(
        self,
        *,
        role: str,
        jd: Optional[str] = None,
        resume: Optional[str] = None,
        question_count: int = 10,
    ) -> List[InterviewQuestion]:
        n = max(5, min(int(question_count or 10), 15))
        prompt_lines: List[str] = [f"Role: {role}", f"Question count: {n}"]
        if jd:
            prompt_lines.append(f"Job description:\n{jd[:4000]}")
        if resume:
            prompt_lines.append(f"Candidate resume:\n{resume[:4000]}")
        prompt_lines.append(
            'Return JSON: {"questions":[{"text":..., "kind":..., '
            '"signal_target":..., "rubric":[...]}]}'
        )
        prompt = "\n".join(prompt_lines)

        try:
            client = self._get_client()
            payload = await client.complete_json(
                prompt=prompt,
                system=_SYSTEM,
                schema=_QUESTION_SCHEMA,
                temperature=0.5,
                task_type="interview_questions",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("interview_planner_llm_failed: %s", str(exc)[:200])
            payload = {"questions": _FALLBACK_BANK[:n]}

        return self._coerce(payload, n)

    def _coerce(self, payload: Any, n: int) -> List[InterviewQuestion]:
        if not isinstance(payload, dict):
            payload = {"questions": []}
        raw_list = payload.get("questions") or []
        out: List[InterviewQuestion] = []
        for raw in raw_list[:n]:
            if not isinstance(raw, dict) or not raw.get("text"):
                continue
            kind_raw = str(raw.get("kind") or "behavioral").lower().strip()
            try:
                kind = QuestionKind(kind_raw)
            except ValueError:
                kind = QuestionKind.behavioral
            rubric = [str(x) for x in (raw.get("rubric") or []) if x]
            out.append(InterviewQuestion(
                id=str(uuid.uuid4()),
                text=str(raw["text"])[:1000],
                kind=kind,
                signal_target=raw.get("signal_target"),
                rubric=rubric[:6],
            ))
        if not out:
            for raw in _FALLBACK_BANK[:n]:
                out.append(InterviewQuestion(
                    id=str(uuid.uuid4()),
                    text=raw["text"], kind=QuestionKind(raw["kind"]),
                    signal_target=raw.get("signal_target"),
                    rubric=raw.get("rubric") or [],
                ))
        return out
