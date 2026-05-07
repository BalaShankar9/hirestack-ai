"""PR m6-pr21 — section_service wires SourceRetriever when ff_aim_rag is on.

When the flag is on AND the section has an `assignment_id`, the
service must construct a SourceRetriever (using a real-shaped
embedder) and pass it through to `generate_section`. When the flag is
off, neither `source_retriever` nor `assignment_id` may leak into the
generation call (preserves prior behaviour).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tests.aim.test_aim_services import FakeDB  # reuse


@pytest.fixture
def section_id_and_db():
    db = FakeDB()
    # Sentinel: section_service inspects `db.client` to construct the
    # retriever; FakeDB has no real Supabase client so we plant a
    # placeholder object the SourceRetriever will accept (it is never
    # called in these tests because generate_section is patched).
    db.client = object()  # type: ignore[attr-defined]
    return db


@pytest.mark.asyncio
async def test_generate_passes_retriever_when_ff_aim_rag_on(section_id_and_db, monkeypatch):
    from ai_engine.chains.aim_pipeline import SectionAttempt, SectionGenerationResult
    from app.services.aim.section_service import AIMSectionService

    db = section_id_and_db
    assignment_id = await db.create(
        "aim_assignments",
        {"user_id": "u1", "title": "T", "academic_level": "pg", "referencing_style": "apa"},
        doc_id="a1",
    )
    section_id = await db.create(
        "aim_sections",
        {
            "assignment_id": assignment_id,
            "user_id": "u1",
            "title": "Intro",
            "order_index": 0,
            "word_limit": 300,
        },
        doc_id="s1",
    )
    await db.create(
        "aim_assignment_analysis",
        {
            "assignment_id": assignment_id,
            "user_id": "u1",
            "directive": "analyse",
            "rubric_breakdown": [],
            "expectations": {},
            "recon_report": {},
        },
        doc_id="ana1",
    )

    fake_attempt = SectionAttempt(
        version=1,
        content="x",
        blocks=[],
        word_count=1,
        reviewer={
            "sub_scores": {
                "directive_alignment": 90,
                "analytical_depth": 90,
                "academic_tone": 90,
                "originality": 90,
                "structure": 90,
            },
            "ranked_issues": [],
        },
        weighted_score=90.0,
        passed_gate=True,
        latency_ms=1,
    )
    captured: dict[str, Any] = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return SectionGenerationResult(
            section_id=section_id,
            final_attempt=fake_attempt,
            history=[fake_attempt],
            final_passed_gate=True,
            stop_reason="passed",
        )

    # Force the flag on without mutating global Settings.
    import app.services.aim.section_service as svc_mod
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "ff_aim_rag", True, raising=False)

    # Stop real OpenAI client construction.
    sentinel_embedder = AsyncMock(return_value=[0.0] * 1536)
    monkeypatch.setattr(
        "app.services.aim.embedder_factory.build_openai_embedder",
        lambda model="text-embedding-3-small": sentinel_embedder,
    )

    svc = AIMSectionService(db=db)
    with patch.object(svc_mod, "generate_section", AsyncMock(side_effect=_fake_gen)):
        await svc.generate("u1", section_id)

    assert captured.get("assignment_id") == assignment_id
    retriever = captured.get("source_retriever")
    assert retriever is not None
    # SourceRetriever holds the same supabase client we planted.
    assert retriever._supabase is db.client


@pytest.mark.asyncio
async def test_generate_omits_retriever_when_ff_aim_rag_off(section_id_and_db, monkeypatch):
    from ai_engine.chains.aim_pipeline import SectionAttempt, SectionGenerationResult
    from app.services.aim.section_service import AIMSectionService

    db = section_id_and_db
    assignment_id = await db.create(
        "aim_assignments",
        {"user_id": "u1", "title": "T", "academic_level": "pg", "referencing_style": "apa"},
        doc_id="a1",
    )
    section_id = await db.create(
        "aim_sections",
        {
            "assignment_id": assignment_id,
            "user_id": "u1",
            "title": "Intro",
            "order_index": 0,
            "word_limit": 300,
        },
        doc_id="s1",
    )
    await db.create(
        "aim_assignment_analysis",
        {
            "assignment_id": assignment_id,
            "user_id": "u1",
            "directive": "analyse",
            "rubric_breakdown": [],
            "expectations": {},
            "recon_report": {},
        },
        doc_id="ana1",
    )

    fake_attempt = SectionAttempt(
        version=1,
        content="x",
        blocks=[],
        word_count=1,
        reviewer={
            "sub_scores": {
                "directive_alignment": 90,
                "analytical_depth": 90,
                "academic_tone": 90,
                "originality": 90,
                "structure": 90,
            },
            "ranked_issues": [],
        },
        weighted_score=90.0,
        passed_gate=True,
        latency_ms=1,
    )
    captured: dict[str, Any] = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return SectionGenerationResult(
            section_id=section_id,
            final_attempt=fake_attempt,
            history=[fake_attempt],
            final_passed_gate=True,
            stop_reason="passed",
        )

    import app.services.aim.section_service as svc_mod
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "ff_aim_rag", False, raising=False)

    svc = AIMSectionService(db=db)
    with patch.object(svc_mod, "generate_section", AsyncMock(side_effect=_fake_gen)):
        await svc.generate("u1", section_id)

    assert captured.get("source_retriever") is None
    assert captured.get("assignment_id") is None
