# HireStack AI — Service Level Objectives (SLOs)

## Document Purpose

Defines measurable reliability and performance targets for the HireStack AI platform.
These SLOs inform alerting thresholds, architecture decisions, and incident severity.

---

## 1. Generation Pipeline SLOs

| Metric | Target | Measurement Window | Alert Threshold |
|--------|--------|-------------------|-----------------|
| **Sync generation latency** (p95) | ≤ 30 s | Rolling 1 h | > 35 s |
| **Stream first-event latency** (p95) | ≤ 5 s | Rolling 1 h | > 7 s |
| **Job start latency** (p95) | ≤ 2 s | Rolling 1 h | > 3 s |
| **Pipeline completion rate** | ≥ 99.5 % | Rolling 24 h | < 99 % |
| **Pipeline error rate** | ≤ 0.5 % | Rolling 24 h | > 1 % |

### Latency Budget Breakdown (Sync Mode, p95)

| Phase | Budget |
|-------|--------|
| Atlas (research) | 8 s |
| Cipher (benchmark) | 5 s |
| Quill (draft) | 6 s |
| Forge (generation) | 6 s |
| Sentinel (validation) | 3 s |
| Nova (learning plan) | 2 s |
| **Total** | **30 s** |

---

## 2. AI Provider SLOs

| Metric | Target | Notes |
|--------|--------|-------|
| **Provider availability** | ≥ 99.9 % | Measured via circuit breaker state |
| **Circuit breaker trip recovery** | ≤ 60 s | Time in OPEN state before HALF_OPEN |
| **Token budget per generation** | ≤ 150 000 tokens | Combined input + output |
| **Estimated cost per generation** | ≤ $0.25 | At current Gemini pricing |

---

## 3. API SLOs

| Metric | Target | Window |
|--------|--------|--------|
| **API availability** | ≥ 99.9 % | Rolling 30 d |
| **Health endpoint latency** (p99) | ≤ 200 ms | Rolling 1 h |
| **Auth endpoint latency** (p95) | ≤ 500 ms | Rolling 1 h |
| **Non-generation API latency** (p95) | ≤ 1 s | Rolling 1 h |

---

## 4. Evidence & Data SLOs

| Metric | Target | Notes |
|--------|--------|-------|
| **Evidence canonicalization latency** | ≤ 2 s | Per-job evidence promotion |
| **Contradiction detection latency** | ≤ 5 s | Full user evidence scan |
| **Evidence graph freshness** | ≤ 1 generation behind | Nodes updated after each generation |

---

## 5. Quality SLOs

| Metric | Target | Measurement |
|--------|--------|-------------|
| **ATS scan score** (mean) | ≥ 75 / 100 | From ATS scanner chain |
| **Validation pass rate** | ≥ 95 % | Sentinel stage pass on first attempt |
| **Evidence-backed claim ratio** | ≥ 80 % | Claims traceable to verbatim/derived evidence |

---

## 6. Error Budget Policy

- **Budget**: 0.5 % failure rate per rolling 24 h window (≈ 7.2 min downtime equivalent).
- **Exhausted budget actions**:
  1. Freeze non-critical deployments.
  2. Redirect engineering effort to reliability.
  3. Post-mortem within 48 h.
- **Budget reset**: Rolling window — budget naturally recovers as failures age out.

---

## 7. Measurement Implementation

SLO metrics are collected via:

- `backend/app/core/metrics.py` — `MetricsCollector` records stage timings, pipeline completion, token usage.
- `/health` endpoint — exposes circuit breaker state and aggregate metrics.
- Database logging — `generation_job_events` table for async job tracking.

### Percentile Calculation

```python
# MetricsCollector.get_stats() provides p50, p95, p99
stats = MetricsCollector.get().get_stats()
assert stats["pipeline_latency_p95"] <= 30.0  # SLO check
```

---

*Last updated: Phase 1 — C4 SLO definitions*
