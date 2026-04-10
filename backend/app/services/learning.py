"""
Micro-Learning Service
Daily challenges, streak tracking, and skill progression (Supabase)
"""
from typing import Optional, Dict, Any, List
from datetime import date, timedelta
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import get_ai_client
from ai_engine.chains.learning_challenge import LearningChallengeChain

logger = structlog.get_logger()


class LearningService:
    """Service for micro-learning challenges and streak tracking."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = get_ai_client()

    async def get_or_create_streak(self, user_id: str) -> Dict[str, Any]:
        """Get or create a user's learning streak record."""
        streaks = await self.db.query(
            TABLES["learning_streaks"],
            filters=[("user_id", "==", user_id)],
            limit=1,
        )
        if streaks:
            return streaks[0]

        record = {
            "user_id": user_id,
            "current_streak": 0,
            "longest_streak": 0,
            "total_points": 0,
            "total_challenges": 0,
            "correct_challenges": 0,
            "level": 1,
            "skills_mastered": [],
        }
        doc_id = await self.db.create(TABLES["learning_streaks"], record)
        saved = await self.db.get(TABLES["learning_streaks"], doc_id)
        return saved or {**record, "id": doc_id}

    async def generate_daily_challenges(
        self,
        user_id: str,
        skills: Optional[List[str]] = None,
        count: int = 5,
        job_context: str = "software engineering",
    ) -> Dict[str, Any]:
        """Generate a daily set of learning challenges."""
        # If no skills specified, derive from user's gap reports
        if not skills:
            gaps = await self.db.query(
                TABLES["gap_reports"],
                filters=[("user_id", "==", user_id)],
                order_by="created_at",
                order_direction="DESCENDING",
                limit=1,
            )
            if gaps and gaps[0].get("skill_gaps"):
                skill_gaps = gaps[0]["skill_gaps"]
                if isinstance(skill_gaps, list):
                    skills = [g.get("skill", "") for g in skill_gaps[:8] if g.get("skill")]

        if not skills:
            skills = ["Problem Solving", "Communication", "Technical Skills"]

        # Determine difficulty from streak
        streak = await self.get_or_create_streak(user_id)
        level = streak.get("level", 1)
        if level <= 3:
            difficulty = "easy"
        elif level <= 7:
            difficulty = "medium"
        else:
            difficulty = "hard"

        chain = LearningChallengeChain(self.ai_client)
        result = await chain.generate_daily_set(
            skills=skills,
            difficulty=difficulty,
            count=count,
            job_context=job_context,
        )

        # Save challenges
        saved = []
        for challenge in result.get("challenges", []):
            record = {
                "user_id": user_id,
                "skill": challenge.get("skill", ""),
                "difficulty": challenge.get("difficulty", difficulty),
                "challenge_type": challenge.get("challenge_type", "quiz"),
                "question": challenge.get("question", ""),
                "options": challenge.get("options", []),
                "correct_answer": challenge.get("correct_answer", ""),
                "explanation": challenge.get("explanation", ""),
                "points_earned": 0,
                "streak_day": streak.get("current_streak", 0) + 1,
            }
            doc_id = await self.db.create(TABLES["learning_challenges"], record)
            saved.append({**record, "id": doc_id})

        logger.info("daily_challenges_generated", count=len(saved), user_id=user_id)
        return {
            "challenges": saved,
            "theme": result.get("theme", "Daily Challenge"),
            "streak": streak,
        }

    async def submit_answer(
        self,
        user_id: str,
        challenge_id: str,
        user_answer: str,
    ) -> Dict[str, Any]:
        """Submit an answer to a challenge and update streak."""
        challenge = await self.db.get(TABLES["learning_challenges"], challenge_id)
        if not challenge or challenge.get("user_id") != user_id:
            raise ValueError("Challenge not found")

        if challenge.get("completed_at"):
            raise ValueError("Challenge already completed")

        is_correct = user_answer.strip().lower() == (challenge.get("correct_answer", "").strip().lower())
        from datetime import datetime, timezone
        points = challenge.get("points_earned", 10) if is_correct else 0

        await self.db.update(TABLES["learning_challenges"], challenge_id, {
            "user_answer": user_answer,
            "is_correct": is_correct,
            "points_earned": points,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        # Update streak
        streak = await self.get_or_create_streak(user_id)
        today = date.today()
        last_date = streak.get("last_challenge_date")

        if last_date:
            if isinstance(last_date, str):
                last_date = date.fromisoformat(last_date)
            days_diff = (today - last_date).days
        else:
            days_diff = 999

        if days_diff == 0:
            new_streak = streak.get("current_streak", 0)
        elif days_diff == 1:
            new_streak = streak.get("current_streak", 0) + 1
        else:
            new_streak = 1

        total_points = streak.get("total_points", 0) + points
        total_challenges = streak.get("total_challenges", 0) + 1
        correct_challenges = streak.get("correct_challenges", 0) + (1 if is_correct else 0)
        level = 1 + total_points // 100

        await self.db.update(TABLES["learning_streaks"], streak["id"], {
            "current_streak": new_streak,
            "longest_streak": max(new_streak, streak.get("longest_streak", 0)),
            "total_points": total_points,
            "total_challenges": total_challenges,
            "correct_challenges": correct_challenges,
            "level": level,
            "last_challenge_date": today.isoformat(),
        })

        return {
            "is_correct": is_correct,
            "correct_answer": challenge.get("correct_answer", ""),
            "explanation": challenge.get("explanation", ""),
            "points_earned": points,
            "streak": {
                "current": new_streak,
                "longest": max(new_streak, streak.get("longest_streak", 0)),
                "total_points": total_points,
                "level": level,
            },
        }

    async def get_today_challenges(self, user_id: str) -> List[Dict[str, Any]]:
        """Get today's challenges for a user."""
        today = date.today().isoformat()
        # Get challenges created today
        all_challenges = await self.db.query(
            TABLES["learning_challenges"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=20,
        )
        return [c for c in all_challenges if c.get("created_at", "").startswith(today)]

    async def get_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get challenge history."""
        return await self.db.query(
            TABLES["learning_challenges"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )
