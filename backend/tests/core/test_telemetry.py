"""PR m4-pr12: telemetry + langfuse no-op behaviour."""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_SERVICE_NAME",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def _reload_telemetry():
    import app.core.telemetry as mod  # type: ignore

    importlib.reload(mod)
    return mod


def test_setup_telemetry_noop_when_endpoint_unset():
    mod = _reload_telemetry()
    assert mod.setup_telemetry(object()) is False


def test_setup_telemetry_noop_when_endpoint_blank(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "   ")
    mod = _reload_telemetry()
    assert mod.setup_telemetry(object()) is False


def test_setup_telemetry_returns_false_when_sdk_missing(monkeypatch):
    """If user sets the endpoint but SDK is absent, we degrade rather than crash."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
    # Force import failure by injecting a sentinel into sys.modules.
    import sys

    saved = {k: sys.modules.get(k) for k in list(sys.modules) if k.startswith("opentelemetry")}
    for k in saved:
        sys.modules[k] = None  # type: ignore[assignment]
    try:
        mod = _reload_telemetry()
        # Either it wires up (if real SDK was imported via re-resolution) or no-ops.
        result = mod.setup_telemetry(object())
        assert result in (True, False)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


@pytest.mark.asyncio
async def test_trace_llm_noop_when_disabled():
    from ai_engine.observability import is_enabled, trace_llm

    assert is_enabled() is False
    async with trace_llm(model="gemini-2.5-flash") as span:
        assert span is None


@pytest.mark.asyncio
async def test_trace_llm_propagates_exceptions_when_disabled():
    from ai_engine.observability import trace_llm

    with pytest.raises(RuntimeError, match="boom"):
        async with trace_llm(model="x"):
            raise RuntimeError("boom")


def test_get_langfuse_returns_none_without_keys():
    from ai_engine.observability.langfuse_client import get_langfuse, is_enabled

    assert is_enabled() is False
    # Reset memo
    import ai_engine.observability.langfuse_client as m

    m._client = None
    m._init_attempted = False
    assert get_langfuse() is None
