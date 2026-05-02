"""Tests for backend/app/api/routes/insights.py (A2.api)."""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api.routes import insights as insights_route
from app.api.routes.insights import (
    _coerce_fit_score,
    _coerce_optional_str,
    _serialize,
    hydrate_records,
    serialize_blocker_report,
    serialize_pattern_insights,
)
from app.services.insights_blockers import (
    BlockerReport,
    Recommendation,
    classify_blockers,
)
from app.services.pattern_insights import (
    ApplicationRecord,
    InsufficientData,
    PatternInsights,
    compute_pattern_insights,
)


# ───────────────────── _coerce_fit_score (pure) ────────────────────────


class TestCoerceFitScore:
    def test_rescales_db_100_to_core_5(self) -> None:
        assert _coerce_fit_score({"overall": 80}) == pytest.approx(4.0)
        assert _coerce_fit_score({"overall": 100}) == pytest.approx(5.0)
        assert _coerce_fit_score({"overall": 0}) == pytest.approx(0.0)

    def test_accepts_float(self) -> None:
        assert _coerce_fit_score({"overall": 72.5}) == pytest.approx(3.625)

    def test_clamps_above_100(self) -> None:
        # Bad data shouldn't poison the bucketing.
        assert _coerce_fit_score({"overall": 500}) == 5.0

    def test_clamps_below_zero(self) -> None:
        assert _coerce_fit_score({"overall": -10}) == 0.0

    def test_missing_overall_returns_none(self) -> None:
        assert _coerce_fit_score({}) is None
        assert _coerce_fit_score({"other": 50}) is None

    def test_non_dict_returns_none(self) -> None:
        assert _coerce_fit_score(None) is None
        assert _coerce_fit_score("80") is None
        assert _coerce_fit_score(80) is None

    def test_non_numeric_overall_returns_none(self) -> None:
        assert _coerce_fit_score({"overall": "high"}) is None
        assert _coerce_fit_score({"overall": None}) is None


# ───────────────────── _coerce_optional_str ────────────────────────────


class TestCoerceOptionalStr:
    def test_strips_and_returns(self) -> None:
        assert _coerce_optional_str("  hello  ") == "hello"

    def test_blank_returns_none(self) -> None:
        assert _coerce_optional_str("") is None
        assert _coerce_optional_str("   ") is None

    def test_non_string_returns_none(self) -> None:
        assert _coerce_optional_str(None) is None
        assert _coerce_optional_str(42) is None


# ───────────────────── hydrate_records (pure) ──────────────────────────


class TestHydrateRecords:
    def test_basic_split(self) -> None:
        rows = [{
            "id": "a1",
            "status": "responded",
            "scores": {"overall": 80},
            "archetype_label": "big_tech_ic",
            "rejection_reason": "ghosted",
        }]
        pat, blk = hydrate_records(rows)
        assert len(pat) == 1
        assert pat[0] == ApplicationRecord(
            application_id="a1",
            status="responded",
            fit_score=pytest.approx(4.0),  # type: ignore[arg-type]
            archetype_label="big_tech_ic",
        )
        assert len(blk) == 1
        assert blk[0].application_id == "a1"
        assert blk[0].status == "responded"
        assert blk[0].rejection_reason == "ghosted"

    def test_falls_back_to_application_id_field(self) -> None:
        rows = [{"application_id": "alt-1", "status": "applied"}]
        pat, _ = hydrate_records(rows)
        assert pat[0].application_id == "alt-1"

    def test_skips_rows_with_no_id(self) -> None:
        rows = [
            {"status": "applied"},                 # no id at all
            {"id": "", "status": "applied"},       # empty id
            {"id": "ok", "status": "applied"},
        ]
        pat, blk = hydrate_records(rows)
        assert len(pat) == 1 and pat[0].application_id == "ok"
        assert len(blk) == 1

    def test_skips_rows_with_blank_status(self) -> None:
        rows = [
            {"id": "a1", "status": ""},
            {"id": "a2", "status": "   "},
            {"id": "a3", "status": "applied"},
        ]
        pat, _ = hydrate_records(rows)
        assert [r.application_id for r in pat] == ["a3"]

    def test_missing_optional_fields_become_none(self) -> None:
        rows = [{"id": "a1", "status": "applied"}]
        pat, blk = hydrate_records(rows)
        assert pat[0].fit_score is None
        assert pat[0].archetype_label is None
        assert blk[0].rejection_reason is None

    def test_blank_archetype_label_becomes_none(self) -> None:
        rows = [{"id": "a1", "status": "applied", "archetype_label": "   "}]
        pat, _ = hydrate_records(rows)
        assert pat[0].archetype_label is None

    def test_empty_input(self) -> None:
        pat, blk = hydrate_records([])
        assert pat == [] and blk == []


# ───────────────────── _serialize ──────────────────────────────────────


class TestSerialize:
    def test_passes_primitives(self) -> None:
        assert _serialize(None) is None
        assert _serialize(1) == 1
        assert _serialize("x") == "x"
        assert _serialize(True) is True

    def test_tuple_becomes_list(self) -> None:
        assert _serialize((1, 2, 3)) == [1, 2, 3]

    def test_dataclass_to_dict(self) -> None:
        rec = ApplicationRecord(
            application_id="a1", status="applied", fit_score=3.5,
            archetype_label="big_tech_ic",
        )
        out = _serialize(rec)
        assert out == {
            "application_id": "a1",
            "status": "applied",
            "fit_score": 3.5,
            "archetype_label": "big_tech_ic",
        }

    def test_insufficient_data_tagged_with_kind(self) -> None:
        ins = InsufficientData(have=2, need=5)
        out = _serialize(ins)
        assert out["kind"] == "insufficient_data"
        assert out["have"] == 2
        assert out["need"] == 5

    def test_nested_insufficient_data_inside_dataclass_tagged(self) -> None:
        # Simulate a PatternInsights where a section is InsufficientData
        empty = compute_pattern_insights([])
        out = serialize_pattern_insights(empty)
        # Each section should be tagged so the UI can branch.
        assert out["funnel"]["kind"] == "insufficient_data"
        assert out["score_outcome"]["kind"] == "insufficient_data"
        assert out["archetype"]["kind"] == "insufficient_data"


# ───────────────────── End-to-end serialization ────────────────────────


def _records_with_signal(n_offers: int = 3, n_rejected: int = 4) -> List[ApplicationRecord]:
    out: List[ApplicationRecord] = []
    for i in range(n_offers):
        out.append(ApplicationRecord(
            application_id=f"o-{i}", status="offer", fit_score=4.5,
            archetype_label="big_tech_ic",
        ))
    for i in range(n_rejected):
        out.append(ApplicationRecord(
            application_id=f"r-{i}", status="rejected", fit_score=1.0,
            archetype_label="enterprise_saas",
        ))
    return out


def test_serialize_pattern_insights_with_real_data() -> None:
    insights = compute_pattern_insights(_records_with_signal())
    out = serialize_pattern_insights(insights)
    # Should have rendered sections (not InsufficientData), since outcomes ≥ 5.
    assert "stages" in out["funnel"]
    assert isinstance(out["funnel"]["stages"], list)
    # total_outcomes should be int, not tuple.
    assert isinstance(out["funnel"]["total_outcomes"], int)
    assert isinstance(out["total_applications"], int)


def test_serialize_blocker_report_with_real_data() -> None:
    from app.services.insights_blockers import RejectedApplication
    rejected = [
        RejectedApplication(application_id=f"r-{i}", status="rejected",
                            rejection_reason="Looking for someone with more experience")
        for i in range(6)
    ]
    report = classify_blockers(rejected)
    out = serialize_blocker_report(report)
    assert isinstance(out["counts"], list)
    assert out["sufficient"] is True


# ───────────────────── Route integration ───────────────────────────────


_FAKE_USER = {"id": "user-1", "email": "u@example.com"}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = insights_route.limiter
    app.include_router(insights_route.router, prefix="/api")
    app.dependency_overrides[api_deps.get_current_user] = lambda: _FAKE_USER
    return app


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    # Reset slowapi limiter so 30/min cap doesn't bleed across tests.
    try:
        insights_route.limiter.reset()
    except Exception:
        pass

    return TestClient(_build_app())


def _patch_db(monkeypatch, rows: List[Dict[str, Any]]) -> None:
    """Replace get_db() with a fake DB returning ``rows`` from .query()."""
    fake_db = type("FakeDB", (), {})()
    fake_db.query = AsyncMock(return_value=rows)
    monkeypatch.setattr(insights_route, "get_db", lambda: fake_db)


class TestInsightsRoute:
    def test_empty_user_returns_insufficient_data_sections(
        self, client: TestClient, monkeypatch,
    ) -> None:
        _patch_db(monkeypatch, [])
        resp = client.get("/api/insights")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_applications"] == 0
        assert body["patterns"]["funnel"]["kind"] == "insufficient_data"
        assert body["recommendations"] == []

    def test_user_with_signal_renders_sections(
        self, client: TestClient, monkeypatch,
    ) -> None:
        rows = [
            {
                "id": f"o-{i}",
                "status": "offer",
                "scores": {"overall": 90},
                "archetype_label": "big_tech_ic",
            }
            for i in range(3)
        ] + [
            {
                "id": f"r-{i}",
                "status": "rejected",
                "scores": {"overall": 20},
                "archetype_label": "enterprise_saas",
                "rejection_reason": "Looking for someone more senior with 10+ years experience",
            }
            for i in range(5)
        ]
        _patch_db(monkeypatch, rows)
        resp = client.get("/api/insights")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_applications"] == 8
        # Funnel rendered (≥5 applies).
        assert "stages" in body["patterns"]["funnel"]
        # Blockers classified.
        assert body["blockers"]["sufficient"] is True
        # Recommendations is a list (may be empty depending on thresholds).
        assert isinstance(body["recommendations"], list)

    def test_response_is_json_serializable_no_tuples_or_dataclasses(
        self, client: TestClient, monkeypatch,
    ) -> None:
        rows = [
            {"id": f"a-{i}", "status": "applied"} for i in range(6)
        ]
        _patch_db(monkeypatch, rows)
        resp = client.get("/api/insights")
        assert resp.status_code == 200
        # If any tuple / dataclass leaked, .json() above would have raised.
        body = resp.json()
        # Patterns funnel stages should be a list of dicts.
        funnel = body["patterns"]["funnel"]
        if "stages" in funnel:
            for stage in funnel["stages"]:
                assert isinstance(stage, dict)
                assert "name" in stage and "count" in stage

    def test_route_passes_user_id_to_db(
        self, client: TestClient, monkeypatch,
    ) -> None:
        captured = {}
        fake_db = type("FakeDB", (), {})()

        async def _query(table, filters=None, limit=None, **_kw):
            captured["table"] = table
            captured["filters"] = filters
            captured["limit"] = limit
            return []

        fake_db.query = _query
        monkeypatch.setattr(insights_route, "get_db", lambda: fake_db)
        resp = client.get("/api/insights")
        assert resp.status_code == 200
        assert captured["filters"] == [("user_id", "==", "user-1")]
        assert captured["limit"] == 500
