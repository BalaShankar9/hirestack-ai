"""S18 — Resilience patterns: Circuit Breaker and Rate Limiting for Recon Swarm.

Provides production-grade reliability patterns for external API calls:
- Circuit Breaker: Prevents cascade failures
- Rate Limiter: Respects API quotas
- ResilientProvider: Wraps providers with both patterns
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TypeVar

from .schemas import ProviderResult

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open (failing fast)."""
    pass


class CircuitBreaker:
    """Circuit breaker for external provider calls.
    
    States:
        CLOSED: Normal operation, requests pass through
        OPEN: Failing fast, requests immediately rejected
        HALF_OPEN: Testing if service recovered (limited calls allowed)
    
    Example:
        cb = CircuitBreaker("github_api", failure_threshold=3, recovery_timeout=60.0)
        try:
            result = await cb.call(lambda: fetch_github_data())
        except CircuitBreakerOpen:
            # Circuit is open, fail fast
            pass
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._state = "closed"
        self._failures = 0
        self._successes = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> str:
        """Current circuit state: closed, open, or half-open."""
        return self._state
    
    @property
    def failures(self) -> int:
        """Number of consecutive failures."""
        return self._failures
    
    async def call(self, fn: Callable[[], T]) -> T:
        """Execute function with circuit breaker protection.
        
        Args:
            fn: Async callable to execute
            
        Returns:
            Result from fn
            
        Raises:
            CircuitBreakerOpen: If circuit is open
            Exception: Any exception raised by fn
        """
        async with self._lock:
            if self._state == "open":
                if self._should_attempt_reset():
                    self._state = "half-open"
                    self._successes = 0
                    logger.info(f"Circuit {self.name} entering HALF-OPEN (testing recovery)")
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit '{self.name}' is OPEN (failing fast)"
                    )
            
            if self._state == "half-open" and self._successes >= self.half_open_max_calls:
                raise CircuitBreakerOpen(
                    f"Circuit '{self.name}' is HALF-OPEN (max test calls reached)"
                )
        
        try:
            result = await fn()
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self._failures = 0
            if self._state == "half-open":
                self._successes += 1
                if self._successes >= self.half_open_max_calls:
                    self._state = "closed"
                    logger.info(f"Circuit {self.name} CLOSED (recovered successfully)")
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.monotonic()
            
            if self._state == "half-open":
                self._state = "open"
                logger.warning(
                    f"Circuit {self.name} OPEN (failure in half-open: {self._failures} failures)"
                )
            elif self._failures >= self.failure_threshold:
                self._state = "open"
                logger.warning(
                    f"Circuit {self.name} OPEN ({self._failures} consecutive failures)"
                )
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try recovery."""
        if self._last_failure_time is None:
            return True
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.recovery_timeout
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize circuit breaker state."""
        return {
            "name": self.name,
            "state": self._state,
            "failures": self._failures,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_ago_seconds": (
                time.monotonic() - self._last_failure_time
                if self._last_failure_time else None
            ),
        }


class RateLimiter:
    """Token bucket rate limiter for API calls.
    
    Example:
        limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        async with limiter:
            await make_api_call()
    """
    
    def __init__(
        self,
        requests_per_minute: float,
        burst_size: Optional[int] = None,
    ):
        self.rate = requests_per_minute / 60.0
        self.burst = burst_size or int(requests_per_minute / 6)
        self._tokens = float(self.burst)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens. Returns wait time if throttled.
        
        Args:
            tokens: Number of tokens to acquire (default 1 per request)
            
        Returns:
            Wait time in seconds (0.0 if no wait needed)
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            
            # Add tokens based on elapsed time
            self._tokens = min(
                self.burst,
                self._tokens + elapsed * self.rate
            )
            self._last_update = now
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            
            # Calculate wait time
            needed = tokens - self._tokens
            wait_time = needed / self.rate
            self._tokens = 0
            return wait_time
    
    async def __aenter__(self):
        """Context manager entry - acquire and wait if needed."""
        wait = await self.acquire()
        if wait > 0:
            await asyncio.sleep(wait)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - nothing to clean up."""
        pass
    
    @property
    def tokens_available(self) -> float:
        """Current available tokens (approximate, for monitoring)."""
        elapsed = time.monotonic() - self._last_update
        return min(self.burst, self._tokens + elapsed * self.rate)


@dataclass
class ProviderResilienceConfig:
    """Configuration for provider resilience features.
    
    Attributes:
        circuit_breaker: Optional circuit breaker instance
        rate_limiter: Optional rate limiter instance
        timeout_seconds: Per-call timeout
        max_retries: Max retry attempts (0 = no retries)
        retry_delay: Base delay between retries (exponential backoff applied)
        retry_exponential_base: Multiply delay by this each retry (default 2.0)
    """
    circuit_breaker: Optional[CircuitBreaker] = None
    rate_limiter: Optional[RateLimiter] = None
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_delay: float = 0.5
    retry_exponential_base: float = 2.0


class ResilientProvider:
    """Wraps a SourceProvider with circuit breaker and rate limiting.
    
    This wrapper adds production-grade resilience patterns:
    - Circuit breaker prevents cascade failures
    - Rate limiting respects API quotas
    - Exponential backoff retries
    - Comprehensive error handling
    
    Example:
        config = ProviderResilienceConfig(
            circuit_breaker=CircuitBreaker("github", failure_threshold=3),
            rate_limiter=RateLimiter(requests_per_minute=60),
        )
        resilient = ResilientProvider(github_provider, config)
        result = await resilient.fetch(company="Stripe")
    """
    
    def __init__(
        self,
        provider: Any,  # SourceProvider protocol
        config: ProviderResilienceConfig,
    ):
        self._provider = provider
        self._config = config
        self.name = getattr(provider, "name", "unknown")
        self.layer = getattr(provider, "layer", 0)
    
    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        """Fetch with resilience patterns applied.
        
        Flow:
        1. Check rate limit (wait if needed)
        2. Check circuit breaker (fail fast if open)
        3. Execute with timeout
        4. Retry with exponential backoff on failure
        5. Record result for health tracking
        
        Args:
            company: Company name to research
            **ctx: Additional context (website, is_public, etc.)
            
        Returns:
            ProviderResult with success/failure status
        """
        provider_started = time.perf_counter()
        last_error: Optional[Exception] = None
        
        for attempt in range(1, self._config.max_retries + 1):
            try:
                # Apply rate limiting
                if self._config.rate_limiter:
                    await self._config.rate_limiter.acquire()
                
                # Apply circuit breaker
                if self._config.circuit_breaker:
                    result = await self._config.circuit_breaker.call(
                        lambda: self._do_fetch(company, **ctx)
                    )
                else:
                    result = await self._do_fetch(company, **ctx)
                
                # Update latency in result
                result.latency_ms = int((time.perf_counter() - provider_started) * 1000)
                return result
                
            except CircuitBreakerOpen:
                # Fast fail - don't retry if circuit is open
                latency_ms = int((time.perf_counter() - provider_started) * 1000)
                return ProviderResult(
                    provider=self.name,
                    layer=self.layer,
                    success=False,
                    latency_ms=latency_ms,
                    error=f"Circuit breaker open for {self.name}",
                )
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Provider {self.name} timeout (attempt {attempt}/{self._config.max_retries})"
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Provider {self.name} error (attempt {attempt}/{self._config.max_retries}): {e}"
                )
            
            # Calculate retry delay with exponential backoff
            if attempt < self._config.max_retries:
                delay = self._config.retry_delay * (
                    self._config.retry_exponential_base ** (attempt - 1)
                )
                logger.debug(f"Retrying {self.name} in {delay:.2f}s (attempt {attempt + 1})")
                await asyncio.sleep(delay)
        
        # All retries exhausted
        latency_ms = int((time.perf_counter() - provider_started) * 1000)
        error_msg = str(last_error)[:200] if last_error else "unknown error"
        
        logger.error(f"Provider {self.name} failed after {self._config.max_retries} attempts: {error_msg}")
        
        return ProviderResult(
            provider=self.name,
            layer=self.layer,
            success=False,
            latency_ms=latency_ms,
            error=error_msg,
        )
    
    async def _do_fetch(self, company: str, **ctx: Any) -> ProviderResult:
        """Execute actual fetch with timeout.
        
        Args:
            company: Company name
            **ctx: Context dict
            
        Returns:
            ProviderResult from wrapped provider
            
        Raises:
            asyncio.TimeoutError: If fetch exceeds timeout
            Exception: Any exception from provider
        """
        return await asyncio.wait_for(
            self._provider.fetch(company=company, **ctx),
            timeout=self._config.timeout_seconds,
        )
    
    def __repr__(self) -> str:
        return f"ResilientProvider({self.name}, layer={self.layer})"


def create_default_circuit_breaker(provider_name: str) -> CircuitBreaker:
    """Create a circuit breaker with sensible defaults.
    
    Args:
        provider_name: Name of the provider (for logging)
        
    Returns:
        Configured CircuitBreaker instance
    """
    return CircuitBreaker(
        name=provider_name,
        failure_threshold=3,
        recovery_timeout=60.0,
        half_open_max_calls=1,
    )


def create_rate_limiter_for_provider(provider_name: str) -> Optional[RateLimiter]:
    """Create rate limiter based on provider type.
    
    Known rate limits:
    - GitHub: 60/hr unauthenticated, 5000/hr authenticated
    - SEC EDGAR: 10 requests/second (per their fair access policy)
    - HackerNews: No explicit limit (be respectful)
    - Reddit: 30 requests/minute OAuth, 100/hour unauthenticated
    
    Args:
        provider_name: Name of the provider
        
    Returns:
        RateLimiter or None if no limiting needed
    """
    # Default conservative limits
    limits = {
        "github": 50,  # per minute (conservative)
        "sec_edgar": 8 * 60,  # 8 per second * 60 = 480/minute
        "reddit": 25,  # per minute
        "wikipedia": 200,  # per minute (be nice)
        "wikidata": 200,  # per minute
    }
    
    # Check if provider name matches any known limit
    for key, rpm in limits.items():
        if key in provider_name.lower():
            return RateLimiter(requests_per_minute=rpm)
    
    # No specific limit known - return None (no limiting)
    return None


def create_resilience_config(provider_name: str, layer: int = 1) -> ProviderResilienceConfig:
    """Create resilience configuration for a provider.
    
    This is a factory function that creates appropriate configuration
    based on provider name and layer.
    
    Args:
        provider_name: Name of the provider
        layer: Layer number (1 or 2)
        
    Returns:
        ProviderResilienceConfig with appropriate settings
    """
    # Create circuit breaker for all real API providers
    cb = create_default_circuit_breaker(provider_name)
    
    # Create rate limiter based on provider type
    rl = create_rate_limiter_for_provider(provider_name)
    
    # Layer-specific timeouts
    timeout = 30.0 if layer == 1 else 60.0
    
    return ProviderResilienceConfig(
        circuit_breaker=cb,
        rate_limiter=rl,
        timeout_seconds=timeout,
        max_retries=2,
        retry_delay=0.5,
        retry_exponential_base=2.0,
    )
