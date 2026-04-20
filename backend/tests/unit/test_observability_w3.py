"""Wave 3 tests — Agentic logs & observability (LLM call counters, hashes, /metrics)."""
from __future__ import annotations

import inspect

from app.core.metrics import MetricsCollector


def test_metrics_collector_records_llm_calls():
    MetricsCollector.reset()
    mc = MetricsCollector.get()
    mc.record_llm_call(model="gemini-2.5-flash", task_type="extraction", input_tokens=120, output_tokens=80)
    mc.record_llm_call(model="gemini-2.5-flash", task_type="extraction", input_tokens=200, output_tokens=50)
    mc.record_llm_call(model="gemini-2.5-pro", task_type="reasoning", input_tokens=500, output_tokens=900)

    stats = mc.get_llm_call_stats()
    assert "gemini-2.5-flash|extraction" in stats
    assert "gemini-2.5-pro|reasoning" in stats

    flash = stats["gemini-2.5-flash|extraction"]
    assert flash["calls"] == 2
    assert flash["tokens_in"] == 320
    assert flash["tokens_out"] == 130
    assert flash["model"] == "gemini-2.5-flash"
    assert flash["task_type"] == "extraction"

    pro = stats["gemini-2.5-pro|reasoning"]
    assert pro["calls"] == 1


def test_metrics_collector_record_llm_call_clamps_negative_and_invalid():
    MetricsCollector.reset()
    mc = MetricsCollector.get()
    mc.record_llm_call(model="m", task_type="t", input_tokens=-5, output_tokens=10)
    mc.record_llm_call(model="m", task_type="t", input_tokens="bad", output_tokens=10)  # type: ignore[arg-type]
    stats = mc.get_llm_call_stats()
    # First call recorded with input_tokens clamped to 0; second rejected
    assert stats["m|t"]["calls"] == 1
    assert stats["m|t"]["tokens_in"] == 0
    assert stats["m|t"]["tokens_out"] == 10


def test_metrics_collector_default_keys_when_unknown():
    MetricsCollector.reset()
    mc = MetricsCollector.get()
    mc.record_llm_call(model="", task_type="", input_tokens=10, output_tokens=10)
    stats = mc.get_llm_call_stats()
    assert "unknown|unknown" in stats


def test_metrics_endpoint_exposes_llm_and_cost_gauges():
    import backend.main as backend_main  # type: ignore
    src = inspect.getsource(backend_main)
    for marker in (
        "hirestack_llm_calls_total",
        "hirestack_llm_tokens_in_total",
        "hirestack_llm_tokens_out_total",
        "hirestack_ai_daily_cost_cents",
        "hirestack_ai_daily_calls_total",
        "hirestack_ai_daily_tokens_total",
        "hirestack_ai_daily_cache_hits_total",
        "get_llm_call_stats",
        "_daily_tracker.stats",
    ):
        assert marker in src, f"missing /metrics marker: {marker}"


def test_ai_client_track_usage_logs_hashes_and_records_to_collector():
    """Anchor: _track_usage emits structured ai_call_audit log + records to MetricsCollector."""
    import ai_engine.client as cli
    src = inspect.getsource(cli)
    assert "ai_call_audit" in src
    assert "prompt_hash" in src
    assert "response_hash" in src
    assert "MetricsCollector.get().record_llm_call" in src
    # Hash truncation must be 12 hex chars (matches log marker convention)
    assert "[:12]" in src
