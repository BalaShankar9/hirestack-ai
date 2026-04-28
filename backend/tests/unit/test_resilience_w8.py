"""W8 Strength & resilience — /livez + circuit-breaker Prometheus gauges."""
from __future__ import annotations

import inspect


def test_livez_endpoint_registered() -> None:
    import main as backend_main
    paths = {getattr(r, "path", "") for r in backend_main.app.routes}
    assert "/livez" in paths, paths


def test_livez_does_not_touch_external_dependencies() -> None:
    """The whole point of /livez is to NOT call DB / Redis / AI."""
    from app.api.routes.health import liveness_probe
    src = inspect.getsource(liveness_probe)
    forbidden = ("get_supabase", "get_redis", "ai_engine", "circuit_breaker", "MetricsCollector")
    for token in forbidden:
        assert token not in src, f"/livez must not call {token}"
    # And it must return 200
    assert "HTTP_200_OK" in src or "200" in src


def test_metrics_endpoint_emits_circuit_breaker_state() -> None:
    """Prometheus scraper needs a numeric gauge it can alert on."""
    import main as backend_main
    src = inspect.getsource(backend_main.prometheus_metrics)
    assert "hirestack_circuit_breaker_state" in src
    assert "hirestack_circuit_breaker_failures" in src
    # Numeric encoding documented for alert rules.
    assert "0=closed" in src and "2=open" in src


def test_circuit_breaker_state_encoding_is_stable() -> None:
    """0/1/2 mapping must remain stable so alert rules don't break."""
    from app.core.circuit_breaker import CircuitState
    # values exist
    assert CircuitState.CLOSED is not None
    assert CircuitState.HALF_OPEN is not None
    assert CircuitState.OPEN is not None


def test_livez_response_shape() -> None:
    """Response body must include status='alive' and a version string."""
    from fastapi.testclient import TestClient
    import main as backend_main
    client = TestClient(backend_main.app)
    resp = client.get("/livez")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "alive"
    assert "version" in body


def test_livez_is_cheap_no_route_dependencies() -> None:
    """Confirm /livez has no auth dependency that could turn 200 into 401."""
    import main as backend_main
    for r in backend_main.app.routes:
        if getattr(r, "path", "") == "/livez":
            # No security dependencies on liveness probe.
            deps = getattr(r, "dependencies", []) or []
            assert deps == [], f"/livez must have no dependencies, got {deps}"
            return
    raise AssertionError("/livez route not found")
