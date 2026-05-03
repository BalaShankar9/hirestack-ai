"""Tests for backend/app/services/batch_persister.py (B0.persist.route glue)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest

from app.services.batch_evaluator import RankedBatch, ScoringResult
from app.services.batch_persister import (
    make_batch_id,
    persist_ranked_batch,
)


# ── helpers ──────────────────────────────────────────────────────────


class _RecordingDB:
    """Test-only DB stub recording every create() call."""

    def __init__(self, *, ids: Optional[List[str]] = None,
                 raise_on: Optional[int] = None) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self._ids = list(ids) if ids else None
        self._raise_on = raise_on
        self._counter = 0

    async def create(
        self,
        table: str,
        data: Dict[str, Any],
        doc_id: Optional[str] = None,
    ) -> str:
        if self._raise_on is not None and self._counter == self._raise_on:
            self._counter += 1
            raise RuntimeError("simulated db failure")
        self.calls.append((table, dict(data)))
        self._counter += 1
        if self._ids is not None:
            return self._ids[len(self.calls) - 1]
        return f"app-{len(self.calls):03d}"


def _result(*, canonical_url: str, fit_score: float = 4.0,
            title: str = "t", company: str = "c",
            error: Optional[str] = None) -> ScoringResult:
    return ScoringResult(
        canonical_url=canonical_url,
        fit_score=fit_score,
        error=error,
        title=title,
        company=company,
    )


def _ranked(*results: ScoringResult, below=tuple(), failed=tuple()) -> RankedBatch:
    return RankedBatch(
        ranked=tuple(results),
        below_threshold=tuple(below),
        failed=tuple(failed),
    )


_FIXED_NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
_USER = "user-abc"


# ── make_batch_id ────────────────────────────────────────────────────


class TestMakeBatchId:
    def test_returns_32_char_hex(self) -> None:
        bid = make_batch_id()
        assert len(bid) == 32
        int(bid, 16)  # hex-only

    def test_distinct_calls_different(self) -> None:
        a, b = make_batch_id(), make_batch_id()
        assert a != b


# ── persist_ranked_batch ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestPersistRankedBatch:
    async def test_empty_ranked_returns_empty_no_db_call(self) -> None:
        db = _RecordingDB()
        out = await persist_ranked_batch(
            db=db, ranked=_ranked(), user_id=_USER, batch_id="b1",
        )
        assert out == tuple()
        assert db.calls == []

    async def test_below_and_failed_only_no_db_call(self) -> None:
        db = _RecordingDB()
        out = await persist_ranked_batch(
            db=db,
            ranked=_ranked(
                below=(_result(canonical_url="https://x/b"),),
                failed=(_result(canonical_url="https://x/f", error="ai_error"),),
            ),
            user_id=_USER,
            batch_id="b1",
        )
        assert out == tuple()
        assert db.calls == []

    async def test_inserts_one_row_per_ranked_entry(self) -> None:
        db = _RecordingDB(ids=["id-a", "id-b", "id-c"])
        ranked = _ranked(
            _result(canonical_url="https://x/a"),
            _result(canonical_url="https://x/b"),
            _result(canonical_url="https://x/c"),
        )
        out = await persist_ranked_batch(
            db=db, ranked=ranked, user_id=_USER,
            batch_id="b1", now=_FIXED_NOW,
        )
        assert len(out) == 3
        assert len(db.calls) == 3

    async def test_returns_url_id_pairs_in_input_order(self) -> None:
        db = _RecordingDB(ids=["id-a", "id-b"])
        ranked = _ranked(
            _result(canonical_url="https://x/a"),
            _result(canonical_url="https://x/b"),
        )
        out = await persist_ranked_batch(
            db=db, ranked=ranked, user_id=_USER, batch_id="b1",
        )
        assert out == (
            ("https://x/a", "id-a"),
            ("https://x/b", "id-b"),
        )

    async def test_writes_to_applications_table(self) -> None:
        db = _RecordingDB()
        await persist_ranked_batch(
            db=db,
            ranked=_ranked(_result(canonical_url="https://x/a")),
            user_id=_USER, batch_id="b1",
        )
        assert db.calls[0][0] == "applications"

    async def test_row_carries_user_id_and_batch_id(self) -> None:
        db = _RecordingDB()
        await persist_ranked_batch(
            db=db,
            ranked=_ranked(_result(canonical_url="https://x/a")),
            user_id="user-7", batch_id="batch-77",
        )
        row = db.calls[0][1]
        assert row["user_id"] == "user-7"
        assert row["confirmed_facts"]["batch_id"] == "batch-77"

    async def test_row_status_is_draft(self) -> None:
        db = _RecordingDB()
        await persist_ranked_batch(
            db=db,
            ranked=_ranked(_result(canonical_url="https://x/a")),
            user_id=_USER, batch_id="b1",
        )
        assert db.calls[0][1]["status"] == "draft"

    async def test_row_carries_fit_score(self) -> None:
        db = _RecordingDB()
        await persist_ranked_batch(
            db=db,
            ranked=_ranked(_result(canonical_url="https://x/a", fit_score=4.7)),
            user_id=_USER, batch_id="b1",
        )
        assert db.calls[0][1]["scores"]["fit"] == 4.7

    async def test_row_carries_dedup_key(self) -> None:
        db = _RecordingDB()
        await persist_ranked_batch(
            db=db,
            ranked=_ranked(_result(canonical_url="https://x/a")),
            user_id=_USER, batch_id="b1",
        )
        dk = db.calls[0][1]["confirmed_facts"]["dedup_key"]
        assert isinstance(dk, str)
        assert len(dk) == 32

    async def test_no_batch_id_generates_one(self) -> None:
        db = _RecordingDB()
        await persist_ranked_batch(
            db=db,
            ranked=_ranked(_result(canonical_url="https://x/a")),
            user_id=_USER,
        )
        bid = db.calls[0][1]["confirmed_facts"]["batch_id"]
        assert len(bid) == 32

    async def test_db_failure_propagates_after_partial_insert(self) -> None:
        # Sequential inserts: row 0 succeeds, row 1 raises, row 2 never reached.
        db = _RecordingDB(raise_on=1)
        with pytest.raises(RuntimeError, match="simulated db failure"):
            await persist_ranked_batch(
                db=db,
                ranked=_ranked(
                    _result(canonical_url="https://x/a"),
                    _result(canonical_url="https://x/b"),
                    _result(canonical_url="https://x/c"),
                ),
                user_id=_USER, batch_id="b1",
            )
        # Only the first row landed before the raise.
        assert len(db.calls) == 1
