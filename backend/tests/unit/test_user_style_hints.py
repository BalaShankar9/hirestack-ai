"""Phase C.1 — synthesize_user_style_hints unit tests.

Verifies cold-start safety, relevance threshold, vote agreement, and
prompt rendering."""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_engine.agents.user_style_hints import (
    MIN_RELEVANCE,
    render_style_hints_for_prompt,
    synthesize_user_style_hints,
)


def _mem(value: Dict[str, Any], *, relevance: float = 0.8) -> Dict[str, Any]:
    return {
        "id": f"mem-{id(value)}",
        "memory_value": value,
        "relevance_score": relevance,
    }


def _make_memory(rows: List[Dict[str, Any]]) -> Any:
    m = MagicMock()
    m.arecall = AsyncMock(return_value=rows)
    return m


@pytest.mark.asyncio
async def test_returns_none_when_user_id_unknown() -> None:
    out = await synthesize_user_style_hints(MagicMock(), "unknown")
    assert out is None


@pytest.mark.asyncio
async def test_returns_none_when_memory_empty() -> None:
    out = await synthesize_user_style_hints(_make_memory([]), "user-1")
    assert out is None


@pytest.mark.asyncio
async def test_returns_none_when_below_min_runs() -> None:
    # Only one confirming row → not enough independent signal.
    rows = [_mem({"tone": "concise"}, relevance=0.9)]
    assert await synthesize_user_style_hints(_make_memory(rows), "user-1") is None


@pytest.mark.asyncio
async def test_filters_out_low_relevance_memories() -> None:
    # Two rows but both below the relevance floor → ignored.
    rows = [
        _mem({"tone": "concise"}, relevance=MIN_RELEVANCE - 0.1),
        _mem({"tone": "concise"}, relevance=MIN_RELEVANCE - 0.2),
    ]
    assert await synthesize_user_style_hints(_make_memory(rows), "user-1") is None


@pytest.mark.asyncio
async def test_synthesizes_majority_tone_and_length() -> None:
    rows = [
        _mem({"tone": "concise", "length": "short"}, relevance=0.9),
        _mem({"tone": "concise", "length": "short"}, relevance=0.85),
        _mem({"tone": "narrative"}, relevance=0.7),  # outvoted
    ]
    out = await synthesize_user_style_hints(_make_memory(rows), "user-1")
    assert out is not None
    assert out["tone"] == "concise"
    assert out["length"] == "short"
    assert out["_source"]["memory_rows_considered"] == 3


@pytest.mark.asyncio
async def test_collects_confirmed_keywords_only() -> None:
    rows = [
        _mem({"preferred_keywords": ["python", "kafka", "design"]}, relevance=0.9),
        _mem({"preferred_keywords": ["python", "kafka"]}, relevance=0.8),
        _mem({"preferred_keywords": ["python", "rust"]}, relevance=0.75),
    ]
    out = await synthesize_user_style_hints(_make_memory(rows), "user-1")
    assert out is not None
    assert "python" in out["preferred_keywords"]  # 3 votes
    assert "kafka" in out["preferred_keywords"]   # 2 votes
    # design and rust each have only 1 vote → must be excluded
    assert "design" not in out["preferred_keywords"]
    assert "rust" not in out["preferred_keywords"]


@pytest.mark.asyncio
async def test_renders_empty_when_no_hints() -> None:
    assert render_style_hints_for_prompt(None) == ""
    assert render_style_hints_for_prompt({}) == ""


@pytest.mark.asyncio
async def test_renders_human_readable_block() -> None:
    rendered = render_style_hints_for_prompt({
        "tone": "concise",
        "length": "short",
        "preferred_keywords": ["python", "kafka"],
        "avoid_phrases": ["passionate"],
        "recurring_strengths": ["distributed-systems leadership"],
    })
    assert "Preferred tone: concise" in rendered
    assert "python, kafka" in rendered
    assert "passionate" in rendered
    assert "distributed-systems leadership" in rendered
    assert "Honor these preferences" in rendered


@pytest.mark.asyncio
async def test_recall_failure_returns_none_safely() -> None:
    m = MagicMock()
    m.arecall = AsyncMock(side_effect=RuntimeError("db down"))
    assert await synthesize_user_style_hints(m, "user-1") is None
