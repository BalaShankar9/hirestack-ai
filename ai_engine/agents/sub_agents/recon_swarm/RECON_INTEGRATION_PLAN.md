# Recon Swarm Integration & Streaming Implementation Plan

## Current State Analysis

### ✅ Already Implemented
1. **Free Providers** (free_providers.py, free_mode.py) - 7 free data sources
2. **Production Infrastructure**:
   - CircuitBreaker, RateLimiter, ResilientProvider (resilience.py)
   - ProviderHealthTracker (health.py)
   - ProviderCache (cache.py)
   - QualityScorer (quality.py)
   - ReconMetrics (metrics.py)
3. **Exports** (__init__.py) - All classes exported

### ❌ Not Yet Integrated
1. **Coordinator doesn't use production features**
   - No circuit breakers on provider calls
   - No rate limiting
   - No health tracking
   - No per-provider caching
   - No quality scoring on output
   - No metrics collection

2. **No Streaming Support**
   - Coordinator returns final result only
   - No progress callbacks
   - No AsyncGenerator for real-time updates
   - Frontend has to poll

3. **Free Mode Not Wired In**
   - FreeModeRecon exists but not integrated with main coordinator
   - No way to choose "free mode" vs "full mode"

4. **Missing API Endpoints**
   - No streaming endpoint
   - No health/status endpoint
   - No metrics export endpoint

---

## Implementation Plan

### Phase 1: Streaming Architecture

#### 1.1 Define Streaming Types
```python
@dataclass
class ReconProgressUpdate:
    """Real-time progress update for streaming."""
    layer: int  # 1-5
    phase: str  # "source_discovery", "fusion", etc.
    status: str  # "running", "completed", "failed"
    percent: int  # 0-100 overall
    message: str
    providers_completed: int
    providers_total: int
    fields_discovered: int
    latency_ms: int
    metadata: Dict[str, Any]
```

#### 1.2 Create AsyncGenerator Coordinator
```python
async def run_streaming(self, request: ReconSwarmRequest) -> AsyncGenerator[ReconProgressUpdate, None]:
    """Yield progress updates, then final report."""
```

### Phase 2: Production Integration

#### 2.1 Enhanced Coordinator Init
```python
class ReconSwarmCoordinator:
    def __init__(
        self,
        *,
        # Existing params
        ai_client=None,
        layer1=None,
        layer2=None,
        cache=None,
        # NEW: Production features
        enable_resilience: bool = True,
        enable_health_tracking: bool = True,
        enable_metrics: bool = True,
        enable_provider_cache: bool = True,
        # NEW: Streaming
        progress_callback: Optional[Callable[[ReconProgressUpdate], None]] = None,
        # NEW: Mode selection
        mode: Literal["auto", "free", "full"] = "auto",
    )
```

#### 2.2 Wrap Providers with Resilience
```python
# Each provider wrapped with CircuitBreaker + RateLimiter
self._resilient_providers = {
    p.name: ResilientProvider(
        provider=p,
        circuit_breaker=circuit_breakers[p.name],
        rate_limiter=rate_limiters[p.name],
    )
    for p in all_providers
}
```

#### 2.3 Add Health & Metrics Tracking
```python
# After each provider call
await self.health_tracker.record(name, success, latency_ms)
self.metrics.record_provider_call(name, latency_ms, success)
```

### Phase 3: Free Mode Integration

#### 3.1 Auto Mode Selection
```python
if mode == "auto":
    # Check for API keys, fallback to free if none
    has_keys = bool(os.getenv("CRUNCHBASE_API_KEY") or ...)
    effective_mode = "full" if has_keys else "free"
```

#### 3.2 Unified Interface
```python
# Same interface works for both modes
report = await coordinator.run(request)  # Works in free or full mode
```

### Phase 4: API Layer

#### 4.1 Streaming SSE Endpoint
```python
@router.get("/profile/stream")
async def profile_stream(request: ReconSwarmRequest):
    async def event_generator():
        async for update in coordinator.run_streaming(request):
            yield f"data: {json.dumps(update.to_dict())}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

#### 4.2 Health & Metrics Endpoints
```python
@router.get("/health")
async def health() -> ProviderHealthSnapshot

@router.get("/metrics")
async def metrics() -> str  # Prometheus format
```

---

## Gaps Identified

### Critical Gaps (Must Fix)
1. **No Streaming**: Frontend cannot show real-time progress
2. **No Resilience Applied**: Provider failures not handled gracefully
3. **No Health Visibility**: Can't tell which providers are working
4. **No Metrics**: No observability into performance

### Important Gaps (Should Fix)
5. **Free Mode Not Default**: Should auto-detect and use free mode
6. **No Partial Results**: Can't return partial intel if budget exceeded
7. **No Provider Selection**: Can't prioritize working providers
8. **No Request Deduplication**: Same requests run multiple times

### Nice-to-Have (Future)
9. **No WebSocket Support**: SSE only, no bidirectional
10. **No Batch Requests**: Can't research multiple companies efficiently
11. **No Caching Strategy**: TTL only, no LRU/invalidation strategy
12. **No A/B Testing**: Can't compare provider combinations

---

## Implementation Priority

```
P0 (Critical):
  ☐ 1. Streaming AsyncGenerator for coordinator
  ☐ 2. Integrate CircuitBreaker into provider calls
  ☐ 3. Add progress callback support

P1 (Important):
  ☐ 4. Wire up FreeModeRecon as default when no keys
  ☐ 5. Add health tracking to provider calls
  ☐ 6. Add metrics collection
  ☐ 7. Streaming SSE API endpoint

P2 (Enhancement):
  ☐ 8. Per-provider caching
  ☐ 9. Provider priority/selection based on health
  ☐ 10. Request deduplication
  ☐ 11. Health & metrics API endpoints

P3 (Future):
  ☐ 12. WebSocket support
  ☐ 13. Batch operations
  ☐ 14. Advanced caching strategies
```

---

## Success Criteria

1. **Streaming Works**: Frontend receives layer-by-layer updates
2. **Resilience Active**: Failed providers auto-skip, circuit breakers trip
3. **Free Mode Default**: Works out-of-box with no API keys
4. **Observable**: Prometheus metrics + health dashboard visible
5. **Backward Compatible**: Existing `run()` method still works
