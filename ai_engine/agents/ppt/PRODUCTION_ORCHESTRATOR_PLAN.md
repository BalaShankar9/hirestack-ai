# Production Orchestrator Implementation Plan

## Objective
Transform the basic PPT orchestrator into an enterprise-grade, production-ready system with comprehensive observability, resilience, and operational features.

## Success Criteria
- [ ] All 20 identified gaps resolved
- [ ] 10 improvement areas implemented
- [ ] Backward compatibility maintained
- [ ] Full test coverage
- [ ] Zero breaking changes to existing API

---

## Phase 1: Foundation & Core Infrastructure
**Goal**: Build the foundational classes and infrastructure

### Step 1.1: Create Status & Progress Types
**File**: `orchestrator.py` (add at top)
**What**: Create enums and dataclasses for tracking
**Code**:
```python
class GenerationStatus(Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RESEARCHING = "researching"
    ENHANCING = "enhancing"
    GENERATING_IMAGES = "generating_images"
    VALIDATING = "validating"
    COMPOSING = "composing"
    POLISHING = "polishing"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class GenerationProgress:
    status: GenerationStatus
    percent: int
    message: str
    phase: Optional[str] = None
    latency_so_far_ms: int = 0
```
**Validation**: Import works, enum values accessible

### Step 1.2: Enhance GenerationResult
**File**: `orchestrator.py`
**What**: Add observability fields to result
**Add to GenerationResult**:
```python
generation_id: str = ""
phase_latencies: Dict[str, int] = field(default_factory=dict)
cache_hit: bool = False
```
**Validation**: Dataclass remains frozen, new fields have defaults

### Step 1.3: Create CircuitBreaker Class
**File**: `orchestrator.py`
**What**: Resilience pattern for external APIs
**Implementation**:
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half-open
    
    def call(self, fn: Callable[[], Any]) -> Any:
        # Implementation with state machine
        pass
```
**Validation**: Unit test with 3 scenarios: success, failure threshold, recovery

---

## Phase 2: Caching Infrastructure
**Goal**: Implement result caching with TTL and LRU

### Step 2.1: Add Cache Fields to Orchestrator
**File**: `orchestrator.py` - `__init__` method
**Add**:
```python
self._enable_caching = enable_caching
self._cache_ttl = cache_ttl_seconds
self._cache: Dict[str, Tuple[GenerationResult, float]] = {}
```

### Step 2.2: Implement Cache Key Generation
**Method**: `_get_cache_key(**kwargs) -> str`
**Logic**:
- Sort parameters alphabetically
- Filter None values
- MD5 hash of "key=value|key=value"
**Validation**: Same params = same key, different params = different key

### Step 2.3: Implement Cache Get
**Method**: `_get_cached(key: str) -> Optional[GenerationResult]`
**Logic**:
- Check if key exists
- Check if expired (time.monotonic() - timestamp > ttl)
- Return None if expired (and remove from cache)
**Validation**: Returns result if valid, None if expired/missing

### Step 2.4: Implement Cache Set
**Method**: `_cache_result(key: str, result: GenerationResult)`
**Logic**:
- If cache size >= 100, evict oldest (LRU)
- Store (result, time.monotonic())
**Validation**: Cache stores correctly, eviction works at limit

### Step 2.5: Implement Cache Clear
**Method**: `clear_cache() -> int`
**Logic**:
- Count entries
- Clear dict
- Log count
- Return count
**Validation**: Returns correct count, cache empty after

---

## Phase 3: Concurrency & Resource Management
**Goal**: Prevent resource exhaustion under load

### Step 3.1: Add Semaphore to __init__
**File**: `orchestrator.py`
**Add**:
```python
import asyncio
self._semaphore = asyncio.Semaphore(max_concurrent_generations)
```
**Validation**: Semaphore created with correct initial value

### Step 3.2: Wrap Generate in Semaphore
**File**: `generate()` method
**Change**:
```python
async def generate(self, ...):
    # ... validation ...
    async with self._semaphore:
        return await self._execute_pipeline(...)
```
**Validation**: Multiple concurrent calls respect limit

### Step 3.3: Create Pipeline Execution Method
**Method**: `_execute_pipeline(...)` - extract from generate()
**Logic**: Move all execution logic here, generate() becomes entry point
**Validation**: Same behavior, semaphore wraps correctly

---

## Phase 4: Progress Tracking System
**Goal**: Real-time feedback during generation

### Step 4.1: Add Progress Callback Field
**File**: `__init__`
**Add**:
```python
self._progress_callback: Optional[Callable[[GenerationProgress], None]] = None
```

### Step 4.2: Implement Progress Reporter
**Method**: `_report_progress(status, percent, message, latency_so_far=0)`
**Logic**:
- If callback exists, call it
- Wrap in try/except (don't fail generation if callback fails)
**Validation**: Callback called with correct data, exceptions swallowed

### Step 4.3: Add Progress Points in Pipeline
**In _execute_pipeline**, add at:
1. Start: PLANNING, 5%, "Generating outline..."
2. After outline: Update based on pre-composition phases
3. Before composition: COMPOSING, 50%
4. After composition: Update based on post-composition phases
5. End: COMPLETED, 100%
6. On failure: FAILED, appropriate percent
**Validation**: Progress increments from 0 to 100, status changes appropriately

---

## Phase 5: Phase Latency Tracking
**Goal**: Per-phase performance metrics

### Step 5.1: Initialize Latency Tracker
**In _execute_pipeline**:
```python
phase_latencies: Dict[str, int] = {}
```

### Step 5.2: Time Each Phase
**Pattern for each phase**:
```python
phase_t0 = time.monotonic()
result = await phase.execute(...)
phase_latencies[phase_name] = int((time.monotonic() - phase_t0) * 1000)
```
**Apply to**:
- Outline generation
- Each pre-composition phase
- Composition
- Each post-composition phase

### Step 5.3: Include in Result
**When creating GenerationResult**:
```python
phase_latencies=phase_latencies
```
**Validation**: Result contains timing for all executed phases

---

## Phase 6: Input Validation & Safety
**Goal**: Prevent invalid inputs from reaching pipeline

### Step 6.1: Add Topic Validation
**In generate()**, after existing check:
```python
if len(topic.strip()) > 500:
    raise ValueError("topic must be under 500 characters")
```

### Step 6.2: Add Slide Count Validation
**In generate()**:
```python
if slide_count < 3 or slide_count > 30:
    raise ValueError("slide_count must be between 3 and 30")
```

### Step 6.3: Add Tone Validation
**In generate()**:
```python
valid_tones = {"professional", "casual", "formal", "friendly", None}
if tone not in valid_tones:
    raise ValueError(f"tone must be one of {valid_tones}")
```

### Step 6.4: Add Skip Cache Parameter
**Add to generate() signature**:
```python
skip_cache: bool = False
```
**Logic**: Check cache only if not skip_cache

---

## Phase 7: Generation ID & Tracing
**Goal**: Full traceability of each generation

### Step 7.1: Generate Unique ID
**In generate()**, after validation:
```python
import hashlib
generation_id = hashlib.md5(
    f"{topic}{time.monotonic()}".encode()
).hexdigest()[:12]
```

### Step 7.2: Pass ID Through Context
**In _execute_pipeline context**:
```python
context = {
    "topic": topic,
    "theme": theme,
    "generation_id": generation_id,
}
```

### Step 7.3: Include in Metadata & Result
**In result creation**:
```python
metadata={"generation_id": generation_id, ...}
generation_id=generation_id
```

---

## Phase 8: Structured Logging & Observability
**Goal**: Machine-parseable logs for monitoring

### Step 8.1: Update Success Log
**Replace existing log with**:
```python
logger.info(
    "presentation_generated: "
    "generation_id=%s topic=%s slides=%d size=%dKB "
    "latency=%dms quality=%.2f phases=%s",
    generation_id,
    topic[:60],
    deck.slide_count,
    len(pptx_bytes) // 1024,
    total_latency_ms,
    quality_score,
    phase_latencies,
)
```

### Step 8.2: Add Cache Hit Log
**When cache hit**:
```python
logger.info("cache_hit: generation_id=%s topic=%s", generation_id, topic[:40])
```

### Step 8.3: Add Cache Clear Log
**In clear_cache()**:
```python
logger.info("cache_cleared: entries=%d", count)
```

---

## Phase 9: Health Checks & Operations
**Goal**: Operational visibility and control

### Step 9.1: Implement Health Check Method
**Method**: `health_check() -> Dict[str, Any]`
**Return structure**:
```python
{
    "status": "healthy" | "degraded",
    "phases": {
        "outline": {"type": "OutlineGenerationPhase", "available": True},
        "pre_0": {"type": "DataResearchPhase", "available": True},
        ...
    },
    "circuit_breakers": {
        "data_research": "closed" | "open",
        ...
    },
    "cache": {
        "enabled": True,
        "size": 42
    }
}
```

### Step 9.2: Implement Metrics Method
**Method**: `get_metrics() -> Dict[str, Any]`
**Return**:
```python
{
    "cache": {"enabled": ..., "entries": ..., "ttl_seconds": ...},
    "concurrency": {"max_concurrent": ...},
    "circuit_breakers": {...},
    "phases": {"pre_composition_count": ..., "post_composition_count": ...}
}
```

### Step 9.3: Implement Circuit Breaker Access
**Method**: `_get_circuit_breaker(name: str) -> CircuitBreaker`
**Logic**: Lazy creation and storage in dict
**Validation**: Same name returns same instance

---

## Phase 10: Integration & Factory Updates
**Goal**: Wire everything together

### Step 10.1: Update Factory Method
**Add parameters to create_with_defaults()**:
```python
enable_caching: bool = True,
cache_ttl_seconds: float = 3600.0,
max_concurrent_generations: int = 5,
progress_callback: Optional[Callable[[GenerationProgress], None]] = None,
```

### Step 10.2: Pass Through to Constructor
**In return cls(...)**:
```python
enable_caching=enable_caching,
cache_ttl_seconds=cache_ttl_seconds,
max_concurrent_generations=max_concurrent_generations,
progress_callback=progress_callback,
```

### Step 10.3: Update Integration Layer
**File**: `integration.py`
**Update**: Use factory method with production parameters
**Change**: `orch = PresentationOrchestrator.create_with_defaults(...)`

---

## Phase 11: Exports & Public API
**Goal**: Make new features accessible

### Step 11.1: Update __init__.py Imports
**Add**:
```python
from ai_engine.agents.ppt.orchestrator import (
    PresentationOrchestrator,
    GenerationResult,
    GenerationStatus,
    GenerationProgress,
    CircuitBreaker,
    PPTOrchestrator,
    PPTResult,
)
```

### Step 11.2: Update __all__
**Add to __all__**:
```python
"PresentationOrchestrator",
"GenerationResult",
"GenerationStatus",
"GenerationProgress",
"CircuitBreaker",
"PPTOrchestrator",
"PPTResult",
```

---

## Phase 12: Validation & Testing
**Goal**: Verify everything works

### Step 12.1: Syntax Check
```bash
python3 -m py_compile orchestrator.py
python3 -m py_compile __init__.py
python3 -m py_compile integration.py
```

### Step 12.2: Import Test
```python
from ai_engine.agents.ppt import (
    PresentationOrchestrator,
    GenerationStatus,
    GenerationProgress,
    CircuitBreaker,
)
```

### Step 12.3: Basic Usage Test
```python
orch = PresentationOrchestrator.create_with_defaults()
# Verify all new methods exist
assert hasattr(orch, 'health_check')
assert hasattr(orch, 'get_metrics')
assert hasattr(orch, 'clear_cache')
```

---

## Milestone Checklist

### Milestone 1: Foundation Complete
- [ ] GenerationStatus enum created
- [ ] GenerationProgress dataclass created
- [ ] GenerationResult enhanced
- [ ] CircuitBreaker class created

### Milestone 2: Caching Complete
- [ ] Cache fields added
- [ ] _get_cache_key implemented
- [ ] _get_cached implemented
- [ ] _cache_result implemented
- [ ] clear_cache implemented

### Milestone 3: Concurrency Complete
- [ ] Semaphore added
- [ ] _execute_pipeline extracted
- [ ] Generate wrapped in semaphore

### Milestone 4: Progress Tracking Complete
- [ ] Progress callback field added
- [ ] _report_progress implemented
- [ ] Progress points in pipeline

### Milestone 5: Observability Complete
- [ ] Phase latency tracking
- [ ] Generation ID generation
- [ ] Structured logging
- [ ] Health check method
- [ ] Metrics method

### Milestone 6: Validation Complete
- [ ] Input validation added
- [ ] skip_cache parameter
- [ ] Factory method updated

### Milestone 7: Integration Complete
- [ ] Exports updated
- [ ] Integration layer updated
- [ ] All syntax valid

---

## Execution Order

**Start with Phase 1** → Phase 2 → Phase 3 → ... → Phase 12

**Do NOT skip phases**. Each builds on previous.

**After each phase**: Run syntax check

**After each milestone**: Verify milestone checklist

---

## Estimated Effort

| Phase | Lines | Time |
|-------|-------|------|
| Phase 1 | ~60 | 15 min |
| Phase 2 | ~80 | 20 min |
| Phase 3 | ~30 | 10 min |
| Phase 4 | ~50 | 15 min |
| Phase 5 | ~40 | 10 min |
| Phase 6 | ~30 | 10 min |
| Phase 7 | ~20 | 5 min |
| Phase 8 | ~20 | 5 min |
| Phase 9 | ~80 | 20 min |
| Phase 10 | ~30 | 10 min |
| Phase 11 | ~20 | 5 min |
| Phase 12 | ~0 | 10 min |
| **Total** | **~460** | **~2.5 hours** |

---

## Final Deliverables

1. `orchestrator.py` - Production-ready orchestrator (~1100 lines)
2. `__init__.py` - Updated exports
3. `integration.py` - Updated integration
4. `PRODUCTION_ORCHESTRATOR_PLAN.md` - This plan (documentation)
5. `ORCHESTRATOR_IMPROVEMENTS.md` - Summary of improvements

**Backward Compatibility**: `PPTOrchestrator` and `PPTResult` aliases maintained
