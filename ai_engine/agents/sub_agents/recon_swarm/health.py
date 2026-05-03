"""S18 — Provider Health Monitoring for Recon Swarm.

Tracks provider performance metrics over time and provides
health status for operational monitoring.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional


@dataclass(frozen=True)
class ProviderHealth:
    """Health status for a single provider.
    
    Attributes:
        name: Provider name
        status: Overall health status (healthy/degraded/unhealthy/unknown)
        success_rate_1h: Success rate over last hour (0-1)
        avg_latency_ms: Average latency in milliseconds
        p95_latency_ms: 95th percentile latency
        p99_latency_ms: 99th percentile latency
        last_error: Most recent error message (truncated)
        last_success_at: ISO timestamp of last success
        last_failure_at: ISO timestamp of last failure
        consecutive_failures: Current streak of failures
        total_calls_1h: Total calls in the last hour
    """
    name: str
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    success_rate_1h: float
    avg_latency_ms: int
    p95_latency_ms: int
    p99_latency_ms: int
    last_error: Optional[str]
    last_success_at: Optional[str]
    last_failure_at: Optional[str]
    consecutive_failures: int
    total_calls_1h: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status,
            "success_rate_1h": self.success_rate_1h,
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "last_error": self.last_error,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "consecutive_failures": self.consecutive_failures,
            "total_calls_1h": self.total_calls_1h,
        }


@dataclass
class _ProviderCallRecord:
    """Internal record of a provider call."""
    timestamp: float
    success: bool
    latency_ms: int
    error: Optional[str] = None


class ProviderHealthTracker:
    """Track provider health metrics over time.
    
    Maintains a rolling window of call history for each provider
    and calculates health metrics on demand.
    
    Example:
        tracker = ProviderHealthTracker(window_minutes=60)
        
        # Record calls
        await tracker.record("github", success=True, latency_ms=150)
        await tracker.record("crunchbase", success=False, latency_ms=0, error="Timeout")
        
        # Get health status
        health = await tracker.get_health("github")
        print(f"{health.name}: {health.status} ({health.success_rate_1h:.1%} success)")
    """
    
    def __init__(self, window_minutes: int = 60, max_calls_per_provider: int = 10000):
        """Initialize health tracker.
        
        Args:
            window_minutes: Time window for metrics calculation (default 60)
            max_calls_per_provider: Maximum call history to retain per provider
        """
        self._window = window_minutes * 60  # Convert to seconds
        self._max_calls = max_calls_per_provider
        self._calls: Dict[str, List[_ProviderCallRecord]] = {}
        self._lock = asyncio.Lock()
    
    async def record(
        self,
        provider_name: str,
        success: bool,
        latency_ms: int,
        error: Optional[str] = None,
    ):
        """Record a provider call result.
        
        Args:
            provider_name: Name of the provider
            success: Whether the call succeeded
            latency_ms: Call latency in milliseconds
            error: Error message if failed (will be truncated)
        """
        async with self._lock:
            if provider_name not in self._calls:
                self._calls[provider_name] = []
            
            # Truncate error message
            truncated_error = error[:200] if error else None
            
            # Add new record
            self._calls[provider_name].append(_ProviderCallRecord(
                timestamp=time.monotonic(),
                success=success,
                latency_ms=latency_ms,
                error=truncated_error,
            ))
            
            # Clean old entries outside window
            cutoff = time.monotonic() - self._window
            self._calls[provider_name] = [
                r for r in self._calls[provider_name] if r.timestamp > cutoff
            ]
            
            # Enforce max calls limit
            if len(self._calls[provider_name]) > self._max_calls:
                self._calls[provider_name] = self._calls[provider_name][-self._max_calls:]
    
    async def get_health(self, provider_name: str) -> ProviderHealth:
        """Get health status for a specific provider.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            ProviderHealth with current metrics
        """
        async with self._lock:
            calls = self._calls.get(provider_name, [])
            
            if not calls:
                return ProviderHealth(
                    name=provider_name,
                    status="unknown",
                    success_rate_1h=0.0,
                    avg_latency_ms=0,
                    p95_latency_ms=0,
                    p99_latency_ms=0,
                    last_error=None,
                    last_success_at=None,
                    last_failure_at=None,
                    consecutive_failures=0,
                    total_calls_1h=0,
                )
            
            # Calculate metrics
            total = len(calls)
            successes = [c for c in calls if c.success]
            failures = [c for c in calls if not c.success]
            
            # Success rate
            success_rate = len(successes) / total if total > 0 else 0.0
            
            # Latency stats (only successful calls)
            latencies = [c.latency_ms for c in successes if c.latency_ms > 0]
            
            if latencies:
                sorted_latencies = sorted(latencies)
                avg_latency = sum(latencies) / len(latencies)
                p95_idx = int(len(sorted_latencies) * 0.95)
                p99_idx = int(len(sorted_latencies) * 0.99)
                p95_latency = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
                p99_latency = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]
            else:
                avg_latency = 0
                p95_latency = 0
                p99_latency = 0
            
            # Consecutive failures (from most recent)
            consecutive_failures = 0
            for record in reversed(calls):
                if not record.success:
                    consecutive_failures += 1
                else:
                    break
            
            # Last success/failure timestamps
            last_success = next(
                (c for c in reversed(calls) if c.success), None
            )
            last_failure = next(
                (c for c in reversed(calls) if not c.success), None
            )
            
            # Last error message
            last_error = last_failure.error if last_failure else None
            
            # Determine status based on heuristics
            status = self._determine_status(
                success_rate=success_rate,
                consecutive_failures=consecutive_failures,
                avg_latency=avg_latency,
            )
            
            # Format timestamps
            def fmt_ts(timestamp: Optional[float]) -> Optional[str]:
                if timestamp is None:
                    return None
                return datetime.fromtimestamp(timestamp).isoformat()
            
            return ProviderHealth(
                name=provider_name,
                status=status,
                success_rate_1h=round(success_rate, 3),
                avg_latency_ms=int(avg_latency),
                p95_latency_ms=p95_latency,
                p99_latency_ms=p99_latency,
                last_error=last_error,
                last_success_at=fmt_ts(last_success.timestamp if last_success else None),
                last_failure_at=fmt_ts(last_failure.timestamp if last_failure else None),
                consecutive_failures=consecutive_failures,
                total_calls_1h=total,
            )
    
    def _determine_status(
        self,
        success_rate: float,
        consecutive_failures: int,
        avg_latency: float,
    ) -> Literal["healthy", "degraded", "unhealthy", "unknown"]:
        """Determine health status based on metrics.
        
        Heuristics:
        - Healthy: >= 95% success, no consecutive failures, reasonable latency
        - Degraded: >= 80% success, or < 5 consecutive failures
        - Unhealthy: < 80% success, or >= 5 consecutive failures
        - Unknown: No data
        """
        # High failure streak is always unhealthy
        if consecutive_failures >= 5:
            return "unhealthy"
        
        # High success rate with no failures is healthy
        if success_rate >= 0.95 and consecutive_failures == 0:
            return "healthy"
        
        # Medium success rate is degraded
        if success_rate >= 0.80:
            return "degraded"
        
        # Low success rate is unhealthy
        if success_rate > 0:
            return "unhealthy"
        
        # No data
        return "unknown"
    
    async def get_all_health(self) -> Dict[str, ProviderHealth]:
        """Get health status for all tracked providers.
        
        Returns:
            Dictionary mapping provider names to health status
        """
        async with self._lock:
            result = {}
            for name in self._calls.keys():
                # Release lock while calculating to avoid holding it too long
                pass
            
            # Calculate outside lock to prevent long-held lock
            names = list(self._calls.keys())
        
        # Calculate health for each provider (lock released between calls)
        for name in names:
            result[name] = await self.get_health(name)
        
        return result
    
    async def get_unhealthy_providers(self) -> List[str]:
        """Get list of unhealthy provider names.
        
        Returns:
            List of provider names with unhealthy or degraded status
        """
        all_health = await self.get_all_health()
        return [
            name for name, health in all_health.items()
            if health.status in ("unhealthy", "degraded")
        ]
    
    async def reset_provider(self, provider_name: str):
        """Clear history for a specific provider.
        
        Args:
            provider_name: Name of provider to reset
        """
        async with self._lock:
            if provider_name in self._calls:
                del self._calls[provider_name]
    
    async def reset_all(self):
        """Clear all provider history."""
        async with self._lock:
            self._calls.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tracker statistics.
        
        Returns:
            Dictionary with tracker metadata
        """
        return {
            "tracked_providers": len(self._calls),
            "total_calls_tracked": sum(len(c) for c in self._calls.values()),
            "window_seconds": self._window,
            "max_calls_per_provider": self._max_calls,
        }
