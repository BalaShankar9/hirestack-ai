"""Phase C.3 — style outcome scorer unit tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_engine.agents.style_outcome_scorer import (
    OUTCOME_WEIGHTS,
    apply_outcome_to_style_scores,
    preferred_style,
)


def _make_app_resp(cv_variants=None, ps_variants=None):
    class _Resp:
        data = {
            "cv_variants": cv_variants,
            "ps_variants": ps_variants,
        }
    return _Resp()


def _make_sb(app_resp):
    sb = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.maybe_single.return_value = chain
    chain.execute.return_value = app_resp
    sb.table.return_value = chain
    return sb


def _make_memory(existing_value=None):
    mem = MagicMock()
    if existing_value is None:
        mem.arecall = AsyncMock(return_value=[])
    else:
        mem.arecall = AsyncMock(return_value=[
            {"memory_key": "style_outcome_scores", "memory_value": existing_value}
        ])
    mem.astore = AsyncMock(return_value=None)
    return mem


@pytest.mark.asyncio
async def test_callback_increments_locked_cv_style() -> None:
    sb = _make_sb(_make_app_resp(
        cv_variants=[
            {"variant": "concise", "locked": False},
            {"variant": "narrative", "locked": True, "content": "..."},
        ],
    ))
    mem = _make_memory()
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="app-1",
        outcome="callback",
    )
    assert out is not None
    assert out["cv"]["narrative"] == 1.0
    assert out["cv"]["_runs"] == 1
    assert out["ps"] == {}  # no ps_variants
    mem.astore.assert_awaited_once()


@pytest.mark.asyncio
async def test_offer_increments_both_cv_and_ps() -> None:
    sb = _make_sb(_make_app_resp(
        cv_variants=[{"variant": "concise", "locked": True}],
        ps_variants=[{"variant": "narrative", "locked": True}],
    ))
    mem = _make_memory()
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="app-1",
        outcome="offer",
    )
    assert out["cv"]["concise"] == 3.0
    assert out["ps"]["narrative"] == 3.0


@pytest.mark.asyncio
async def test_existing_scores_accumulate() -> None:
    sb = _make_sb(_make_app_resp(
        cv_variants=[{"variant": "concise", "locked": True}],
    ))
    mem = _make_memory(existing_value={
        "cv": {"concise": 2.0, "_runs": 2},
        "ps": {},
    })
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="app-1",
        outcome="callback",
    )
    assert out["cv"]["concise"] == 3.0
    assert out["cv"]["_runs"] == 3


@pytest.mark.asyncio
async def test_rejected_decrements() -> None:
    sb = _make_sb(_make_app_resp(
        cv_variants=[{"variant": "concise", "locked": True}],
    ))
    mem = _make_memory(existing_value={"cv": {"concise": 2.0}})
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="app-1",
        outcome="rejected",
    )
    assert out["cv"]["concise"] == 1.5


@pytest.mark.asyncio
async def test_ghosted_is_noop() -> None:
    sb = _make_sb(_make_app_resp())
    mem = _make_memory()
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="app-1",
        outcome="ghosted",
    )
    assert out is None
    mem.astore.assert_not_called()


@pytest.mark.asyncio
async def test_no_locked_variants_is_noop() -> None:
    sb = _make_sb(_make_app_resp(
        cv_variants=[{"variant": "concise", "locked": False}],
    ))
    mem = _make_memory()
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="app-1",
        outcome="callback",
    )
    assert out is None
    mem.astore.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_outcome_is_noop() -> None:
    sb = _make_sb(_make_app_resp(
        cv_variants=[{"variant": "concise", "locked": True}],
    ))
    mem = _make_memory()
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="app-1",
        outcome="bogus",
    )
    assert out is None


@pytest.mark.asyncio
async def test_unknown_user_is_noop() -> None:
    sb = _make_sb(_make_app_resp())
    mem = _make_memory()
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="unknown",
        application_id="app-1",
        outcome="callback",
    )
    assert out is None


@pytest.mark.asyncio
async def test_application_not_found_is_noop() -> None:
    class _Resp:
        data = None
    sb = _make_sb(_Resp())
    mem = _make_memory()
    out = await apply_outcome_to_style_scores(
        memory=mem,
        sb=sb,
        tables={"applications": "applications"},
        user_id="u1",
        application_id="missing",
        outcome="callback",
    )
    assert out is None


def test_preferred_style_returns_highest() -> None:
    scores = {"cv": {"concise": 2.0, "narrative": 5.0, "_runs": 7}}
    assert preferred_style(scores, "cv") == "narrative"


def test_preferred_style_falls_back_when_empty() -> None:
    assert preferred_style(None, "cv") == "concise"
    assert preferred_style({}, "cv") == "concise"
    assert preferred_style({"cv": {}}, "cv") == "concise"
    assert preferred_style({"cv": {"concise": 0.0, "narrative": 0.0}}, "cv") == "concise"


def test_preferred_style_custom_fallback() -> None:
    assert preferred_style(None, "ps", fallback="narrative") == "narrative"


def test_outcome_weights_immutable_shape() -> None:
    # Snapshot guard against accidental tweaks
    assert OUTCOME_WEIGHTS == {
        "callback": 1.0,
        "offer": 3.0,
        "rejected": -0.5,
        "ghosted": 0.0,
    }
