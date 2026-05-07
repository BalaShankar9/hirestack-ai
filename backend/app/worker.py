"""Standalone worker process for consuming generation jobs from Redis Streams.

Run via::

    cd /app/backend && PYTHONPATH=/app python -m app.worker

Or in Railway via the ``worker`` process in Procfile.

PR m2-pr5 — bootstrap moved into ``app.workers.runtime``; this module is
a thin entry point so future PRs (outbox relay, event consumers) can
reuse the same runtime without touching this file.
"""
import asyncio
import os
import sys

# Ensure the backend package root is on sys.path when invoked with -m.
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


async def _handler(job_id: str, user_id: str) -> None:
    """Execute a generation job — same runner the web process uses."""
    from app.api.routes.generate.jobs import _run_generation_job_via_runtime

    await _run_generation_job_via_runtime(job_id, user_id)


async def main() -> None:
    from app.workers.runtime import run_worker

    await run_worker(_handler)


if __name__ == "__main__":
    asyncio.run(main())

