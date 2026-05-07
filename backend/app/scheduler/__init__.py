"""Dedicated scheduler process — owns all periodic / background tasks.

The web process used to spawn:
  * stale-job sweeper (every 10 min)
  * career-monitor tick (every N seconds)
  * JobWatchdog (every 30 s)

That works for one replica; the moment the API horizontally scales the
sweeps fire on every replica, racing each other.  PR m2-pr6 splits these
into a dedicated ``scheduler`` process guarded by a Redis leader-lock so
exactly one instance runs the sweeps, regardless of replica count.

Public surface:

* ``LeaderLock``      — Redis SET NX EX 30 lease with refresh loop.
* ``run_scheduler``   — entry point: acquire lock, run all periodic jobs.
* ``periodic_stale_job_cleanup`` / ``periodic_career_monitor_tick``
                       — the loops themselves, importable so the legacy
                       in-proc path in ``main.py`` keeps working when
                       ``settings.legacy_inproc_scheduler`` is True.
"""
from app.scheduler.leader_lock import LeaderLock
from app.scheduler.jobs import (
    periodic_stale_job_cleanup,
    periodic_career_monitor_tick,
)

__all__ = [
    "LeaderLock",
    "periodic_stale_job_cleanup",
    "periodic_career_monitor_tick",
    "run_scheduler",
]


async def run_scheduler() -> None:  # pragma: no cover — thin entry point
    from app.scheduler.main import run

    await run()
