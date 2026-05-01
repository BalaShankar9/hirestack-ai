"""
InterviewSimulator — orchestrates the practice loop.

Lifecycle:
    sim = InterviewSimulator()
    session = await sim.start_session(role=..., jd=..., resume=...)
    next_q = sim.next_question(session)             # returns InterviewQuestion or None
    sim.submit_answer(session, question_id, answer) # scores + advances cursor
    report = sim.finalize(session)                  # SessionReport

Sessions are returned by value (Pydantic models). Persistence is the
caller's responsibility — the route layer keeps an in-memory dict.
"""
from __future__ import annotations

import base64
import logging
import time
import uuid
from typing import Any, List, Optional

from ai_engine.agents.interview_sim.question_planner import QuestionPlanner
from ai_engine.agents.interview_sim.schemas import (
    InterviewQuestion,
    InterviewSession,
    InterviewTurn,
    SessionReport,
)
from ai_engine.agents.interview_sim.scorer import score_answer
from ai_engine.agents.interview_sim.tts_adapter import TTSAdapter

logger = logging.getLogger(__name__)


class InterviewSimulator:
    def __init__(
        self,
        *,
        ai_client: Optional[Any] = None,
        planner: Optional[QuestionPlanner] = None,
        tts: Optional[TTSAdapter] = None,
    ) -> None:
        self.planner = planner or QuestionPlanner(ai_client=ai_client)
        self._tts = tts  # None means lazy-construct on first use

    def _get_tts(self) -> TTSAdapter:
        if self._tts is None:
            self._tts = TTSAdapter()
        return self._tts

    # ─── session lifecycle ──────────────────────────────────────────────

    async def start_session(
        self,
        *,
        role: str,
        jd: Optional[str] = None,
        resume: Optional[str] = None,
        question_count: int = 10,
        audience_hint: Optional[str] = None,
        with_audio: bool = False,
    ) -> InterviewSession:
        if not role or not role.strip():
            raise ValueError("role must be a non-empty string")
        questions = await self.planner.plan(
            role=role, jd=jd, resume=resume, question_count=question_count,
        )
        if with_audio:
            tts = self._get_tts()
            for q in questions:
                audio = await tts.synthesize(q.text)
                if audio:
                    q.audio_b64 = base64.b64encode(audio).decode("ascii")
        session = InterviewSession(
            session_id=str(uuid.uuid4()),
            role=role,
            audience_hint=audience_hint,
            questions=questions,
            cursor=0,
        )
        return session

    def next_question(self, session: InterviewSession) -> Optional[InterviewQuestion]:
        if session.finalized:
            return None
        if session.cursor >= len(session.questions):
            return None
        return session.questions[session.cursor]

    def submit_answer(
        self,
        session: InterviewSession,
        *,
        question_id: str,
        answer: str,
    ) -> InterviewTurn:
        if session.finalized:
            raise ValueError("session is already finalized")
        question = next((q for q in session.questions if q.id == question_id), None)
        if question is None:
            raise ValueError(f"unknown question_id: {question_id}")
        score, feedback = score_answer(question, answer)
        turn = InterviewTurn(
            question=question,
            candidate_answer=answer,
            score=score,
            feedback=feedback,
        )
        session.turns.append(turn)
        # Advance cursor if this question was the current one.
        if (session.cursor < len(session.questions)
                and session.questions[session.cursor].id == question_id):
            session.cursor += 1
        return turn

    def finalize(self, session: InterviewSession) -> SessionReport:
        started = time.perf_counter()
        session.finalized = True
        scored = [t for t in session.turns if t.score is not None]
        if scored:
            overall = sum(t.score.overall for t in scored) / len(scored)
        else:
            overall = 0.0

        strengths, gaps = self._derive_themes(session.turns)
        return SessionReport(
            session_id=session.session_id,
            role=session.role,
            overall_score=round(overall, 3),
            strengths=strengths,
            gaps=gaps,
            turns=session.turns,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    # ─── helpers ────────────────────────────────────────────────────────

    def _derive_themes(self, turns: List[InterviewTurn]) -> tuple[List[str], List[str]]:
        strengths: List[str] = []
        gaps: List[str] = []
        if not turns:
            return strengths, gaps
        # Aggregate per-axis avg.
        axes = ("star_score", "signal_coverage", "clarity", "specificity")
        scored = [t for t in turns if t.score is not None]
        if not scored:
            return strengths, gaps
        avgs = {ax: sum(getattr(t.score, ax) for t in scored) / len(scored) for ax in axes}
        labels = {
            "star_score": "STAR structure",
            "signal_coverage": "rubric coverage",
            "clarity": "clarity / pacing",
            "specificity": "quantified specifics",
        }
        for ax, val in avgs.items():
            if val >= 0.75:
                strengths.append(f"Strong {labels[ax]} (avg {val:.2f})")
            elif val < 0.5:
                gaps.append(f"Weak {labels[ax]} (avg {val:.2f}) — focus here")
        if not strengths:
            strengths.append("Completed the practice loop — keep iterating.")
        if not gaps:
            gaps.append("No major gaps — drill on edge-case curveballs next.")
        return strengths, gaps
