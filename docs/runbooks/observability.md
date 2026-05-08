# Observability — OpenTelemetry + Langfuse

PR m4-pr12 wires two **optional** observability surfaces:

| Surface | Captures | Activated by |
|---|---|---|
| OpenTelemetry (OTLP HTTP) | FastAPI requests, outbound httpx calls | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| Langfuse | Per-LLM-call traces (model, latency, errors) | `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` |

Both are **off by default** and degrade silently if the relevant env vars or Python packages are missing.

---

## 1. Local Langfuse stack

```bash
docker compose -f infra/observability/docker-compose.langfuse.yml up -d
open http://localhost:3000
```

Sign up, create a project, copy the public/secret keys, then add to `backend/.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000   # omit for cloud
```

Restart the backend. Every Gemini call from `ai_engine.client._GeminiProvider._generate_content_throttled` now appears as a span in Langfuse.

## 2. OpenTelemetry traces

Point at any OTLP/HTTP collector (Jaeger, Tempo, Honeycomb, etc.):

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
OTEL_SERVICE_NAME=hirestack-backend   # optional, defaults to this
```

`backend/main.py` calls `setup_telemetry(app)` after middleware registration; FastAPI + httpx are auto-instrumented.

## 3. Rollback

| To disable | Action |
|---|---|
| Langfuse | Unset `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` and restart |
| OTel | Unset `OTEL_EXPORTER_OTLP_ENDPOINT` and restart |

No code change required.

## 4. Dependencies

The `opentelemetry-*` and `langfuse` packages are listed in `requirements.txt` but **lazily imported** — if a deployment chooses to omit them (e.g. via a stripped image), the bootstrap logs a warning and continues.
