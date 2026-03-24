"""
Interview Simulator Service
Handles interview session management and AI-powered question generation
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import structlog

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from ai_engine.client import AIClient
from ai_engine.chains.interview_simulator import InterviewSimulatorChain

logger = structlog.get_logger()

SESSION_TIMEOUT_HOURS = 2


class InterviewService:
    """Service for interview simulation using Firestore."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.ai_client = AIClient()

    async def create_session(
        self,
        user_id: str,
        job_title: str,
        company: str = "",
        jd_text: str = "",
        profile_summary: str = "",
        interview_type: str = "mixed",
        question_count: int = 10,
    ) -> Dict[str, Any]:
        """Create a new interview session with generated questions."""
        chain = InterviewSimulatorChain(self.ai_client)
        questions_data = await chain.generate_questions(
            job_title=job_title,
            company=company,
            jd_summary=jd_text[:3000],
            profile_summary=profile_summary,
            interview_type=interview_type,
            question_count=question_count,
        )

        now = datetime.now(timezone.utc)
        record = {
            "user_id": user_id,
            "job_title": job_title,
            "company": company,
            "interview_type": interview_type,
            "questions": questions_data.get("questions", []),
            "interview_focus": questions_data.get("interview_focus", ""),
            "preparation_tips": questions_data.get("preparation_tips", []),
            "answers": [],
            "scores": [],
            "status": "active",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=SESSION_TIMEOUT_HOURS)).isoformat(),
        }

        doc_id = await self.db.create(COLLECTIONS.get("interview_sessions", "interview_sessions"), record)
        logger.info("interview_session_created", session_id=doc_id)
        return await self.db.get(COLLECTIONS.get("interview_sessions", "interview_sessions"), doc_id)

    async def submit_answer(
        self,
        session_id: str,
        user_id: str,
        question_id: str,
        answer: str,
    ) -> Dict[str, Any]:
        """Submit an answer and get feedback."""
        session = await self._get_active_session(session_id, user_id)

        # Find the question
        question_obj = next(
            (q for q in session.get("questions", []) if q.get("id") == question_id),
            None,
        )
        if not question_obj:
            raise ValueError(f"Question {question_id} not found in session")

        chain = InterviewSimulatorChain(self.ai_client)
        evaluation = await chain.evaluate_answer(
            question=question_obj.get("question", ""),
            answer=answer,
            role_context=f"{session.get('job_title', '')} at {session.get('company', '')}",
        )

        # Append to session answers
        answers = session.get("answers", [])
        answers.append({
            "question_id": question_id,
            "answer": answer,
            "evaluation": evaluation,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        })
        scores = session.get("scores", [])
        scores.append(evaluation.get("score", 0))

        await self.db.update(
            COLLECTIONS.get("interview_sessions", "interview_sessions"),
            session_id,
            {"answers": answers, "scores": scores},
        )
        return evaluation

    async def complete_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """Mark a session as completed."""
        session = await self._get_active_session(session_id, user_id)
        scores = session.get("scores", [])
        avg_score = int(sum(scores) / len(scores)) if scores else 0
        await self.db.update(
            COLLECTIONS.get("interview_sessions", "interview_sessions"),
            session_id,
            {"status": "completed", "average_score": avg_score},
        )
        return await self.db.get(
            COLLECTIONS.get("interview_sessions", "interview_sessions"), session_id
        )

    async def get_user_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.db.query(
            COLLECTIONS.get("interview_sessions", "interview_sessions"),
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )

    async def get_session(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        session = await self.db.get(
            COLLECTIONS.get("interview_sessions", "interview_sessions"), session_id
        )
        if session and session.get("user_id") == user_id:
            return session
        return None

    async def _get_active_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """Get a session and validate it's active and not expired."""
        session = await self.get_session(session_id, user_id)
        if not session:
            raise ValueError("Session not found")

        if session.get("status") != "active":
            raise ValueError(f"Session is {session.get('status')}, not active")

        # Check expiry
        expires_at_str = session.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expires_at:
                    await self.db.update(
                        COLLECTIONS.get("interview_sessions", "interview_sessions"),
                        session_id,
                        {"status": "expired"},
                    )
                    raise ValueError("Session has expired")
            except (ValueError, TypeError) as exc:
                if "expired" in str(exc):
                    raise
                logger.warning("invalid_expires_at", session_id=session_id)

        return session
