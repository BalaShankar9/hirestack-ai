"""Shared Temporal test env (PR m6-pr17). One in-process time-skipping
server per session — booting it costs ~5s, so we amortise."""

from __future__ import annotations

import pytest_asyncio
from temporalio.testing import WorkflowEnvironment


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def temporal_env():
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        yield env
    finally:
        await env.shutdown()
