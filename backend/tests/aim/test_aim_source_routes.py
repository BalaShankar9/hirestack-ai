from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.aim.test_aim_services import FakeDB

FAKE_USER = {"id": "user-1", "email": "u@example.com"}


@pytest.fixture
def source_client(monkeypatch):
    db = FakeDB()
    import app.services.aim.assignment_service as assignment_mod
    import app.services.aim.source_service as source_mod

    monkeypatch.setattr(assignment_mod, "get_db", lambda: db)
    monkeypatch.setattr(source_mod, "get_db", lambda: db)

    from app.api.deps import get_current_user
    from app.api.routes.aim import router as aim_router

    app = FastAPI()
    app.include_router(aim_router, prefix="/api/aim")
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    try:
        yield db, TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_create_and_list_assignment_sources(source_client):
    db, client = source_client
    import asyncio

    assignment_id = asyncio.run(db.create(
        "aim_assignments",
        {"user_id": FAKE_USER["id"], "title": "Research report", "status": "draft"},
    ))

    response = client.post(
        f"/api/aim/assignments/{assignment_id}/sources",
        json={
            "source_type": "journal_article",
            "title": "Academic integrity systems",
            "authors": ["Ada Lovelace"],
            "year": 2024,
            "doi": "10.1234/example",
            "raw_text": "Article body",
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["assignment_id"] == assignment_id
    assert created["reliability_tier"] == "tier_1"
    assert created["verification_status"] == "unverified"

    list_response = client.get(f"/api/aim/assignments/{assignment_id}/sources")
    assert list_response.status_code == 200
    assert list_response.json()[0]["title"] == "Academic integrity systems"


def test_source_routes_are_assignment_owner_scoped(source_client):
    db, client = source_client
    import asyncio

    assignment_id = asyncio.run(db.create(
        "aim_assignments",
        {"user_id": "someone-else", "title": "Private", "status": "draft"},
    ))

    response = client.post(
        f"/api/aim/assignments/{assignment_id}/sources",
        json={"source_type": "book", "title": "Hidden", "raw_text": "Text"},
    )

    assert response.status_code == 404


def test_get_and_delete_source(source_client):
    db, client = source_client
    import asyncio

    assignment_id = asyncio.run(db.create(
        "aim_assignments",
        {"user_id": FAKE_USER["id"], "title": "Essay", "status": "draft"},
    ))
    created = client.post(
        f"/api/aim/assignments/{assignment_id}/sources",
        json={"source_type": "book", "title": "Methods", "raw_text": "Text"},
    ).json()

    get_response = client.get(f"/api/aim/sources/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Methods"

    delete_response = client.delete(f"/api/aim/sources/{created['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/aim/sources/{created['id']}").status_code == 404