"""
Circuit breaker for AI pipeline stages.

Prevents cascading failures when the AI provider is down or degraded.
After ``failure_threshold`` consecutive failures, the breaker opens and
immediately rejects calls for ``recovery_timeout`` seconds.  A single
probe call is then allowed through (half-open); if it succeeds, the
breaker resets to closed.

Thread-safe and async-safe — uses a simple lock around state transitions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum

logger = logging.getLogger("hirestack.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when a call is rejected because the breaker is open."""

    def __init__(self, name: str, remaining_s: float):
        self.name = name
        self.remaining_s = remaining_s
        super().__init__(
            f"Circuit breaker '{name}' is open. "
            f"Retry in {remaining_s:.0f}s."
        )


class CircuitBreaker:
    """Per-name circuit breaker.

    Parameters
    ----------
    name : str
        Identifier (e.g. ``"gemini"``, ``"cv_generation"``).
    failure_threshold : int
        Consecutive failures before the breaker opens (default 5).
    recovery_timeout : float
        Seconds the breaker stays open before allowing a probe (default 60).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def __aenter__(self):
        await self._before_call()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self.record_success()
        else:
            await self.record_failure()
        return False  # Don't suppress the exception

    async def _before_call(self) -> None:
        """Gate: decide whether to allow the call through."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    # Transition to half-open — allow one probe call
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        "circuit_breaker_half_open: name=%s elapsed_s=%.1f",
                        self.name,
                        elapsed,
                    )
                    return
                remaining = self.recovery_timeout - elapsed
                raise CircuitBreakerOpen(self.name, remaining)

            # HALF_OPEN — allow the probe call through
            return

    async def record_success(self) -> None:
        """Record a successful call — reset the breaker."""
        async with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info(
                    "circuit_breaker_closed: name=%s previous_state=%s",
                    self.name,
                    self._state.value,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call — potentially open the breaker."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_reopened: name=%s failures=%d",
                    self.name,
                    self._failure_count,
                )
                return

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_opened: name=%s failures=%d recovery_timeout_s=%.0f",
                    self.name,
                    self._failure_count,
                    self.recovery_timeout,
                )

    async def reset(self) -> None:
        """Manually reset the breaker (e.g. for testing or admin action)."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0


# ── Global registry ─────────────────────────────────────────────────────
_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = asyncio.Lock()


async def get_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Get or create a named circuit breaker (process-global singleton per name)."""
    if name in _breakers:
        return _breakers[name]

    async with _registry_lock:
        # Double-check after acquiring lock
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _breakers[name]


def get_breaker_sync(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Non-async version — creates the breaker if it doesn't exist.

    Safe to call from module-level or non-async contexts.
    """
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _breakers[name]


def reset_all_breakers() -> None:
    """Reset all breakers — useful for testing."""
    _breakers.clear()
