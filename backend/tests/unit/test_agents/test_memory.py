# backend/tests/unit/test_agents/test_memory.py
import pytest
from unittest.mock import MagicMock
from ai_engine.agents.memory import AgentMemory


@pytest.fixture
def mock_db():
    """Supabase client is synchronous — all .execute() calls return MagicMock."""
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.select = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.update = MagicMock(return_value=db)
    db.delete = MagicMock(return_value=db)
    db.upsert = MagicMock(return_value=db)
    db.eq = MagicMock(return_value=db)
    db.order = MagicMock(return_value=db)
    db.limit = MagicMock(return_value=db)
    db.execute = MagicMock(return_value=MagicMock(data=[]))
    return db


def test_ranking_formula():
    """rank = relevance_score * 0.7 + recency_score * 0.3"""
    mem = AgentMemory.__new__(AgentMemory)
    # Fresh memory (0 days ago) with relevance 1.0
    rank = mem._compute_rank(relevance_score=1.0, days_since_last_used=0)
    assert rank == pytest.approx(1.0)  # 1.0*0.7 + 1.0*0.3

    # Old memory (9 days ago) with relevance 1.0
    rank = mem._compute_rank(relevance_score=1.0, days_since_last_used=9)
    assert rank == pytest.approx(0.73)  # 1.0*0.7 + 0.1*0.3

    # Fresh memory with low relevance
    rank = mem._compute_rank(relevance_score=0.0, days_since_last_used=0)
    assert rank == pytest.approx(0.3)  # 0.0*0.7 + 1.0*0.3


def test_feedback_positive_caps_at_1():
    mem = AgentMemory.__new__(AgentMemory)
    new_score = mem._adjust_relevance(0.95, was_useful=True)
    assert new_score == 1.0


def test_feedback_negative_floors_at_0():
    mem = AgentMemory.__new__(AgentMemory)
    new_score = mem._adjust_relevance(0.1, was_useful=False)
    assert new_score == 0.0


def test_max_memories_constant():
    assert AgentMemory.MAX_MEMORIES_PER_USER_AGENT == 50
