"""Worker process building blocks.

This package contains the reusable bootstrap logic for our background
worker fleet (``cd backend && python -m app.worker``).  It exists so the
worker entry point itself stays a thin shell, the bootstrap is unit
testable without spawning subprocesses, and follow-on PRs (outbox relay
in PR-9, event consumers in PR-10) can reuse the same runtime.
"""
from app.workers.runtime import WorkerRuntime, WorkerSettings, run_worker

__all__ = ["WorkerRuntime", "WorkerSettings", "run_worker"]
