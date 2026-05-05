"""Tests for AIM Deadline Mode service \u2014 plan generation + status updates."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.aim.deadline_service import AIMDeadlineService

# Reuse the FakeDB pattern from test_aim_services
from backend.tests.aim.test_aim_services import FakeDB


@pytest.mark.asyncio
async def test_replan_creates_ordered_plan_with_submit_task():
    db = FakeDB()
    # Seed assignment + two sections
    await db.create("aim_assignments", {"id": "a1", "user_id": "u1"}, doc_id="a1")
    await db.create("aim_sections", {
        "user_id": "u1", "assignment_id": "a1",
        "title": "Intro", "order_index": 0, "word_limit": 300,
    })
    await db.create("aim_sections", {
        "user_id": "u1", "assignment_id": "a1",
        "title": "Body", "order_index": 1, "word_limit": 1500,
    })

    svc = AIMDeadlineService(db=db)
    deadline = (date.today() + timedelta(days=10)).isoformat()
    plan = await svc.replan("u1", "a1", deadline)

    assert len(plan) >= 4  # parser + recon + 2 sections + polish + submit
    titles = [t["task_name"] for t in plan]
    assert any("Parse" in t for t in titles)
    assert any("Recon" in t for t in titles)
    assert any("Intro" in t for t in titles)
    assert any("Body" in t for t in titles)
    assert titles[-1].startswith("Final")  # submit task last
    # All tasks owner-tagged
    assert all(t["user_id"] == "u1" and t["assignment_id"] == "a1" for t in plan)
    # order_index strictly increasing
    indices = [t["order_index"] for t in plan]
    assert indices == sorted(indices)


@pytest.mark.asyncio
async def test_replan_rejects_past_deadline():
    svc = AIMDeadlineService(db=FakeDB())
    past = (date.today() - timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="past"):
        await svc.replan("u1", "a1", past)


@pytest.mark.asyncio
async def test_replan_rejects_invalid_format():
    svc = AIMDeadlineService(db=FakeDB())
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await svc.replan("u1", "a1", "not-a-date")


@pytest.mark.asyncio
async def test_replan_replaces_existing_plan():
    db = FakeDB()
    await db.create("aim_assignments", {"id": "a1", "user_id": "u1"}, doc_id="a1")
    svc = AIMDeadlineService(db=db)
    deadline = (date.today() + timedelta(days=7)).isoformat()
    first = await svc.replan("u1", "a1", deadline)
    second = await svc.replan("u1", "a1", deadline)
    # No accumulation \u2014 same number of tasks
    rows = await db.query("aim_tasks", filters=[("assignment_id", "==", "a1")])
    assert len(rows) == len(second) == len(first)


@pytest.mark.asyncio
async def test_update_status_owner_scoped_and_sets_completed_at():
    db = FakeDB()
    svc = AIMDeadlineService(db=db)
    await db.create("aim_tasks", {
        "user_id": "u1", "assignment_id": "a1",
        "task_name": "x", "status": "pending",
    })
    [task] = await db.query("aim_tasks", filters=[("user_id", "==", "u1")])

    updated = await svc.update_status("u1", task["id"], "done")
    assert updated["status"] == "done"
    assert updated.get("completed_at")

    with pytest.raises(PermissionError):
        await svc.update_status("u-other", task["id"], "pending")

    with pytest.raises(ValueError):
        await svc.update_status("u1", task["id"], "bogus")
