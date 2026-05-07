"""Tests for the PR m6-pr18 Temporal strangler.

Two surfaces:

* `_start_generation_job` (the route handler entry point) — branches on
  `ff_temporal_generation` + `TemporalSettings.enabled`. This file
  exercises both legs by monkey-patching the dispatch helper.
* `dispatch_generation_workflow` — verified through a fake `Client`
  to keep the test sync and dependency-free.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from app.temporal import dispatch as dispatch_mod
from app.temporal.config import TemporalSettings


# ── dispatch_generation_workflow ────────────────────────────────────────


class _FakeHandle:
    def __init__(self, workflow_id: str) -> None:
        self.id = workflow_id


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def start_workflow(self, workflow, payload, *, id, task_queue):
        self.calls.append(
            {
                "workflow": workflow,
                "payload": payload,
                "id": id,
                "task_queue": task_queue,
            }
        )
        return _FakeHandle(id)


@pytest.mark.asyncio
async def test_dispatch_generation_workflow_starts_workflow():
    fake = _FakeClient()
    settings = TemporalSettings(
        host="example.tmprl.cloud:7233",
        namespace="hirestack.dev",
        task_queue="hirestack-generation",
        api_key="key",
        tls=True,
    )

    async def _fake_get_client(_):
        return fake

    with patch.object(dispatch_mod, "get_client", _fake_get_client):
        wf_id = await dispatch_mod.dispatch_generation_workflow(
            job_id="job-123",
            user_id="user-1",
            application_id="app-9",
            requested_modules=["resume", "cover_letter"],
            settings=settings,
        )

    assert wf_id == "generation-job-123"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["id"] == "generation-job-123"
    assert call["task_queue"] == "hirestack-generation"
    payload = call["payload"]
    assert payload.job_id == "job-123"
    assert payload.payload == {
        "application_id": "app-9",
        "requested_modules": ["resume", "cover_letter"],
    }


@pytest.mark.asyncio
async def test_get_client_raises_when_temporal_disabled():
    settings = TemporalSettings(
        host="", namespace="default", task_queue="x", api_key=None, tls=False
    )
    with pytest.raises(RuntimeError, match="not configured"):
        await dispatch_mod.get_client(settings)


# ── _start_generation_job strangler ─────────────────────────────────────


@pytest.fixture
def jobs_module():
    from app.api.routes.generate import jobs as jobs_module

    # Reset the active-jobs registry so test ordering doesn't matter.
    jobs_module._ACTIVE_GENERATION_TASKS.clear()
    return jobs_module


@pytest.mark.asyncio
async def test_start_generation_job_uses_legacy_when_flag_off(jobs_module):
    legacy_calls: list[tuple[str, str]] = []
    temporal_calls: list[tuple[str, str]] = []

    def _legacy(job_id, user_id):
        legacy_calls.append((job_id, user_id))

    async def _dispatch(**kwargs):
        temporal_calls.append((kwargs["job_id"], kwargs["user_id"]))
        return f"generation-{kwargs['job_id']}"

    from app.core.config import settings as app_settings

    with patch.object(jobs_module, "_start_generation_job_legacy", _legacy), \
         patch.object(dispatch_mod, "dispatch_generation_workflow", _dispatch), \
         patch.object(app_settings, "ff_temporal_generation", False, create=True):
        jobs_module._start_generation_job("job-A", "user-X")
        await asyncio.sleep(0)  # let any pending tasks run

    assert legacy_calls == [("job-A", "user-X")]
    assert temporal_calls == []


@pytest.mark.asyncio
async def test_start_generation_job_uses_legacy_when_temporal_unconfigured(
    jobs_module,
):
    """Flag ON but TEMPORAL_HOST unset → fall through to legacy."""
    legacy_calls: list[tuple[str, str]] = []
    temporal_calls: list[tuple[str, str]] = []

    def _legacy(job_id, user_id):
        legacy_calls.append((job_id, user_id))

    async def _dispatch(**kwargs):
        temporal_calls.append((kwargs["job_id"], kwargs["user_id"]))
        return "should-not-reach"

    from app.core.config import settings as app_settings
    from app.temporal import config as temporal_config

    disabled = TemporalSettings(
        host="", namespace="default", task_queue="x", api_key=None, tls=False
    )

    with patch.object(jobs_module, "_start_generation_job_legacy", _legacy), \
         patch.object(dispatch_mod, "dispatch_generation_workflow", _dispatch), \
         patch.object(temporal_config, "load_settings", lambda: disabled), \
         patch.object(app_settings, "ff_temporal_generation", True, create=True):
        jobs_module._start_generation_job("job-B", "user-Y")
        await asyncio.sleep(0)

    assert legacy_calls == [("job-B", "user-Y")]
    assert temporal_calls == []


@pytest.mark.asyncio
async def test_start_generation_job_dispatches_when_flag_on_and_configured(
    jobs_module,
):
    legacy_calls: list[tuple[str, str]] = []
    temporal_calls: list[dict[str, Any]] = []

    def _legacy(job_id, user_id):
        legacy_calls.append((job_id, user_id))

    async def _dispatch(**kwargs):
        temporal_calls.append(kwargs)
        return f"generation-{kwargs['job_id']}"

    from app.core.config import settings as app_settings
    from app.temporal import config as temporal_config

    enabled = TemporalSettings(
        host="example.tmprl.cloud:7233",
        namespace="hirestack.dev",
        task_queue="hirestack-generation",
        api_key="key",
        tls=True,
    )

    # Patch on the *jobs_module*'s import surface — _start_generation_job
    # does `from app.temporal.dispatch import dispatch_generation_workflow`
    # *inside* the closure, so we patch the module the import resolves to.
    with patch.object(jobs_module, "_start_generation_job_legacy", _legacy), \
         patch.object(dispatch_mod, "dispatch_generation_workflow", _dispatch), \
         patch.object(temporal_config, "load_settings", lambda: enabled), \
         patch.object(app_settings, "ff_temporal_generation", True, create=True):
        jobs_module._start_generation_job("job-C", "user-Z")
        # Yield twice: first lets _try_temporal start, second lets it await
        # the patched coroutine.
        for _ in range(3):
            await asyncio.sleep(0)

    assert legacy_calls == []
    assert len(temporal_calls) == 1
    assert temporal_calls[0]["job_id"] == "job-C"
    assert temporal_calls[0]["user_id"] == "user-Z"


@pytest.mark.asyncio
async def test_start_generation_job_falls_back_when_dispatch_raises(
    jobs_module,
):
    legacy_calls: list[tuple[str, str]] = []

    def _legacy(job_id, user_id):
        legacy_calls.append((job_id, user_id))

    async def _failing_dispatch(**_kwargs):
        raise RuntimeError("temporal unreachable")

    from app.core.config import settings as app_settings
    from app.temporal import config as temporal_config

    enabled = TemporalSettings(
        host="example.tmprl.cloud:7233",
        namespace="hirestack.dev",
        task_queue="hirestack-generation",
        api_key="key",
        tls=True,
    )

    with patch.object(jobs_module, "_start_generation_job_legacy", _legacy), \
         patch.object(dispatch_mod, "dispatch_generation_workflow", _failing_dispatch), \
         patch.object(temporal_config, "load_settings", lambda: enabled), \
         patch.object(app_settings, "ff_temporal_generation", True, create=True):
        jobs_module._start_generation_job("job-D", "user-W")
        for _ in range(3):
            await asyncio.sleep(0)

    assert legacy_calls == [("job-D", "user-W")]
