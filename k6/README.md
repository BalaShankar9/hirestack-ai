# HireStack AI — K6 Load Tests

## Prerequisites

```bash
brew install k6
```

## Running Tests

```bash
# Smoke test (sanity check, 1-3 VUs)
k6 run k6/scenarios/smoke.js

# Load test (50 concurrent users, 5 min sustained)
k6 run k6/scenarios/load.js

# Stress test (ramp to 200 concurrent, find breaking point)
k6 run k6/scenarios/stress.js

# Spike test (sudden burst of 500 users)
k6 run k6/scenarios/spike.js

# Soak test (50 users for 30 min, detect memory leaks)
k6 run k6/scenarios/soak.js
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BASE_URL` | No | `http://localhost:8000` | Backend base URL |
| `AUTH_TOKEN` | **Yes** | — | Valid Supabase JWT for authenticated endpoints |
| `AUTH_TOKEN_2` | No | — | Second user token (for multi-user scenarios) |

```bash
export BASE_URL=http://localhost:8000
export AUTH_TOKEN="eyJhbG..."
k6 run k6/scenarios/load.js
```

## SLO Thresholds

All scenarios enforce these production SLOs:

| Metric | Threshold |
|--------|-----------|
| HTTP error rate | < 1% |
| p95 latency (reads) | < 500ms |
| p95 latency (writes) | < 1500ms |
| p95 latency (AI generation) | < 30s |
| p99 latency (all) | < 5s |

## Output

```bash
# JSON output for dashboards
k6 run --out json=results.json k6/scenarios/load.js

# InfluxDB for Grafana
k6 run --out influxdb=http://localhost:8086/k6 k6/scenarios/load.js
```
