"""S18 — Metrics and Observability for Recon Swarm.

Provides Prometheus-compatible metrics export for production monitoring.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProviderMetrics:
    """Metrics for a single provider."""
    name: str
    calls_total: int = 0
    calls_successful: int = 0
    calls_failed: int = 0
    latency_total_ms: int = 0
    latency_samples: List[int] = field(default_factory=list)
    last_called_at: Optional[float] = None
    last_error: Optional[str] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate (0-1)."""
        if self.calls_total == 0:
            return 0.0
        return self.calls_successful / self.calls_total
    
    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if not self.latency_samples:
            return 0.0
        return sum(self.latency_samples) / len(self.latency_samples)
    
    @property
    def p95_latency_ms(self) -> int:
        """Calculate 95th percentile latency."""
        if not self.latency_samples:
            return 0
        sorted_samples = sorted(self.latency_samples)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]


class ReconMetrics:
    """Metrics collector for recon swarm.
    
    Collects and exports metrics in Prometheus-compatible format
    for monitoring dashboards and alerting.
    
    Example:
        metrics = ReconMetrics()
        
        # Record calls
        metrics.record_provider_call("github", latency_ms=150, success=True)
        metrics.record_cache_hit()
        
        # Export
        prometheus_text = metrics.to_prometheus()
    """
    
    def __init__(self, max_latency_samples: int = 1000):
        """Initialize metrics collector.
        
        Args:
            max_latency_samples: Max samples to keep per provider for percentiles
        """
        self._max_samples = max_latency_samples
        self._provider_metrics: Dict[str, ProviderMetrics] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._circuit_breaker_opens = 0
        self._total_requests = 0
        self._total_latency_ms = 0
        self._started_at = time.monotonic()
    
    def record_provider_call(
        self,
        name: str,
        latency_ms: int,
        success: bool,
        error: Optional[str] = None,
    ):
        """Record a provider call.
        
        Args:
            name: Provider name
            latency_ms: Call latency in milliseconds
            success: Whether call succeeded
            error: Error message if failed
        """
        if name not in self._provider_metrics:
            self._provider_metrics[name] = ProviderMetrics(name=name)
        
        pm = self._provider_metrics[name]
        pm.calls_total += 1
        pm.latency_total_ms += latency_ms
        pm.latency_samples.append(latency_ms)
        pm.last_called_at = time.monotonic()
        
        # Keep only recent samples for percentile calculation
        if len(pm.latency_samples) > self._max_samples:
            pm.latency_samples = pm.latency_samples[-self._max_samples:]
        
        if success:
            pm.calls_successful += 1
        else:
            pm.calls_failed += 1
            pm.last_error = error[:200] if error else None
    
    def record_cache_hit(self):
        """Record a cache hit."""
        self._cache_hits += 1
    
    def record_cache_miss(self):
        """Record a cache miss."""
        self._cache_misses += 1
    
    def record_circuit_breaker_open(self):
        """Record a circuit breaker opening."""
        self._circuit_breaker_opens += 1
    
    def record_request(self, latency_ms: int):
        """Record a completed recon request.
        
        Args:
            latency_ms: Total request latency
        """
        self._total_requests += 1
        self._total_latency_ms += latency_ms
    
    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format.
        
        Returns:
            Prometheus exposition format string
        """
        lines = []
        timestamp = int(time.time() * 1000)
        
        # Request metrics
        lines.append("# HELP recon_swarm_requests_total Total recon requests")
        lines.append("# TYPE recon_swarm_requests_total counter")
        lines.append(f"recon_swarm_requests_total {self._total_requests}")
        
        # Average latency
        lines.append("")
        lines.append("# HELP recon_swarm_avg_latency_ms Average request latency")
        lines.append("# TYPE recon_swarm_avg_latency_ms gauge")
        avg_latency = (
            self._total_latency_ms / self._total_requests
            if self._total_requests > 0 else 0
        )
        lines.append(f"recon_swarm_avg_latency_ms {avg_latency:.3f}")
        
        # Cache metrics
        lines.append("")
        lines.append("# HELP recon_swarm_cache_hits_total Total cache hits")
        lines.append("# TYPE recon_swarm_cache_hits_total counter")
        lines.append(f"recon_swarm_cache_hits_total {self._cache_hits}")
        
        lines.append("")
        lines.append("# HELP recon_swarm_cache_misses_total Total cache misses")
        lines.append("# TYPE recon_swarm_cache_misses_total counter")
        lines.append(f"recon_swarm_cache_misses_total {self._cache_misses}")
        
        lines.append("")
        lines.append("# HELP recon_swarm_cache_hit_ratio Cache hit ratio")
        lines.append("# TYPE recon_swarm_cache_hit_ratio gauge")
        total_cache = self._cache_hits + self._cache_misses
        hit_ratio = self._cache_hits / total_cache if total_cache > 0 else 0
        lines.append(f"recon_swarm_cache_hit_ratio {hit_ratio:.3f}")
        
        # Circuit breaker metrics
        lines.append("")
        lines.append("# HELP recon_swarm_circuit_breaker_opens_total Total circuit breaker opens")
        lines.append("# TYPE recon_swarm_circuit_breaker_opens_total counter")
        lines.append(f"recon_swarm_circuit_breaker_opens_total {self._circuit_breaker_opens}")
        
        # Provider metrics
        lines.append("")
        lines.append("# HELP recon_swarm_provider_calls_total Total provider calls")
        lines.append("# TYPE recon_swarm_provider_calls_total counter")
        for name, pm in self._provider_metrics.items():
            lines.append(f'recon_swarm_provider_calls_total{{provider="{name}"}} {pm.calls_total}')
        
        lines.append("")
        lines.append("# HELP recon_swarm_provider_calls_successful Successful provider calls")
        lines.append("# TYPE recon_swarm_provider_calls_successful counter")
        for name, pm in self._provider_metrics.items():
            lines.append(f'recon_swarm_provider_calls_successful{{provider="{name}"}} {pm.calls_successful}')
        
        lines.append("")
        lines.append("# HELP recon_swarm_provider_success_rate Provider success rate")
        lines.append("# TYPE recon_swarm_provider_success_rate gauge")
        for name, pm in self._provider_metrics.items():
            lines.append(f'recon_swarm_provider_success_rate{{provider="{name}"}} {pm.success_rate:.3f}')
        
        lines.append("")
        lines.append("# HELP recon_swarm_provider_latency_avg_ms Average provider latency")
        lines.append("# TYPE recon_swarm_provider_latency_avg_ms gauge")
        for name, pm in self._provider_metrics.items():
            lines.append(f'recon_swarm_provider_latency_avg_ms{{provider="{name}"}} {pm.avg_latency_ms:.3f}')
        
        lines.append("")
        lines.append("# HELP recon_swarm_provider_latency_p95_ms P95 provider latency")
        lines.append("# TYPE recon_swarm_provider_latency_p95_ms gauge")
        for name, pm in self._provider_metrics.items():
            lines.append(f'recon_swarm_provider_latency_p95_ms{{provider="{name}"}} {pm.p95_latency_ms}')
        
        # Uptime
        lines.append("")
        lines.append("# HELP recon_swarm_uptime_seconds Total uptime")
        lines.append("# TYPE recon_swarm_uptime_seconds counter")
        uptime = time.monotonic() - self._started_at
        lines.append(f"recon_swarm_uptime_seconds {int(uptime)}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as dictionary.
        
        Returns:
            Dictionary with all metrics
        """
        total_cache = self._cache_hits + self._cache_misses
        
        return {
            "requests": {
                "total": self._total_requests,
                "avg_latency_ms": (
                    self._total_latency_ms / self._total_requests
                    if self._total_requests > 0 else 0
                ),
            },
            "cache": {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_ratio": (
                    self._cache_hits / total_cache if total_cache > 0 else 0
                ),
            },
            "circuit_breakers": {
                "opens_total": self._circuit_breaker_opens,
            },
            "providers": {
                name: {
                    "calls_total": pm.calls_total,
                    "calls_successful": pm.calls_successful,
                    "calls_failed": pm.calls_failed,
                    "success_rate": pm.success_rate,
                    "avg_latency_ms": pm.avg_latency_ms,
                    "p95_latency_ms": pm.p95_latency_ms,
                }
                for name, pm in self._provider_metrics.items()
            },
            "uptime_seconds": int(time.monotonic() - self._started_at),
        }
    
    def get_provider_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all provider metrics.
        
        Returns:
            List of provider metric summaries
        """
        return [
            {
                "name": pm.name,
                "calls_total": pm.calls_total,
                "success_rate": round(pm.success_rate, 3),
                "avg_latency_ms": round(pm.avg_latency_ms, 1),
                "p95_latency_ms": pm.p95_latency_ms,
                "last_error": pm.last_error,
            }
            for pm in sorted(
                self._provider_metrics.values(),
                key=lambda x: x.calls_total,
                reverse=True
            )
        ]
