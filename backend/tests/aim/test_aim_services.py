"""AIM \u2014 unit tests for the assignment + section services and the orchestration chain."""
from __future__ import annotations

from typing import Any

import pytest
from unittest.mock import AsyncMock, patch


class FakeDB:
    """In-memory fake for SupabaseDB used by the AIM services."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}
        self._counter = 0

    async def create(self, table, data, doc_id=None):
        self._counter += 1
        new_id = doc_id or f"row-{self._counter}"
        row = {**data, "id": new_id}
        self._store.setdefault(table, []).append(row)
        return new_id

    async def get(self, table, doc_id):
        for r in self._store.get(table, []):
            if r.get("id") == doc_id:
                return r
        return None

    async def update(self, table, doc_id, data):
        for r in self._store.get(table, []):
            if r.get("id") == doc_id:
                r.update(data)
                return True
        return False

    async def delete(self, table, doc_id):
        rows = self._store.get(table, [])
        self._store[table] = [r for r in rows if r.get("id") != doc_id]
        return True

    async def query(self, table, filters=None, order_by=None, order_direction="DESCENDING", limit=None, offset=None):
        rows = list(self._store.get(table, []))
        if filters:
            for field, op, value in filters:
                if op == "==":
                    rows = [r for r in rows if r.get(field) == value]
                elif op == "in":
                    rows = [r for r in rows if r.get(field) in value]
                elif op == "!=":
                    rows = [r for r in rows if r.get(field) != value]
                elif op == ">":
                    rows = [r for r in rows if (r.get(field) or 0) > value]
                elif op == ">=":
                    rows = [r for r in rows if (r.get(field) or 0) >= value]
                elif op == "<":
                    rows = [r for r in rows if (r.get(field) or 0) < value]
                elif op == "<=":
                    rows = [r for r in rows if (r.get(field) or 0) <= value]
        if order_by:
            rows.sort(key=lambda r: r.get(order_by) or 0,
                      reverse=(order_direction == "DESCENDING"))
        if offset:
            rows = rows[offset:]
        if limit:
            rows = rows[:limit]
        return rows


# ── Quota service ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quota_enforces_free_limit():
    from app.services.aim.quota import AIMQuotaService, FREE_ASSIGNMENT_LIMIT
    from fastapi import HTTPException

    quota = AIMQuotaService(db=FakeDB())
    user_id = "u1"
    for _ in range(FREE_ASSIGNMENT_LIMIT):
        await quota.enforce_create_assignment(user_id)
        await quota.record_assignment_created(user_id)
    with pytest.raises(HTTPException) as exc:
        await quota.enforce_create_assignment(user_id)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_quota_paid_plan_bypasses_limit():
    from app.services.aim.quota import AIMQuotaService, FREE_ASSIGNMENT_LIMIT

    db = FakeDB()
    quota = AIMQuotaService(db=db)
    user_id = "u-paid"
    await quota.get_or_create_period(user_id)
    # bump plan to paid in fake db
    db._store["aim_usage"][0]["plan"] = "paid"
    for _ in range(FREE_ASSIGNMENT_LIMIT + 5):
        await quota.enforce_create_assignment(user_id)
        await quota.record_assignment_created(user_id)


# ── Assignment service CRUD + analyze ───────────────────────────


@pytest.mark.asyncio
async def test_assignment_create_and_get_owner_scoped():
    from app.services.aim.assignment_service import AIMAssignmentService

    svc = AIMAssignmentService(db=FakeDB())
    row = await svc.create("u1", {"title": "Test brief"})
    assert row["id"]
    fetched = await svc.get("u1", row["id"])
    assert fetched and fetched["title"] == "Test brief"
    assert await svc.get("u2", row["id"]) is None


@pytest.mark.asyncio
async def test_analyze_requires_brief_document():
    from app.services.aim.assignment_service import AIMAssignmentService

    svc = AIMAssignmentService(db=FakeDB())
    row = await svc.create("u1", {"title": "Empty"})
    with pytest.raises(ValueError):
        await svc.analyze("u1", row["id"])


@pytest.mark.asyncio
async def test_analyze_with_clarification_does_not_materialize_sections():
    from ai_engine.chains.aim_pipeline import AnalysisResult

    from app.services.aim.assignment_service import AIMAssignmentService

    svc = AIMAssignmentService(db=FakeDB())
    row = await svc.create("u1", {"title": "Vague brief"})
    await svc.attach_document(
        "u1", row["id"], doc_type="brief", file_name=None, raw_text="Discuss things."
    )

    fake = AnalysisResult(
        parsed={"directive": "discuss", "rubric_breakdown": []},
        recon=None,
        needs_clarification=True,
        clarification_questions=["What is the topic?"],
        parser_confidence=0.42,
        flags=["needs_clarification"],
    )
    with patch(
        "app.services.aim.assignment_service.analyze_assignment",
        AsyncMock(return_value=fake),
    ):
        result = await svc.analyze("u1", row["id"])
    assert result.needs_clarification
    sections = await svc.db.query("aim_sections", filters=[("assignment_id", "==", row["id"])])
    assert sections == []
    a = await svc.get("u1", row["id"])
    assert a["status"] == "draft"


@pytest.mark.asyncio
async def test_analyze_materializes_sections_from_recon():
    from ai_engine.chains.aim_pipeline import AnalysisResult

    from app.services.aim.assignment_service import AIMAssignmentService

    svc = AIMAssignmentService(db=FakeDB())
    row = await svc.create("u1", {"title": "Good brief"})
    await svc.attach_document(
        "u1", row["id"], doc_type="brief", file_name=None,
        raw_text="Critically evaluate Tesla's strategy in 2024.",
    )
    fake = AnalysisResult(
        parsed={"directive": "evaluate", "rubric_breakdown": []},
        recon={
            "structure": [
                {"title": "Introduction", "purpose": "intro", "key_argument": "set scope",
                 "word_limit": 300, "order_index": 0},
                {"title": "Body", "purpose": "analysis", "key_argument": "thesis",
                 "word_limit": 1200, "order_index": 1},
            ]
        },
        needs_clarification=False,
        clarification_questions=[],
        parser_confidence=0.95,
        flags=[],
    )
    with patch(
        "app.services.aim.assignment_service.analyze_assignment",
        AsyncMock(return_value=fake),
    ):
        await svc.analyze("u1", row["id"])
    sections = await svc.db.query(
        "aim_sections", filters=[("assignment_id", "==", row["id"])]
    )
    assert len(sections) == 2
    a = await svc.get("u1", row["id"])
    assert a["status"] == "ready"


# ── Reviewer + filters deterministic behaviour ──────────────────


def test_quality_filters_detect_banned_phrase():
    from ai_engine.agents.aim.quality_filters import (
        BANNED_PHRASES, scan_banned_phrases,
    )
    sample = next(iter(BANNED_PHRASES))
    text = f"This essay will explore many topics. {sample.capitalize()} the issue is complex."
    hits = scan_banned_phrases(text)
    assert any(h.kind == "banned_phrase" for h in hits)


def test_quality_filters_detect_no_critique():
    from ai_engine.agents.aim.quality_filters import detect_no_critique
    bland = "Tesla makes cars. Tesla sells cars. Tesla is in many countries."
    hits = detect_no_critique(bland)
    assert hits, "expected critique-marker filter to flag bland prose"


def test_quality_filters_detect_repetition():
    from ai_engine.agents.aim.quality_filters import detect_repetition
    repeated = (
        "Tesla operates in many global markets across the world today. "
        "Tesla operates in many global markets across the world today. "
        "Tesla operates in many global markets across the world today. "
        "Tesla operates in many global markets across the world today. "
        "Their growth has been steady throughout this expansion period."
    )
    hits = detect_repetition(repeated)
    assert hits, "expected repetition filter to flag duplicated sentences"


# ── Grade predictor ceiling rule ────────────────────────────────


@pytest.mark.asyncio
async def test_grade_predictor_caps_distinction_when_subscores_low():
    from ai_engine.agents.aim.grade_predictor import AIMGradePredictorAgent

    agent = AIMGradePredictorAgent()
    # Simulate the agent's deterministic post-processing directly: build a fake
    # LLM result that claims distinction but section sub_scores are weak.
    section_reviews = [
        {"sub_scores": {"directive_alignment": 70, "analytical_depth": 60,
                        "academic_tone": 80, "originality": 65, "structure": 75}}
    ]
    parsed = {"academic_level": "ug", "rubric_breakdown": []}

    fake_llm = {
        "predicted_grade_low": 75,
        "predicted_grade_high": 80,
        "band": "First",
        "per_criterion": [],
        "feedback": {},
        "reasoning": "n/a",
        "confidence": 0.6,
    }
    with patch.object(agent.ai_client, "complete_json", AsyncMock(return_value=fake_llm)):
        result = await agent.run({
            "parsed": parsed, "section_reviews": section_reviews,
        })
    out = result.content
    assert out["predicted_grade_high"] <= 69
    assert out["band"] != "First"
