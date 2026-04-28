"""S1-F11: behavioral tests for the extracted health router.

Pins:
  - /livez, /healthz/ready, /health are all registered.
  - /healthz/ready returns 200 when Supabase reachable.
  - /healthz/ready returns 503 when Supabase unreachable.
  - /healthz/ready does NOT touch AI provider / model_router / breakers.
"""
from __future__ import annotations

import inspect

from fastapi.testclient import TestClient


def test_health_routes_registered() -> None:
    import main as backend_main

    paths = {getattr(r, "path", "") for r in backend_main.app.routes}
    assert "/livez" in paths
    assert "/healthz/ready" in paths
    assert "/health" in paths


def test_readiness_returns_200_when_supabase_reachable(monkeypatch) -> None:
    from app.api.routes import health as health_mod
    import main as backend_main

    async def _ok(timeout_s: float = 2.0):
        return {"connected": True}

    async def _redis_ok(timeout_s: float = 1.0):
        return {"connected": True}

    monkeypatch.setattr(health_mod, "_check_supabase", _ok)
    monkeypatch.setattr(health_mod, "_check_redis", _redis_ok)

    client = TestClient(backend_main.app)
    resp = client.get("/healthz/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["supabase"]["connected"] is True


def test_readiness_returns_503_when_supabase_unreachable(monkeypatch) -> None:
    from app.api.routes import health as health_mod
    import main as backend_main

    async def _bad(timeout_s: float = 2.0):
        return {"connected": False, "error": "boom"}

    async def _redis_ok(timeout_s: float = 1.0):
        return {"connected": True}

    monkeypatch.setattr(health_mod, "_check_supabase", _bad)
    monkeypatch.setattr(health_mod, "_check_redis", _redis_ok)

    client = TestClient(backend_main.app)
    resp = client.get("/healthz/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"


def test_readiness_redis_optional_when_in_memory_fallback(monkeypatch) -> None:
    """Redis being absent must not flip readiness to 503 — the in-mem
    fallback is acceptable for serving traffic."""
    from app.api.routes import health as health_mod
    import main as backend_main

    async def _ok(timeout_s: float = 2.0):
        return {"connected": True}

    async def _redis_missing(timeout_s: float = 1.0):
        return {"connected": False, "fallback": "in_memory"}

    monkeypatch.setattr(health_mod, "_check_supabase", _ok)
    monkeypatch.setattr(health_mod, "_check_redis", _redis_missing)

    client = TestClient(backend_main.app)
    resp = client.get("/healthz/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["redis"]["fallback"] == "in_memory"


def test_readiness_does_not_touch_ai_or_breakers() -> None:
    """Readiness must stay cheap — no model_router, no breakers,
    no metrics collection."""
    from app.api.routes.health import readiness_probe

    src = inspect.getsource(readiness_probe)
    forbidden = (
        "model_router",
        "get_model_health",
        "MetricsCollector",
        "_breakers",
        "queue_depth",
        "ai_engine",
    )
    for token in forbidden:
        assert token not in src, f"/healthz/ready must not call {token}"
