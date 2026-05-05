"""Integration tests for AIM HTTP routes \u2014 deadline, fix, upload."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock

# Stub pptx (optional dep used by an unrelated route) before route imports —
# but ONLY when python-pptx isn't actually installed. Otherwise this leaks a
# MagicMock into sys.modules that later poisons real ppt tests
# (test_ppt_smoke etc.) with `Presentation()` returning a MagicMock.
import importlib.util as _ilu
if _ilu.find_spec("pptx") is None:
    for mod in ("pptx", "pptx.dml", "pptx.dml.color", "pptx.enum",
                "pptx.enum.shapes", "pptx.enum.text", "pptx.util"):
        sys.modules.setdefault(mod, MagicMock())

import pytest
from fastapi.testclient import TestClient

from backend.tests.aim.test_aim_services import FakeDB

FAKE_USER = {"id": "user-1", "email": "u@example.com"}


@pytest.fixture
def fake_db_and_client(monkeypatch):
    db = FakeDB()

    # All AIM services resolve their db via module-level get_db()
    import app.services.aim.assignment_service as assignment_mod
    import app.services.aim.deadline_service as deadline_mod
    import app.services.aim.section_service as section_mod
    monkeypatch.setattr(assignment_mod, "get_db", lambda: db)
    monkeypatch.setattr(deadline_mod, "get_db", lambda: db)
    monkeypatch.setattr(section_mod, "get_db", lambda: db)

    # Build a minimal FastAPI app with only the AIM router mounted to avoid
    # importing every side-effect-heavy router (e.g. ppt → python-pptx).
    from fastapi import FastAPI
    from app.api.routes.aim import router as aim_router
    from app.api.deps import get_current_user

    app = FastAPI()
    app.include_router(aim_router, prefix="/api/aim")
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    try:
        yield db, TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _seed_assignment(db: FakeDB, user_id: str = FAKE_USER["id"]) -> str:
    aid = await db.create("aim_assignments", {
        "user_id": user_id, "title": "T", "status": "draft",
    })
    await db.create("aim_sections", {
        "user_id": user_id, "assignment_id": aid,
        "title": "Intro", "order_index": 0, "word_limit": 300,
    })
    await db.create("aim_sections", {
        "user_id": user_id, "assignment_id": aid,
        "title": "Body", "order_index": 1, "word_limit": 1500,
    })
    return aid


# ── Deadline routes ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deadline_list_empty_then_replan_then_patch(fake_db_and_client):
    db, client = fake_db_and_client
    aid = await _seed_assignment(db)

    # 1. Initially empty
    r = client.get(f"/api/aim/assignments/{aid}/tasks")
    assert r.status_code == 200
    assert r.json() == []

    # 2. Replan
    deadline = (date.today() + timedelta(days=8)).isoformat()
    r = client.post(
        f"/api/aim/assignments/{aid}/tasks/replan",
        json={"deadline": deadline},
    )
    assert r.status_code == 200, r.text
    tasks = r.json()
    assert len(tasks) >= 4
    assert tasks[-1]["task_name"].startswith("Final")

    # 3. Patch first task → in_progress
    first = tasks[0]
    r = client.patch(f"/api/aim/tasks/{first['id']}", json={"status": "in_progress"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_deadline_replan_rejects_past_date(fake_db_and_client):
    db, client = fake_db_and_client
    import asyncio
    aid = asyncio.run(_seed_assignment(db))

    past = (date.today() - timedelta(days=1)).isoformat()
    r = client.post(
        f"/api/aim/assignments/{aid}/tasks/replan",
        json={"deadline": past},
    )
    assert r.status_code == 400


def test_deadline_replan_404_on_unknown_assignment(fake_db_and_client):
    _, client = fake_db_and_client
    deadline = (date.today() + timedelta(days=5)).isoformat()
    r = client.post(
        "/api/aim/assignments/missing-id/tasks/replan",
        json={"deadline": deadline},
    )
    assert r.status_code == 404


def test_deadline_patch_404_on_other_users_task(fake_db_and_client):
    db, client = fake_db_and_client
    import asyncio
    asyncio.run(
        db.create("aim_tasks", {
            "user_id": "someone-else", "assignment_id": "x",
            "task_name": "x", "status": "pending",
        })
    )
    rows = asyncio.run(
        db.query("aim_tasks", filters=[("user_id", "==", "someone-else")])
    )
    r = client.patch(f"/api/aim/tasks/{rows[0]['id']}", json={"status": "done"})
    assert r.status_code == 404


def test_deadline_patch_400_on_bad_status(fake_db_and_client):
    db, client = fake_db_and_client
    import asyncio
    asyncio.run(
        db.create("aim_tasks", {
            "user_id": FAKE_USER["id"], "assignment_id": "x",
            "task_name": "t", "status": "pending",
        })
    )
    rows = asyncio.run(
        db.query("aim_tasks", filters=[("user_id", "==", FAKE_USER["id"])])
    )
    r = client.patch(f"/api/aim/tasks/{rows[0]['id']}", json={"status": "bogus"})
    assert r.status_code == 400


# ── Fix-My-Section route ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fix_section_route_proxies_to_chain(fake_db_and_client, monkeypatch):
    db, client = fake_db_and_client
    aid = await _seed_assignment(db)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]

    async def _fake_fix(section, parsed, draft):
        return {
            "weighted_score": 91.5,
            "passed_gate": True,
            "ranked_issues": [{"severity": "low", "issue": "tone", "suggested_fix": "warmer"}],
            "revised_draft": "Better draft.",
        }

    monkeypatch.setattr("app.services.aim.section_service.fix_section", _fake_fix)

    r = client.post(f"/api/aim/sections/{section_id}/fix", json={"draft": "raw text"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weighted_score"] == 91.5
    assert body["passed_gate"] is True
    assert body["ranked_issues"][0]["severity"] == "low"


def test_fix_section_route_404_on_unknown_section(fake_db_and_client):
    _, client = fake_db_and_client
    r = client.post("/api/aim/sections/missing/fix", json={"draft": "x"})
    assert r.status_code == 404


def test_fix_section_route_422_on_empty_draft(fake_db_and_client):
    _, client = fake_db_and_client
    r = client.post("/api/aim/sections/whatever/fix", json={"draft": ""})
    assert r.status_code == 422


# ── Apply manual draft route ────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_manual_draft_creates_current_version(fake_db_and_client):
    db, client = fake_db_and_client
    aid = await _seed_assignment(db)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]
    # seed an existing current output to verify demotion
    await db.create("aim_section_outputs", {
        "section_id": section_id, "user_id": FAKE_USER["id"],
        "content": "old", "version": 1, "is_current": True, "quality_score": 70,
    })

    r = client.post(
        f"/api/aim/sections/{section_id}/outputs/manual",
        json={"content": "new revised", "quality_score": 88.5},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["content"] == "new revised"
    assert body["is_current"] is True
    assert body["version"] == 2
    assert body["passed_gate"] is True
    assert body["model_used"] == "manual"

    rows = await db.query("aim_section_outputs", filters=[("section_id", "==", section_id)])
    currents = [r for r in rows if r.get("is_current")]
    assert len(currents) == 1 and currents[0]["content"] == "new revised"


def test_apply_manual_draft_404_on_unknown_section(fake_db_and_client):
    _, client = fake_db_and_client
    r = client.post(
        "/api/aim/sections/missing/outputs/manual",
        json={"content": "x"},
    )
    assert r.status_code == 404


# ── Upload route ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_document_route_persists_extracted_text(
    fake_db_and_client, monkeypatch
):
    db, client = fake_db_and_client
    aid = await _seed_assignment(db)

    async def _fake_parse(self, raw, ext):
        return f"extracted from .{ext}: " + raw.decode("utf-8", errors="ignore")

    monkeypatch.setattr(
        "app.services.aim.document_parser.AIMDocumentParser.parse", _fake_parse
    )

    files = {"file": ("brief.txt", BytesIO(b"hello world"), "text/plain")}
    r = client.post(
        f"/api/aim/assignments/{aid}/documents/upload",
        files=files,
        data={"type": "brief"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "brief"
    assert "hello world" in body["raw_text"]
    assert body["file_name"] == "brief.txt"


def test_upload_document_route_404_on_unknown_assignment(fake_db_and_client):
    _, client = fake_db_and_client
    files = {"file": ("x.txt", BytesIO(b"x"), "text/plain")}
    r = client.post(
        "/api/aim/assignments/missing/documents/upload",
        files=files,
        data={"type": "brief"},
    )
    assert r.status_code == 404


# ── /sections/{id}/generate-stream (B2: real streaming) ─────────────


def _parse_sse_stream(body: str) -> list[dict[str, Any]]:
    """Parse an SSE response body into ``[{event, data, raw}]`` dicts."""
    import json as _json

    out: list[dict[str, Any]] = []
    current_event: str | None = None
    for line in body.split("\n"):
        if line.startswith(":"):
            out.append({"event": "_comment", "data": None, "raw": line})
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            raw = line.split(":", 1)[1].strip()
            try:
                data = _json.loads(raw)
            except Exception:
                data = raw
            out.append({"event": current_event or "message", "data": data, "raw": raw})
            current_event = None
    return out


@pytest.mark.asyncio
async def test_generate_stream_emits_real_writer_reviewer_events(
    fake_db_and_client, monkeypatch,
):
    """The new SSE route must surface per-attempt agent_status events as they
    happen \u2014 NOT batch them at the end. Every event must carry
    ``schema_version``. The terminal ``complete`` event must be present."""
    from unittest.mock import AsyncMock
    from ai_engine.chains import aim_pipeline
    from ai_engine.agents.base import AgentResult

    db, client = fake_db_and_client
    aid = await _seed_assignment(db)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]
    # Seed analysis row so the orchestrator has parsed/recon to consume.
    await db.create("aim_assignment_analysis", {
        "assignment_id": aid, "user_id": FAKE_USER["id"],
        "directive": "analyse", "rubric_breakdown": [], "expectations": {},
        "recon_report": {"section_strategy": []},
    })

    def _mk(content, *, metadata=None):
        return AgentResult(content=content, quality_scores={}, flags=[],
                           latency_ms=5, metadata=metadata or {})

    monkeypatch.setattr(
        aim_pipeline.AIMWriterAgent, "run",
        AsyncMock(return_value=_mk({"content": "draft", "blocks": [], "word_count": 1})),
    )
    monkeypatch.setattr(
        aim_pipeline.AIMReviewerAgent, "run",
        AsyncMock(return_value=_mk(
            {"verdict": "pass", "ranked_issues": []},
            metadata={"weighted_score": 92.0, "passed_gate": True},
        )),
    )

    with client.stream("POST", f"/api/aim/sections/{section_id}/generate-stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(chunk for chunk in resp.iter_text())

    events = _parse_sse_stream(body)
    payload_events = [e for e in events if e["event"] != "_comment" and e["event"] != "message"]
    types = [e["event"] for e in payload_events]

    # Initial start envelope before any agent fires
    assert types[0] == "start"
    assert payload_events[0]["data"]["schema_version"]
    assert payload_events[0]["data"]["pipeline_name"] == "aim"

    # At least one writer + reviewer agent_status pair is interleaved BEFORE complete
    agent_statuses = [e for e in payload_events if e["event"] == "agent_status"]
    stages_seen = [e["data"].get("stage") for e in agent_statuses]
    assert "writer" in stages_seen
    assert "reviewer" in stages_seen

    # Every event payload carries a schema_version
    for e in payload_events:
        if isinstance(e["data"], dict):
            assert "schema_version" in e["data"], f"missing schema_version on {e['event']}"

    # Terminal complete event present and last
    assert types[-1] == "complete"
    assert payload_events[-1]["data"]["passed_gate"] is True
    assert payload_events[-1]["data"]["stop_reason"] == "passed"


@pytest.mark.asyncio
async def test_generate_stream_emits_error_on_failure(fake_db_and_client, monkeypatch):
    from unittest.mock import AsyncMock
    from ai_engine.chains import aim_pipeline

    db, client = fake_db_and_client
    aid = await _seed_assignment(db)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]
    await db.create("aim_assignment_analysis", {
        "assignment_id": aid, "user_id": FAKE_USER["id"],
        "directive": "analyse", "rubric_breakdown": [], "expectations": {},
        "recon_report": {},
    })

    monkeypatch.setattr(
        aim_pipeline.AIMWriterAgent, "run",
        AsyncMock(side_effect=RuntimeError("boom: model unavailable")),
    )

    with client.stream("POST", f"/api/aim/sections/{section_id}/generate-stream") as resp:
        assert resp.status_code == 200
        body = "".join(chunk for chunk in resp.iter_text())

    events = _parse_sse_stream(body)
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) == 1
    assert "boom" in error_events[0]["data"]["message"]
    assert error_events[0]["data"]["schema_version"]


def test_generate_stream_404_on_unknown_section(fake_db_and_client):
    _, client = fake_db_and_client
    r = client.post("/api/aim/sections/missing/generate-stream")
    assert r.status_code == 404


# ── /sections/{id}/events (resume-on-reconnect) ─────────────────────


@pytest.mark.asyncio
async def test_list_section_events_returns_events_after_since(
    fake_db_and_client, monkeypatch,
):
    db, client = fake_db_and_client
    aid = await _seed_assignment(db)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]

    # Patch the route's get_db lookup to use our FakeDB.
    monkeypatch.setattr("app.core.database.get_db", lambda: db)

    # Seed 5 events with sequences 1..5
    for seq in range(1, 6):
        await db.create("aim_section_events", {
            "section_id": section_id, "user_id": FAKE_USER["id"],
            "sequence": seq, "event_type": "agent_status",
            "agent": "writer", "status": "running" if seq % 2 else "completed",
            "message": f"step {seq}", "progress": seq * 10,
            "latency_ms": 0, "data": {},
        })

    # since=0 → all 5
    r = client.get(f"/api/aim/sections/{section_id}/events?since=0")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 5
    assert body["last_sequence"] == 5
    assert [e["sequence"] for e in body["events"]] == [1, 2, 3, 4, 5]

    # since=3 → only seq>3 (4, 5)
    r = client.get(f"/api/aim/sections/{section_id}/events?since=3")
    body = r.json()
    assert body["count"] == 2
    assert [e["sequence"] for e in body["events"]] == [4, 5]
    assert body["last_sequence"] == 5

    # since=5 → none, last_sequence falls back to since
    r = client.get(f"/api/aim/sections/{section_id}/events?since=5")
    body = r.json()
    assert body["count"] == 0
    assert body["events"] == []
    assert body["last_sequence"] == 5


def test_list_section_events_404_on_unknown_section(fake_db_and_client):
    _, client = fake_db_and_client
    r = client.get("/api/aim/sections/missing/events?since=0")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_section_events_400_on_negative_since(fake_db_and_client):
    db, client = fake_db_and_client
    aid = await _seed_assignment(db)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]
    r = client.get(f"/api/aim/sections/{section_id}/events?since=-1")
    assert r.status_code == 400

