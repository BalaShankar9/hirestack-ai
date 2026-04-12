"""
HistorySubAgent — user application history and past quality patterns.

Queries the database for past applications and quality scores, identifies
patterns, and provides memory-based insights.
"""
from __future__ import annotations

from typing import Any, Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _query_user_history
from ai_engine.client import AIClient


class HistorySubAgent(SubAgent):
    """
    User history analysis:
    - Past application quality scores
    - Common feedback patterns
    - Previous document versions for same company/role
    - Memory recall of past interactions
    """

    def __init__(
        self,
        db: Any = None,
        user_id: str = "",
        ai_client: Optional[AIClient] = None,
    ):
        super().__init__(name="history", ai_client=ai_client)
        self._db = db
        self._user_id = user_id

    async def run(self, context: dict) -> SubAgentResult:
        if not self._db or not self._user_id:
            return SubAgentResult(
                agent_name=self.name,
                data={"history": [], "note": "No DB or user_id — skipped"},
                confidence=0.30,
            )

        try:
            history = await _query_user_history(
                user_id=self._user_id, db=self._db,
            )
        except Exception as exc:
            return SubAgentResult(
                agent_name=self.name,
                error=f"History query failed: {exc}",
            )

        evidence_items: list[dict] = []
        past_scores = history.get("quality_scores", [])
        if past_scores:
            evidence_items.append({
                "fact": f"User has {len(past_scores)} past applications",
                "source": "user_history",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })
            # Compute average
            if isinstance(past_scores, list) and all(isinstance(s, (int, float)) for s in past_scores):
                avg = sum(past_scores) / len(past_scores)
                evidence_items.append({
                    "fact": f"Average past quality score: {avg:.1f}",
                    "source": "user_history",
                    "tier": "DERIVED",
                    "sub_agent": self.name,
                })

        data = {
            "history": history,
            "application_count": len(past_scores) if past_scores else 0,
        }
        confidence = 0.70 if past_scores else 0.30
        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
