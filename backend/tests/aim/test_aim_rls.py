"""AIM owner-scoping (RLS-equivalent) tests.

The Supabase RLS policy is `auth.uid() = user_id` on every aim_* table. At the
service layer we mirror that with explicit `user_id` filters and ownership
checks. These tests assert that user A can never read, mutate, or destroy data
owned by user B through any AIM service entry point.

Real RLS enforcement happens in Postgres; this file pins the *application
layer* contract so a service-level bypass is impossible even if RLS were
misconfigured.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.aim.assignment_service import AIMAssignmentService
from app.services.aim.deadline_service import AIMDeadlineService
from app.services.aim.section_service import AIMSectionService
from backend.tests.aim.test_aim_services import FakeDB


USER_A = "user-aaaa"
USER_B = "user-bbbb"


async def _seed_assignment_for(db: FakeDB, user_id: str) -> str:
    asvc = AIMAssignmentService(db=db)
    a = await asvc.create(user_id, {
        "title": "User-scoped essay",
        "course": "PHIL101",
        "academic_level": "undergraduate",
        "referencing_style": "APA",
        "word_count": 1500,
    })
    aid = a["id"]
    await db.create("aim_sections", {
        "assignment_id": aid, "user_id": user_id, "title": "Intro", "order_index": 0,
        "word_limit": 300, "purpose": "p", "key_argument": "k",
    })
    return aid


# ── Assignments ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_b_cannot_get_user_a_assignment():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    asvc = AIMAssignmentService(db=db)
    assert await asvc.get(USER_A, aid) is not None
    assert await asvc.get(USER_B, aid) is None


@pytest.mark.asyncio
async def test_list_for_user_only_returns_own_rows():
    db = FakeDB()
    await _seed_assignment_for(db, USER_A)
    await _seed_assignment_for(db, USER_A)
    await _seed_assignment_for(db, USER_B)
    asvc = AIMAssignmentService(db=db)
    a_rows = await asvc.list_for_user(USER_A)
    b_rows = await asvc.list_for_user(USER_B)
    assert len(a_rows) == 2
    assert len(b_rows) == 1
    assert all(r["user_id"] == USER_A for r in a_rows)
    assert all(r["user_id"] == USER_B for r in b_rows)


@pytest.mark.asyncio
async def test_user_b_cannot_delete_user_a_assignment():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    asvc = AIMAssignmentService(db=db)
    deleted = await asvc.delete(USER_B, aid)
    assert deleted is False
    # row still exists for user A
    assert await asvc.get(USER_A, aid) is not None


# ── Sections ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_b_cannot_get_user_a_section():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]
    ssvc = AIMSectionService(db=db)
    assert await ssvc.get_section(USER_A, section_id) is not None
    assert await ssvc.get_section(USER_B, section_id) is None


@pytest.mark.asyncio
async def test_user_b_cannot_apply_manual_draft_to_user_a_section():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]
    ssvc = AIMSectionService(db=db)
    with pytest.raises(ValueError, match="section not found"):
        await ssvc.save_manual_output(USER_B, section_id, "hijack attempt")


@pytest.mark.asyncio
async def test_user_b_cannot_fix_user_a_section():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    rows = await db.query("aim_sections", filters=[("assignment_id", "==", aid)])
    section_id = rows[0]["id"]
    ssvc = AIMSectionService(db=db)
    with pytest.raises(ValueError, match="section not found"):
        await ssvc.fix(USER_B, section_id, "draft text")


# ── Deadline tasks ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_b_cannot_replan_user_a_assignment():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    dsvc = AIMDeadlineService(db=db)
    deadline = (date.today() + timedelta(days=14)).isoformat()
    with pytest.raises(PermissionError):
        await dsvc.replan(USER_B, aid, deadline)


@pytest.mark.asyncio
async def test_user_b_cannot_update_user_a_task_status():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    dsvc = AIMDeadlineService(db=db)
    deadline = (date.today() + timedelta(days=14)).isoformat()
    await dsvc.replan(USER_A, aid, deadline)
    tasks = await dsvc.list_tasks(USER_A, aid)
    assert tasks
    task_id = tasks[0]["id"]
    with pytest.raises(PermissionError):
        await dsvc.update_status(USER_B, task_id, "done")


@pytest.mark.asyncio
async def test_user_b_cannot_list_user_a_tasks():
    db = FakeDB()
    aid = await _seed_assignment_for(db, USER_A)
    dsvc = AIMDeadlineService(db=db)
    deadline = (date.today() + timedelta(days=14)).isoformat()
    await dsvc.replan(USER_A, aid, deadline)
    # list_tasks is RLS-equivalent: filtered by user_id, so user B sees nothing
    # (no permission error required — invisible IS the policy).
    b_tasks = await dsvc.list_tasks(USER_B, aid)
    assert b_tasks == []
    a_tasks = await dsvc.list_tasks(USER_A, aid)
    assert len(a_tasks) > 0
