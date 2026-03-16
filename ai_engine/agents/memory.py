"""
Agent Memory — per-user learning across pipeline runs.

Stores learned patterns (tone preferences, keyword confirmations, length preferences)
and recalls them using a weighted ranking formula:
  rank = relevance_score * 0.7 + recency_score * 0.3
  where recency_score = 1.0 / (1 + days_since_last_used)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.memory")


class AgentMemory:
    """Per-user, per-agent memory with ranked recall and eviction."""

    MAX_MEMORIES_PER_USER_AGENT = 50

    def __init__(self, db):
        self.db = db

    def _compute_rank(self, relevance_score: float, days_since_last_used: float) -> float:
        recency_score = 1.0 / (1.0 + days_since_last_used)
        return round(relevance_score * 0.7 + recency_score * 0.3, 2)

    def _adjust_relevance(self, current: float, was_useful: bool) -> float:
        if was_useful:
            return min(1.0, round(current + 0.1, 2))
        return max(0.0, round(current - 0.15, 2))

    def store(
        self, user_id: str, agent_type: str, key: str, value: dict
    ) -> None:
        self.db.table("agent_memory").upsert({
            "user_id": user_id,
            "agent_type": agent_type,
            "memory_key": key,
            "memory_value": value,
            "relevance_score": 1.0,
            "usage_count": 1,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,agent_type,memory_key").execute()

        self._evict_if_needed(user_id, agent_type)

    def recall(
        self, user_id: str, agent_type: str, limit: int = 10
    ) -> list[dict]:
        result = (
            self.db.table("agent_memory")
            .select("*")
            .eq("user_id", user_id)
            .eq("agent_type", agent_type)
            .execute()
        )
        memories = result.data or []

        now = datetime.now(timezone.utc)
        for mem in memories:
            last_used = mem.get("last_used_at")
            if isinstance(last_used, str):
                try:
                    last_dt = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
                    days_ago = (now - last_dt).total_seconds() / 86400.0
                except (ValueError, TypeError):
                    days_ago = 30.0
            else:
                days_ago = 30.0
            relevance = float(mem.get("relevance_score", 0.5))
            mem["_rank"] = self._compute_rank(relevance, days_ago)

        memories.sort(key=lambda m: m["_rank"], reverse=True)
        top_memories = memories[:limit]

        for mem in top_memories:
            self.db.table("agent_memory").update({
                "last_used_at": now.isoformat(),
                "usage_count": (mem.get("usage_count") or 0) + 1,
            }).eq("id", mem["id"]).execute()
            mem.pop("_rank", None)

        return top_memories

    def feedback(self, memory_id: str, was_useful: bool) -> None:
        result = (
            self.db.table("agent_memory")
            .select("relevance_score")
            .eq("id", memory_id)
            .execute()
        )
        if not result.data:
            return
        current = float(result.data[0].get("relevance_score", 0.5))
        new_score = self._adjust_relevance(current, was_useful)
        self.db.table("agent_memory").update({
            "relevance_score": new_score,
        }).eq("id", memory_id).execute()

    def _evict_if_needed(self, user_id: str, agent_type: str) -> None:
        result = (
            self.db.table("agent_memory")
            .select("id, relevance_score, last_used_at")
            .eq("user_id", user_id)
            .eq("agent_type", agent_type)
            .order("relevance_score", desc=False)
            .execute()
        )
        memories = result.data or []
        if len(memories) <= self.MAX_MEMORIES_PER_USER_AGENT:
            return

        to_remove = memories[: len(memories) - self.MAX_MEMORIES_PER_USER_AGENT]
        for mem in to_remove:
            self.db.table("agent_memory").delete().eq("id", mem["id"]).execute()
            logger.info("memory_evicted", user_id=user_id, agent_type=agent_type, memory_id=mem["id"])
