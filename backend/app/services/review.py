"""
Collaborative Review Service
Shareable links, inline commenting, and AI feedback summarizer (Supabase)
"""
from typing import Optional, Dict, Any, List
import secrets
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from ai_engine.client import get_ai_client

logger = structlog.get_logger()


class ReviewService:
    """Service for collaborative document review."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.ai_client = get_ai_client()

    async def create_review_session(
        self,
        user_id: str,
        application_id: str,
        document_type: str = "cv",
        reviewer_name: str = "",
        expires_hours: int = 168,  # 7 days
    ) -> Dict[str, Any]:
        """Create a shareable review session."""
        from datetime import datetime, timedelta, timezone

        share_token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()

        record = {
            "user_id": user_id,
            "application_id": application_id,
            "document_type": document_type,
            "share_token": share_token,
            "share_url": f"/review/{share_token}",
            "expires_at": expires_at,
            "is_active": True,
            "reviewer_name": reviewer_name,
        }

        doc_id = await self.db.create(TABLES["review_sessions"], record)
        logger.info("review_session_created", session_id=doc_id)
        return await self.db.get(TABLES["review_sessions"], doc_id)

    async def get_session_by_token(self, share_token: str) -> Optional[Dict[str, Any]]:
        """Get a review session by its share token (public access)."""
        results = await self.db.query(
            TABLES["review_sessions"],
            filters=[("share_token", "==", share_token), ("is_active", "==", True)],
            limit=1,
        )
        if not results:
            return None

        session = results[0]
        # Check expiry
        from datetime import datetime, timezone
        if session.get("expires_at"):
            expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                return None
        return session

    async def add_comment(
        self,
        session_id: str,
        reviewer_name: str,
        comment_text: str,
        selection_start: Optional[int] = None,
        selection_end: Optional[int] = None,
        section: str = "",
    ) -> Dict[str, Any]:
        """Add a comment to a review session."""
        # Verify session is active and not expired
        from datetime import datetime, timezone
        session = await self.db.get(TABLES["review_sessions"], session_id)
        if not session or not session.get("is_active"):
            raise ValueError("Review session is not active")
        if session.get("expires_at"):
            expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                raise ValueError("Review session has expired")

        # Detect sentiment using simple heuristics
        lower = comment_text.lower()
        if any(w in lower for w in ("great", "excellent", "good", "well done", "strong", "impressive")):
            sentiment = "positive"
        elif any(w in lower for w in ("suggest", "consider", "could", "try", "maybe", "perhaps")):
            sentiment = "suggestion"
        elif any(w in lower for w in ("weak", "poor", "bad", "wrong", "error", "missing", "lacks")):
            sentiment = "negative"
        else:
            sentiment = "neutral"

        record = {
            "session_id": session_id,
            "reviewer_name": reviewer_name,
            "comment_text": comment_text,
            "selection_start": selection_start,
            "selection_end": selection_end,
            "section": section,
            "sentiment": sentiment,
            "is_resolved": False,
        }

        doc_id = await self.db.create(TABLES["review_comments"], record)
        return {**record, "id": doc_id}

    async def get_comments(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all comments for a review session."""
        return await self.db.query(
            TABLES["review_comments"],
            filters=[("session_id", "==", session_id)],
            order_by="created_at",
        )

    async def summarize_feedback(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """Use AI to summarize all review comments (owner only)."""
        # Verify session belongs to the requesting user
        session = await self.db.get(TABLES["review_sessions"], session_id)
        if not session or session.get("user_id") != user_id:
            return {"summary": "Session not found.", "themes": [], "action_items": []}

        comments = await self.get_comments(session_id)
        if not comments:
            return {"summary": "No comments yet.", "themes": [], "action_items": []}

        comment_text = "\n".join(
            f"[{c.get('sentiment', 'neutral')}] {c.get('reviewer_name', 'Anonymous')}: {c['comment_text']}"
            for c in comments
        )

        result = await self.ai_client.complete_json(
            prompt=f"""Summarize these review comments on a professional document.

COMMENTS:
{comment_text}

Return ONLY valid JSON:
```json
{{
    "summary": "2-3 sentence overall summary",
    "themes": ["Recurring theme 1", "Theme 2"],
    "action_items": ["Specific action 1", "Action 2"],
    "positive_highlights": ["What reviewers liked"],
    "areas_for_improvement": ["What needs work"],
    "sentiment_breakdown": {{ "positive": 3, "neutral": 2, "negative": 1, "suggestion": 4 }}
}}
```""",
            system="You are an expert at synthesizing feedback into actionable insights.",
            max_tokens=1024,
        )
        return result

    async def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all review sessions for a user."""
        return await self.db.query(
            TABLES["review_sessions"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )

    async def deactivate_session(self, session_id: str, user_id: str) -> bool:
        """Deactivate a review session."""
        session = await self.db.get(TABLES["review_sessions"], session_id)
        if not session or session.get("user_id") != user_id:
            return False
        await self.db.update(TABLES["review_sessions"], session_id, {"is_active": False})
        return True
