"""Reusable worker runtime — wraps QueueConsumer with structured logging,
graceful-shutdown signal handling, and a clean test seam.

The previous ``backend/app/worker.py`` did all of this inline.  PR m2-pr5
extracts it into a class so:

1. Bootstrap can be tested without spawning a real subprocess.
2. PR-9 (outbox relay) and PR-10 (event consumers) can reuse the same
   shutdown / supervision pattern instead of copy-pasting signal logic.
3. ``app.worker`` becomes a 10-line entry point that's safe to leave
   untouched across future refactors.

Public surface (intentionally small):

* ``WorkerSettings`` — frozen dataclass of bootstrap config.
* ``WorkerRuntime`` — installs signal handlers, runs the consumer.
* ``run_worker(handler, ...)`` — convenience wrapper used by app.worker.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Optional

import structlog


HandlerFn = Callable[[str, str], Awaitable[None]]
"""Generation job handler signature: ``async def handler(job_id, user_id)``."""


def _configure_default_logging() -> None:
    """Configure structlog → JSON for production worker output.

    Idempotent: safe to call from tests where structlog is already
    configured.  Pulled out of module top-level so importing
    ``app.workers`` for its types does not mutate global logging state.
    """
    if getattr(_configure_default_logging, "_done", False):  # type: ignore[attr-defined]
        return
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    _configure_default_logging._done = True  # type: ignore[attr-defined]


@dataclass(frozen=True)
class WorkerSettings:
    """Frozen config for the worker bootstrap.

    Defaults are wired to ``app.core.config.settings`` by ``run_worker``;
    tests construct this explicitly so they don't depend on env vars.
    """

    consumer_name: str
    concurrency: int = 1
    install_signal_handlers: bool = True
    shutdown_signals: Iterable[int] = field(
        default_factory=lambda: (signal.SIGTERM, signal.SIGINT)
    )

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError(f"concurrency must be >= 1, got {self.concurrency}")
        if not self.consumer_name:
            raise ValueError("consumer_name must be a non-empty string")


class WorkerRuntime:
    """Owns the QueueConsumer lifecycle: install signal handlers, run the
    consumer, log lifecycle events, support clean shutdown.

    The consumer is constructor-injected so tests can pass a fake without
    standing up Redis.  The handler is also pluggable, which is what
    makes the runtime reusable across PR-9 (outbox relay) and PR-10
    (event consumers).
    """

    def __init__(
        self,
        handler: HandlerFn,
        settings: WorkerSettings,
        consumer_factory: Optional[Callable[..., object]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._handler = handler
        self._settings = settings
        self._consumer_factory = consumer_factory
        self._logger = logger or logging.getLogger("hirestack.worker")
        self._consumer: object | None = None

    def _build_consumer(self) -> object:
        if self._consumer_factory is not None:
            return self._consumer_factory(
                handler=self._handler,
                consumer_name=self._settings.consumer_name,
                concurrency=self._settings.concurrency,
            )
        # Lazy import: avoids pulling Redis at module import time, which
        # would break unit tests of WorkerSettings / WorkerRuntime.
        from app.core.queue import QueueConsumer

        return QueueConsumer(
            handler=self._handler,
            consumer_name=self._settings.consumer_name,
            concurrency=self._settings.concurrency,
        )

    def _install_signals(self, consumer: object) -> None:
        if not self._settings.install_signal_handlers:
            return
        loop = asyncio.get_running_loop()

        def _shutdown(*_: object) -> None:
            self._logger.info("worker.shutdown_signal")
            stop = getattr(consumer, "stop", None)
            if callable(stop):
                stop()

        for sig in self._settings.shutdown_signals:
            try:
                loop.add_signal_handler(sig, _shutdown)
            except (NotImplementedError, RuntimeError):
                # Windows / restricted environments — no-op.
                pass

    async def run(self) -> None:
        """Build the consumer, install signal handlers, run until exit."""
        self._consumer = self._build_consumer()
        self._install_signals(self._consumer)
        self._logger.info(
            "worker.starting",
            extra={
                "consumer": self._settings.consumer_name,
                "concurrency": self._settings.concurrency,
            },
        )
        run = getattr(self._consumer, "run", None)
        if run is None or not callable(run):
            raise TypeError(
                "consumer must expose an async `run()` method; "
                f"got {type(self._consumer).__name__}"
            )
        await run()
        self._logger.info("worker.exited")


async def run_worker(
    handler: HandlerFn,
    settings: Optional[WorkerSettings] = None,
) -> None:
    """Bootstrap entry point used by ``app.worker``.

    Reads concurrency / consumer name from ``app.core.config.settings``
    when ``settings`` is not provided.
    """
    _configure_default_logging()
    if settings is None:
        from app.core.config import settings as _config

        settings = WorkerSettings(
            consumer_name=_config.worker_name,
            concurrency=_config.worker_concurrency,
        )
    runtime = WorkerRuntime(handler=handler, settings=settings)
    await runtime.run()
