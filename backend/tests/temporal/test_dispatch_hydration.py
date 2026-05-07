"""Tests for PR m6-pr24 dispatcher hydration: when the strangler
calls dispatch_generation_workflow with empty application_id /
requested_modules, the dispatcher fetches the real values from the
``generation_jobs`` row before starting the workflow."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.temporal import dispatch as dispatch_mod
from app.temporal.config import TemporalSettings


class _FakeHandle:
    def __init__(self, workflow_id: str) -> None:
        self.id = workflow_id


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def start_workflow(self, workflow, payload, *, id, task_queue):
        self.calls.append(
            {"workflow": workflow, "payload": payload, "id": id, "task_queue": task_queue}
        )
        return _FakeHandle(id)


def _settings() -> TemporalSettings:
    return TemporalSettings(
        host="example.tmprl.cloud:7233",
        namespace="hirestack.dev",
        task_queue="hirestack-generation",
        api_key="key",
        tls=True,
    )


class _FakeQuery:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def select(self, *_a, **_kw): return self
    def eq(self, *_a, **_kw): return self
    def limit(self, *_a, **_kw): return self
    def execute(self):
        class R:
            data = [self._row] if self._row is not None else []
        # capture self._row
        R.data = [self._row] if self._row is not None else []
        return R()


class _FakeSupabase:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def table(self, _name: str) -> _FakeQuery:
        return _FakeQuery(self._row)


@pytest.mark.asyncio
async def test_dispatch_hydrates_application_and_modules_when_caller_passes_empty():
    fake_client = _FakeClient()
    row = {
        "application_id": "app-real-42",
        "requested_modules": ["resume", "cover_letter", "linkedin"],
        "org_id": "org-hydrated",
    }

    async def _fake_get_client(_):
        return fake_client

    with patch.object(dispatch_mod, "get_client", _fake_get_client), \
         patch("app.core.database.get_supabase", lambda: _FakeSupabase(row)):
        wf_id = await dispatch_mod.dispatch_generation_workflow(
            job_id="job-99",
            user_id="user-77",
            application_id="",
            requested_modules=[],
            settings=_settings(),
        )

    assert wf_id == "generation-job-99"
    assert len(fake_client.calls) == 1
    payload = fake_client.calls[0]["payload"]
    assert payload.payload == {
        "application_id": "app-real-42",
        "requested_modules": ["resume", "cover_letter", "linkedin"],
    }
    assert payload.org_id == "org-hydrated"


@pytest.mark.asyncio
async def test_dispatch_does_not_overwrite_caller_provided_values():
    fake_client = _FakeClient()
    row = {
        "application_id": "app-real-42",
        "requested_modules": ["resume"],
        "org_id": "org-hydrated",
    }

    async def _fake_get_client(_):
        return fake_client

    with patch.object(dispatch_mod, "get_client", _fake_get_client), \
         patch("app.core.database.get_supabase", lambda: _FakeSupabase(row)):
        await dispatch_mod.dispatch_generation_workflow(
            job_id="job-100",
            user_id="user-1",
            application_id="caller-app",
            requested_modules=["caller-mod"],
            settings=_settings(),
            org_id="caller-org",
        )

    payload = fake_client.calls[0]["payload"]
    assert payload.payload == {
        "application_id": "caller-app",
        "requested_modules": ["caller-mod"],
    }
    assert payload.org_id == "caller-org"


@pytest.mark.asyncio
async def test_dispatch_tolerates_missing_job_row():
    """If the generation_jobs row vanished (e.g. race), dispatcher
    must NOT raise — it just dispatches with the caller's empty
    values rather than wedging the workflow path."""
    fake_client = _FakeClient()

    async def _fake_get_client(_):
        return fake_client

    with patch.object(dispatch_mod, "get_client", _fake_get_client), \
         patch("app.core.database.get_supabase", lambda: _FakeSupabase(None)):
        wf_id = await dispatch_mod.dispatch_generation_workflow(
            job_id="job-ghost",
            user_id="user-1",
            application_id="",
            requested_modules=[],
            settings=_settings(),
        )

    assert wf_id == "generation-job-ghost"
    payload = fake_client.calls[0]["payload"]
    assert payload.payload == {"application_id": "", "requested_modules": []}
