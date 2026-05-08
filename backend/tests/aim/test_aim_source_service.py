from __future__ import annotations

import pytest

from backend.tests.aim.test_aim_services import FakeDB


@pytest.mark.asyncio
async def test_create_source_infers_reliability_and_normalizes_metadata():
    from app.services.aim.source_service import AIMSourceService

    db = FakeDB()
    assignment_id = await db.create(
        "aim_assignments",
        {"user_id": "u1", "title": "Research report", "status": "draft"},
    )
    svc = AIMSourceService(db=db)

    row = await svc.create_source(
        "u1",
        assignment_id,
        {
            "source_type": "journal_article",
            "title": "  AI in Higher Education  ",
            "authors": ["Ada Lovelace", "Ada Lovelace", "  Grace Hopper  "],
            "year": "2024",
            "doi": "10.1234/example",
            "raw_text": "Peer reviewed article text.",
        },
    )

    assert row["id"]
    assert row["title"] == "AI in Higher Education"
    assert row["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert row["year"] == 2024
    assert row["reliability_tier"] == "tier_1"
    assert row["verification_status"] == "unverified"


@pytest.mark.asyncio
async def test_create_source_marks_incomplete_web_source_as_needing_metadata():
    from app.services.aim.source_service import AIMSourceService

    db = FakeDB()
    assignment_id = await db.create(
        "aim_assignments",
        {"user_id": "u1", "title": "Essay", "status": "draft"},
    )
    svc = AIMSourceService(db=db)

    row = await svc.create_source("u1", assignment_id, {"source_type": "web_page"})

    assert row["reliability_tier"] == "tier_4"
    assert row["verification_status"] == "needs_metadata"


@pytest.mark.asyncio
async def test_sources_are_owner_scoped():
    from app.services.aim.source_service import AIMSourceService

    db = FakeDB()
    assignment_id = await db.create(
        "aim_assignments",
        {"user_id": "u1", "title": "Essay", "status": "draft"},
    )
    svc = AIMSourceService(db=db)
    row = await svc.create_source(
        "u1",
        assignment_id,
        {"source_type": "book", "title": "Methods", "raw_text": "Text"},
    )

    assert await svc.get_source("u1", row["id"])
    assert await svc.get_source("u2", row["id"]) is None
    with pytest.raises(ValueError):
        await svc.list_sources("u2", assignment_id)


@pytest.mark.asyncio
async def test_delete_source_requires_owner():
    from app.services.aim.source_service import AIMSourceService

    db = FakeDB()
    assignment_id = await db.create(
        "aim_assignments",
        {"user_id": "u1", "title": "Essay", "status": "draft"},
    )
    svc = AIMSourceService(db=db)
    row = await svc.create_source(
        "u1",
        assignment_id,
        {"source_type": "book", "title": "Methods", "raw_text": "Text"},
    )

    assert await svc.delete_source("u2", row["id"]) is False
    assert await svc.delete_source("u1", row["id"]) is True
    assert await svc.get_source("u1", row["id"]) is None