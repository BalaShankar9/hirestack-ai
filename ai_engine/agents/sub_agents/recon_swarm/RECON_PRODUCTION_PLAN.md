# Recon Swarm Production Implementation Plan

## Objective
Transform the Recon Swarm agent from a basic 5-layer pipeline to an enterprise-grade, production-ready intelligence engine with circuit breakers, rate limiting, health monitoring, and operational observability.

## Success Criteria
- [ ] All 12 critical gaps resolved (Circuit Breakers, Rate Limiting, Health Monitoring, etc.)
- [ ] Zero breaking changes to existing API
- [ ] Full backward compatibility maintained
- [ ] All existing tests pass
- [ ] New features covered by tests

---

## Phase 1: Foundation - Resilience Infrastructure
**Goal**: Build circuit breakers and rate limiting foundation

### Step 1.1: Create CircuitBreaker Class
**File**: `ai_engine/agents/sub_agents/recon_swarm/resilience.py` (NEW FILE)
**Implementation**:
```python
class CircuitBreaker:
    """Circuit breaker for external provider calls."""
    
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
        
        self._state = "closed"  # closed, open, half-open
        self._failures = 0
        self._successes = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> str:
        return self._state
    
    async def call(self, fn: Callable[[], T]) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self._state == "open":
                if self._should_attempt_reset():
                    self._state = "half-open"
                    self._successes = 0
                else:
                    raise CircuitBreakerOpen(f"Circuit {self.name} is OPEN")
            
            if self._state == "half-open" and self._successes >= self.half_open_max_calls:
                raise CircuitBreakerOpen(f"Circuit {self.name} is HALF-OPEN (max calls reached)")
        
        try:
            result = await fn()
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        async with self._lock:
            self._failures = 0
            if self._state == "half-open":
                self._successes += 1
                if self._successes >= self.half_open_max_calls:
                    self._state = "closed"
                    logger.info(f"Circuit {self.name} CLOSED (recovered)")
    
    async def _on_failure(self):
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.monotonic()
            if self._state == "half-open":
                self._state = "open"
                logger.warning(f"Circuit {self.name} OPEN (failure in half-open)")
            elif self._failures >= self.failure_threshold:
                self._state = "open"
                logger.warning(f"Circuit {self.name} OPEN ({self._failures} failures)")
    
    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        return (time.monotonic() - self._last_failure_time) >= self.recovery_timeout


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass
```
**Validation**: Unit test with 3 scenarios: success path, failure threshold, recovery

### Step 1.2: Create RateLimiter Class
**File**: `ai_engine/agents/sub_agents/recon_swarm/resilience.py`
**Implementation**:
```python
class RateLimiter:
    """Token bucket rate limiter for API calls."""
    
    def __init__(self, requests_per_minute: float, burst_size: Optional[int] = None):
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.burst = burst_size or int(requests_per_minute / 6)  # 10-second burst
        self._tokens = self.burst
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens. Returns wait time."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_update = now
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            
            # Need to wait
            needed = tokens - self._tokens
            wait_time = needed / self.rate
            self._tokens = 0
            return wait_time
    
    async def __aenter__(self):
        wait = await self.acquire()
        if wait > 0:
            await asyncio.sleep(wait)
        return self
    
    async def __aexit__(self, *args):
        pass
```
**Validation**: Unit test with burst and sustained rate scenarios

### Step 1.3: Create ProviderResilience Wrapper
**File**: `ai_engine/agents/sub_agents/recon_swarm/resilience.py`
**Implementation**:
```python
@dataclass
class ProviderResilienceConfig:
    """Configuration for provider resilience features."""
    circuit_breaker: Optional[CircuitBreaker] = None
    rate_limiter: Optional[RateLimiter] = None
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_delay: float = 0.5


class ResilientProvider:
    """Wraps a provider with circuit breaker and rate limiting."""
    
    def __init__(
        self,
        provider: SourceProvider,
        config: ProviderResilienceConfig,
    ):
        self._provider = provider
        self._config = config
        self.name = provider.name
        self.layer = provider.layer
    
    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        """Fetch with resilience patterns applied."""
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
                
                return result
                
            except CircuitBreakerOpen:
                # Fast fail - don't retry if circuit is open
                return ProviderResult(
                    provider=self.name,
                    layer=self.layer,
                    success=False,
                    latency_ms=int((time.perf_counter() - provider_started) * 1000),
                    error=f"Circuit breaker open for {self.name}",
                )
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"Provider {self.name} timeout (attempt {attempt})")
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {self.name} error (attempt {attempt}): {e}")
            
            if attempt < self._config.max_retries:
                await asyncio.sleep(self._config.retry_delay * attempt)  # Exponential backoff
        
        return ProviderResult(
            provider=self.name,
            layer=self.layer,
            success=False,
            latency_ms=int((time.perf_counter() - provider_started) * 1000),
            error=str(last_error)[:200] if last_error else "unknown",
        )
    
    async def _do_fetch(self, company: str, **ctx: Any) -> ProviderResult:
        """Actual fetch with timeout."""
        return await asyncio.wait_for(
            self._provider.fetch(company=company, **ctx),
            timeout=self._config.timeout_seconds,
        )
```
**Validation**: Integration test with mock provider

---

## Phase 2: Provider Health Monitoring
**Goal**: Add health checks and metrics tracking

### Step 2.1: Create ProviderHealthTracker Class
**File**: `ai_engine/agents/sub_agents/recon_swarm/health.py` (NEW FILE)
**Implementation**:
```python
@dataclass
class ProviderHealth:
    """Health status for a single provider."""
    name: str
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    success_rate_1h: float
    avg_latency_ms: int
    p95_latency_ms: int
    last_error: Optional[str]
    last_success_at: Optional[str]  # ISO timestamp
    consecutive_failures: int
    total_calls_1h: int


class ProviderHealthTracker:
    """Track provider health metrics over time."""
    
    def __init__(self, window_minutes: int = 60):
        self._window = window_minutes
        self._calls: Dict[str, List[Tuple[float, bool, int]]] = {}  # (time, success, latency_ms)
        self._lock = asyncio.Lock()
    
    async def record(self, provider_name: str, success: bool, latency_ms: int):
        """Record a provider call result."""
        async with self._lock:
            if provider_name not in self._calls:
                self._calls[provider_name] = []
            self._calls[provider_name].append((time.monotonic(), success, latency_ms))
            # Clean old entries
            cutoff = time.monotonic() - (self._window * 60)
            self._calls[provider_name] = [
                c for c in self._calls[provider_name] if c[0] > cutoff
            ]
    
    async def get_health(self, provider_name: str) -> ProviderHealth:
        """Get health status for a provider."""
        async with self._lock:
            calls = self._calls.get(provider_name, [])
            if not calls:
                return ProviderHealth(
                    name=provider_name,
                    status="unknown",
                    success_rate_1h=0.0,
                    avg_latency_ms=0,
                    p95_latency_ms=0,
                    last_error=None,
                    last_success_at=None,
                    consecutive_failures=0,
                    total_calls_1h=0,
                )
            
            total = len(calls)
            successes = sum(1 for _, s, _ in calls if s)
            latencies = [l for _, _, l in calls]
            
            # Calculate consecutive failures (most recent)
            consecutive_failures = 0
            for _, success, _ in reversed(calls):
                if not success:
                    consecutive_failures += 1
                else:
                    break
            
            # Determine status
            success_rate = successes / total if total > 0 else 0.0
            if success_rate >= 0.95 and consecutive_failures == 0:
                status = "healthy"
            elif success_rate >= 0.80:
                status = "degraded"
            else:
                status = "unhealthy"
            
            return ProviderHealth(
                name=provider_name,
                status=status,
                success_rate_1h=round(success_rate, 3),
                avg_latency_ms=int(sum(latencies) / len(latencies)) if latencies else 0,
                p95_latency_ms=int(sorted(latencies)[int(len(latencies) * 0.95)]) if latencies else 0,
                last_error=None,  # Would need separate error tracking
                last_success_at=None,  # Would need to track
                consecutive_failures=consecutive_failures,
                total_calls_1h=total,
            )
    
    async def get_all_health(self) -> Dict[str, ProviderHealth]:
        """Get health for all tracked providers."""
        async with self._lock:
            return {
                name: await self.get_health(name)
                for name in self._calls.keys()
            }
```
**Validation**: Test with simulated call history

---

## Phase 3: Concurrent Limiting & Request Deduplication
**Goal**: Prevent resource exhaustion and duplicate work

### Step 3.1: Add Semaphore to Coordinator
**File**: `coordinator_v2.py`
**Changes**:
```python
class ReconSwarmCoordinator:
    def __init__(...):
        # Existing code...
        self._provider_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent providers
        self._inflight_requests: Dict[str, asyncio.Event] = {}  # For deduplication
        self._health_tracker = ProviderHealthTracker()
```

### Step 3.2: Add Request Deduplication
**Method**: `_deduplicate_request(key: str) -> Tuple[bool, Optional[ReconSwarmReport]]`
**Logic**:
- Check if key in `_inflight_requests`
- If yes, wait on the event and return cached result
- If no, create event, proceed, signal event when done

### Step 3.3: Wrap Provider Calls with Semaphore
**Modify** `_run_provider`:
```python
async def _run_provider(self, ...):
    async with self._provider_semaphore:
        # Existing logic...
```

---

## Phase 4: Provider Caching (Per-Provider)
**Goal**: Cache provider results to avoid redundant API calls

### Step 4.1: Create ProviderCache Class
**File**: `cache.py` (Extend existing)
**Implementation**:
```python
class ProviderCache:
    """Cache for individual provider results."""
    
    def __init__(self, default_ttl_s: float = 3600, max_size: int = 1000):
        self._cache: Dict[str, Tuple[ProviderResult, float]] = {}
        self._default_ttl = default_ttl_s
        self._max_size = max_size
        self._lock = asyncio.Lock()
    
    def _make_key(self, provider: str, company: str, **ctx) -> str:
        """Create cache key from provider + company + context."""
        key_data = f"{provider}:{company}:{sorted(ctx.items())}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
    
    async def get(self, provider: str, company: str, **ctx) -> Optional[ProviderResult]:
        """Get cached result if valid."""
        async with self._lock:
            key = self._make_key(provider, company, **ctx)
            if key not in self._cache:
                return None
            result, expires = self._cache[key]
            if time.monotonic() > expires:
                del self._cache[key]
                return None
            return result
    
    async def set(
        self,
        provider: str,
        company: str,
        result: ProviderResult,
        ttl_s: Optional[float] = None,
        **ctx,
    ):
        """Cache provider result."""
        async with self._lock:
            # LRU eviction if at capacity
            if len(self._cache) >= self._max_size:
                oldest = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest]
            
            key = self._make_key(provider, company, **ctx)
            ttl = ttl_s or self._default_ttl
            self._cache[key] = (result, time.monotonic() + ttl)
    
    async def invalidate(self, provider: Optional[str] = None, company: Optional[str] = None):
        """Invalidate cache entries."""
        async with self._lock:
            if provider is None and company is None:
                self._cache.clear()
                return
            
            to_delete = []
            for key, (result, _) in self._cache.items():
                if provider and result.provider == provider:
                    to_delete.append(key)
                elif company and company.lower() in key.lower():
                    to_delete.append(key)
            
            for key in to_delete:
                del self._cache[key]
```

---

## Phase 5: Provider Priority & Selection
**Goal**: Smart provider selection based on company signals

### Step 5.1: Create ProviderSelector Class
**File**: `coordinator_v2.py` or new `selection.py`
**Implementation**:
```python
@dataclass
class ProviderConfig:
    """Configuration for provider selection."""
    name: str
    priority: int = 10  # Lower = higher priority
    weight: float = 1.0  # Fusion weight
    required: bool = False  # Fail layer if this fails
    company_types: List[str] = field(default_factory=list)  # "startup", "public", "enterprise"
    min_budget_seconds: float = 0.0  # Skip if budget below this


class ProviderSelector:
    """Select and order providers based on company signals."""
    
    def __init__(self, configs: Dict[str, ProviderConfig]):
        self._configs = configs
    
    def select(
        self,
        providers: List[SourceProvider],
        company: str,
        signals: Dict[str, Any],
        remaining_budget: float,
    ) -> List[SourceProvider]:
        """Select and order providers for a company."""
        selected = []
        
        for provider in providers:
            config = self._configs.get(provider.name, ProviderConfig(name=provider.name))
            
            # Check budget constraint
            if remaining_budget < config.min_budget_seconds:
                continue
            
            # Check company type match
            if config.company_types:
                company_type = self._detect_company_type(signals)
                if company_type not in config.company_types:
                    continue
            
            selected.append((provider, config))
        
        # Sort by priority
        selected.sort(key=lambda x: x[1].priority)
        return [p for p, _ in selected]
    
    def _detect_company_type(self, signals: Dict[str, Any]) -> str:
        """Detect company type from signals."""
        if signals.get("is_public"):
            return "public"
        if signals.get("total_funding_usd", 0) > 0 and signals.get("total_funding_usd", 0) < 50_000_000:
            return "startup"
        if signals.get("headcount", 0) > 1000:
            return "enterprise"
        return "private"
```

---

## Phase 6: Streaming & Partial Results
**Goal**: Better UX with real-time updates

### Step 6.1: Create Streaming Types
**File**: `schemas.py` (Add to existing)
**Implementation**:
```python
class ReconUpdate(BaseModel):
    """Streaming update during recon execution."""
    model_config = ConfigDict(extra="ignore")
    
    update_type: Literal[
        "provider_started",
        "provider_completed",
        "provider_failed",
        "layer_completed",
        "fusion_started",
        "fusion_progress",
        "fusion_completed",
        "mapper_completed",
        "partial_result",
        "completed",
        "failed",
    ]
    timestamp: float
    message: str
    progress_percent: int = 0
    
    # Optional details
    provider_name: Optional[str] = None
    layer: Optional[int] = None
    latency_ms: Optional[int] = None
    partial_intel: Optional[CompanyIntelV2] = None
    error: Optional[str] = None


class ReconSwarmReportV2(ReconSwarmReport):
    """Extended report with partial result support."""
    partial: bool = False
    stopped_at_layer: Optional[int] = None
    layers_attempted: List[int] = Field(default_factory=list)
```

### Step 6.2: Add Streaming Method to Coordinator
**Method**: `run_streaming(request) -> AsyncGenerator[ReconUpdate, None]`
**Implementation**:
- Yield updates after each provider
- Yield progress during fusion
- Yield partial intel if stopped early

---

## Phase 7: Quality Scoring
**Goal**: Overall report quality metric

### Step 7.1: Create QualityScorer Class
**File**: `quality.py` (NEW FILE)
**Implementation**:
```python
class QualityScorer:
    """Score the quality of recon reports."""
    
    def score(self, report: ReconSwarmReport) -> Dict[str, Any]:
        """Calculate quality scores for a report."""
        intel = report.intel
        
        # Completeness (0-1)
        completeness = intel.profile_completeness
        
        # Confidence (0-1)
        all_fields = [
            getattr(intel, f) for f in dir(intel)
            if isinstance(getattr(intel, f), IntelField)
        ]
        high_confidence_ratio = sum(
            1 for f in all_fields if f.confidence == "high"
        ) / len(all_fields) if all_fields else 0
        
        # Source diversity (0-1)
        sources = set()
        for field in all_fields:
            sources.update(field.sources)
        source_diversity = min(len(sources) / 5, 1.0)  # Max at 5+ sources
        
        # Provider success rate
        provider_success = sum(
            1 for p in report.provider_results if p.success
        ) / len(report.provider_results) if report.provider_results else 0
        
        # Overall score (weighted)
        overall = (
            completeness * 0.3 +
            high_confidence_ratio * 0.3 +
            source_diversity * 0.2 +
            provider_success * 0.2
        )
        
        # Reliability tier
        if overall >= 0.8 and completeness >= 0.7:
            tier = "high"
        elif overall >= 0.5:
            tier = "medium"
        else:
            tier = "low"
        
        return {
            "overall_score": round(overall, 3),
            "completeness": round(completeness, 3),
            "confidence_ratio": round(high_confidence_ratio, 3),
            "source_diversity": round(source_diversity, 3),
            "provider_success_rate": round(provider_success, 3),
            "reliability_tier": tier,
        }
```

---

## Phase 8: Metrics & Observability
**Goal**: Production monitoring and alerting

### Step 8.1: Create MetricsExporter Class
**File**: `metrics.py` (NEW FILE)
**Implementation**:
```python
class ReconMetrics:
    """Metrics for recon swarm monitoring."""
    
    def __init__(self):
        self._provider_latency: Dict[str, List[float]] = {}
        self._provider_success: Dict[str, List[bool]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._circuit_breaker_opens = 0
        self._total_requests = 0
    
    def record_provider_call(self, name: str, latency_ms: float, success: bool):
        if name not in self._provider_latency:
            self._provider_latency[name] = []
            self._provider_success[name] = []
        self._provider_latency[name].append(latency_ms)
        self._provider_success[name].append(success)
        # Keep last 1000 entries
        self._provider_latency[name] = self._provider_latency[name][-1000:]
        self._provider_success[name] = self._provider_success[name][-1000:]
    
    def record_cache_hit(self):
        self._cache_hits += 1
    
    def record_cache_miss(self):
        self._cache_misses += 1
    
    def record_circuit_breaker_open(self):
        self._circuit_breaker_opens += 1
    
    def record_request(self):
        self._total_requests += 1
    
    def to_prometheus(self) -> str:
        """Export as Prometheus text format."""
        lines = []
        lines.append("# HELP recon_swarm_requests_total Total recon requests")
        lines.append("# TYPE recon_swarm_requests_total counter")
        lines.append(f"recon_swarm_requests_total {self._total_requests}")
        
        lines.append("# HELP recon_swarm_cache_hit_ratio Cache hit ratio")
        lines.append("# TYPE recon_swarm_cache_hit_ratio gauge")
        total = self._cache_hits + self._cache_misses
        ratio = self._cache_hits / total if total > 0 else 0
        lines.append(f"recon_swarm_cache_hit_ratio {ratio:.3f}")
        
        for provider, latencies in self._provider_latency.items():
            if latencies:
                avg = sum(latencies) / len(latencies)
                lines.append(f'recon_swarm_provider_latency_avg{{provider="{provider}"}} {avg:.3f}')
        
        for provider, successes in self._provider_success.items():
            if successes:
                rate = sum(successes) / len(successes)
                lines.append(f'recon_swarm_provider_success_rate{{provider="{provider}"}} {rate:.3f}')
        
        return "\\n".join(lines)
```

---

## Phase 9: Integration & Exports
**Goal**: Wire everything together

### Step 9.1: Update __init__.py
**Add exports**:
```python
from .resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    RateLimiter,
    ResilientProvider,
    ProviderResilienceConfig,
)
from .health import ProviderHealth, ProviderHealthTracker
from .quality import QualityScorer
from .metrics import ReconMetrics
```

### Step 9.2: Update Coordinator Integration
**Modify** `ReconSwarmCoordinator.__init__`:
```python
def __init__(...):
    # Existing code...
    
    # Production features
    self._provider_semaphore = asyncio.Semaphore(5)
    self._inflight_requests: Dict[str, asyncio.Event] = {}
    self._health_tracker = ProviderHealthTracker()
    self._provider_cache = ProviderCache()
    self._metrics = ReconMetrics()
    self._quality_scorer = QualityScorer()
    
    # Provider resilience configs
    self._resilience_configs = self._default_resilience_configs()
```

### Step 9.3: Create Helper Methods
**Methods to add**:
- `get_health()` → Returns health for all providers
- `get_metrics()` → Returns metrics dict
- `invalidate_cache(company)` → Invalidate cache for company
- `run_streaming(request)` → Streaming version of run

---

## Phase 10: Testing & Validation
**Goal**: Verify everything works

### Step 10.1: Unit Tests
**Create** `tests/unit/test_resilience.py`:
- Test circuit breaker state transitions
- Test rate limiting
- Test resilient provider wrapper

### Step 10.2: Integration Tests
**Create** `tests/unit/test_health.py`:
- Test health tracking
- Test provider selection
- Test caching

### Step 10.3: Syntax Validation
```bash
python3 -m py_compile resilience.py health.py quality.py metrics.py
python3 -m py_compile coordinator_v2.py
python3 -c "from ai_engine.agents.sub_agents.recon_swarm import *"
```

---

## Milestone Checklist

### Milestone 1: Resilience Complete ✅
- [ ] CircuitBreaker class
- [ ] RateLimiter class
- [ ] ResilientProvider wrapper
- [ ] Unit tests pass

### Milestone 2: Health Monitoring Complete ✅
- [ ] ProviderHealthTracker class
- [ ] Health status calculation
- [ ] Integration with coordinator

### Milestone 3: Concurrency & Caching Complete ✅
- [ ] Semaphore limiting
- [ ] Request deduplication
- [ ] Per-provider caching

### Milestone 4: Selection & Quality Complete ✅
- [ ] ProviderSelector class
- [ ] Priority-based ordering
- [ ] QualityScorer class

### Milestone 5: Streaming & Metrics Complete ✅
- [ ] ReconUpdate types
- [ ] Streaming method
- [ ] Metrics exporter
- [ ] Prometheus format

### Milestone 6: Integration Complete ✅
- [ ] All new exports
- [ ] Coordinator integration
- [ ] Helper methods exposed
- [ ] Syntax valid

---

## Execution Order

**Start with Phase 1** → Phase 2 → Phase 3 → ... → Phase 10

**Do NOT skip phases. Each builds on previous.**

**After each phase**: Run syntax check
**After each milestone**: Run tests

---

## Estimated Effort

| Phase | Files | Lines | Time |
|-------|-------|-------|------|
| Phase 1 | 1 new | ~200 | 30 min |
| Phase 2 | 1 new | ~150 | 25 min |
| Phase 3 | 1 modify | ~50 | 15 min |
| Phase 4 | 1 modify | ~80 | 20 min |
| Phase 5 | 1 new | ~120 | 25 min |
| Phase 6 | 1 modify | ~100 | 25 min |
| Phase 7 | 1 new | ~80 | 20 min |
| Phase 8 | 1 new | ~100 | 20 min |
| Phase 9 | 2 modify | ~50 | 15 min |
| Phase 10 | 3 new | ~200 | 30 min |
| **Total** | **9 files** | **~1130** | **~4 hours** |

---

## Deliverables

1. `resilience.py` - Circuit breakers & rate limiting
2. `health.py` - Provider health tracking
3. `quality.py` - Report quality scoring
4. `metrics.py` - Prometheus metrics export
5. Updated `coordinator_v2.py` - Integrated features
6. Updated `__init__.py` - New exports
7. Test files - Full coverage

---

## Success Metrics

After implementation:
- **Provider failure rate**: < 1% (was ~5%)
- **Average latency**: -40% (caching + smarter selection)
- **Circuit breaker activations**: Tracked and alerted
- **Cache hit ratio**: > 30% for repeated companies
- **Quality score distribution**: 80% reports rated "high" or "medium"
