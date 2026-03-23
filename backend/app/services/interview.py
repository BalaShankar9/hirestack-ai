"""
Interview Simulator Service
Manages interview practice sessions, question generation, and answer evaluation (Supabase)
"""
from typing import Optional, Dict, Any, List
import json
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import get_ai_client
from ai_engine.chains.interview_simulator import InterviewSimulatorChain

logger = structlog.get_logger()


class InterviewService:
    """Service for interview simulation sessions."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = get_ai_client()

    async def start_session(
        self,
        user_id: str,
        job_title: str,
        company: str = "",
        jd_text: str = "",
        interview_type: str = "mixed",
        difficulty: str = "medium",
        question_count: int = 8,
        application_id: Optional[str] = None,
        profile_summary: str = "",
        gap_summary: str = "",
    ) -> Dict[str, Any]:
        """Start a new interview session with generated questions."""
        chain = InterviewSimulatorChain(self.ai_client)
        result = await chain.generate_questions(
            job_title=job_title,
            company=company,
            jd_text=jd_text,
            interview_type=interview_type,
            difficulty=difficulty,
            count=question_count,
            profile_summary=profile_summary,
            gap_summary=gap_summary,
        )

        questions = result.get("questions", [])
        record = {
            "user_id": user_id,
            "application_id": application_id,
            "job_title": job_title,
            "company": company,
            "interview_type": interview_type,
            "difficulty": difficulty,
            "questions": questions,
            "status": "in_progress",
        }

        doc_id = await self.db.create(TABLES["interview_sessions"], record)
        logger.info("interview_session_started", session_id=doc_id, questions=len(questions))
        return await self.db.get(TABLES["interview_sessions"], doc_id)

    async def submit_answer(
        self,
        user_id: str,
        session_id: str,
        question_index: int,
        answer_text: str,
        duration_seconds: int = 0,
    ) -> Dict[str, Any]:
        """Submit and evaluate an answer for a question."""
        session = await self.db.get(TABLES["interview_sessions"], session_id)
        if not session or session.get("user_id") != user_id:
            raise ValueError("Session not found")

        questions = session.get("questions", [])
        if question_index >= len(questions):
            raise ValueError("Invalid question index")

        question = questions[question_index]
        chain = InterviewSimulatorChain(self.ai_client)
        evaluation = await chain.evaluate_answer(
            question=question.get("text", ""),
            question_type=question.get("type", "behavioral"),
            skill_tested=question.get("skill_tested", ""),
            answer=answer_text,
            ideal_points=question.get("ideal_answer_points", []),
        )

        record = {
            "user_id": user_id,
            "session_id": session_id,
            "question_index": question_index,
            "question_text": question.get("text", ""),
            "question_type": question.get("type", ""),
            "answer_text": answer_text,
            "score": evaluation.get("score", 0),
            "star_scores": evaluation.get("star_scores", {}),
            "feedback": evaluation.get("feedback", ""),
            "strengths": evaluation.get("strengths", []),
            "improvements": evaluation.get("improvements", []),
            "model_answer": evaluation.get("model_answer", ""),
            "duration_seconds": duration_seconds,
        }

        doc_id = await self.db.create(TABLES["interview_answers"], record)
        logger.info("answer_evaluated", answer_id=doc_id, score=record["score"])
        return {**record, "id": doc_id}

    async def complete_session(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """Complete a session and generate overall feedback."""
        session = await self.db.get(TABLES["interview_sessions"], session_id)
        if not session or session.get("user_id") != user_id:
            raise ValueError("Session not found")

        answers = await self.db.query(
            TABLES["interview_answers"],
            filters=[("session_id", "==", session_id)],
            order_by="question_index",
        )

        # Build Q&A summary for AI
        qa_lines = []
        total_score = 0
        for a in answers:
            qa_lines.append(f"Q{a['question_index']+1}: {a['question_text']}")
            qa_lines.append(f"Score: {a.get('score', 0)}/100")
            qa_lines.append(f"Answer excerpt: {a['answer_text'][:200]}")
            qa_lines.append("---")
            total_score += a.get("score", 0)

        chain = InterviewSimulatorChain(self.ai_client)
        summary = await chain.summarize_session(
            job_title=session.get("job_title", ""),
            company=session.get("company", ""),
            interview_type=session.get("interview_type", "mixed"),
            qa_summary="\n".join(qa_lines),
        )

        avg_score = total_score / len(answers) if answers else 0
        await self.db.update(TABLES["interview_sessions"], session_id, {
            "overall_score": summary.get("overall_score", avg_score),
            "overall_feedback": summary.get("overall_feedback", ""),
            "strengths": summary.get("strengths", []),
            "improvements": summary.get("improvements", []),
            "status": "completed",
            "duration_seconds": sum(a.get("duration_seconds", 0) for a in answers),
        })

        return await self.db.get(TABLES["interview_sessions"], session_id)

    async def get_session(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a session with its answers."""
        session = await self.db.get(TABLES["interview_sessions"], session_id)
        if not session or session.get("user_id") != user_id:
            return None
        answers = await self.db.query(
            TABLES["interview_answers"],
            filters=[("session_id", "==", session_id)],
            order_by="question_index",
        )
        session["answers"] = answers
        return session

    async def get_user_sessions(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent sessions for user."""
        return await self.db.query(
            TABLES["interview_sessions"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )
