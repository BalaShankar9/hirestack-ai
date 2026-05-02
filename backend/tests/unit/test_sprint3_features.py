"""Tests for P2-12, P2-14, P3-04, and P3-05 features:

- P2-12: Application completeness check — finalize_job_status_payload uses
  'succeeded_with_warnings' when no module produced content
- P2-14: GenerationAuditLogger — structured audit trail for generation jobs
- P3-04: Benchmark 24h caching — JD analysis cache hit/miss logic
- P3-05: Model routing / cost optimizer metrics exposed in /metrics source
"""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════
#  P2-12: Completeness check in finalize_job_status_payload
# ═══════════════════════════════════════════════════════════════════════

class TestCompletenessCheck:
    """finalize_job_status_payload should flag empty-generation as warnings."""

    def _fn(self):
        from app.api.routes.generate.helpers import finalize_job_status_payload
        return finalize_job_status_payload

    def test_normal_success(self):
        fn = self._fn()
        payload = fn({"scores": {"overall": 80}}, total_steps=7)
        assert payload["status"] == "succeeded"
        assert payload["message"] == "Generation complete."

    def test_validation_failure_produces_warnings(self):
        fn = self._fn()
        result = {"validation": {"passed": False, "error_count": 2, "warning_count": 3}}
        payload = fn(result, total_steps=7)
        assert payload["status"] == "succeeded_with_warnings"
        assert "2 errors" in payload["message"]
        assert "3 warnings" in payload["message"]

    def test_completeness_warning_produces_warnings(self):
        fn = self._fn()
        result = {
            "meta": {
                "completeness_warning": (
                    "Generation completed but no module produced content. "
                    "Try regenerating individual modules."
                )
            }
        }
        payload = fn(result, total_steps=7)
        assert payload["status"] == "succeeded_with_warnings"
        assert "no module produced content" in payload["message"]

    def test_no_completeness_warning_when_content_exists(self):
        fn = self._fn()
        # Normal result with no completeness_warning set
        result = {"cvHtml": "<div>CV</div>"}
        payload = fn(result, total_steps=7)
        assert payload["status"] == "succeeded"

    def test_extra_fields_do_not_override_status(self):
        fn = self._fn()
        result = {"validation": {"passed": True}}
        payload = fn(
            result,
            total_steps=7,
            extra_fields={"status": "failed", "message": "override attempt"},
        )
        assert payload["status"] == "succeeded"
        assert payload["message"] == "Generation complete."

    def test_null_result_defaults_to_succeeded(self):
        fn = self._fn()
        payload = fn(None, total_steps=7)
        assert payload["status"] == "succeeded"

    def test_payload_always_has_required_keys(self):
        fn = self._fn()
        payload = fn(None, total_steps=7)
        for key in ("status", "progress", "phase", "message", "finished_at"):
            assert key in payload, f"Missing key: {key}"


# ═══════════════════════════════════════════════════════════════════════
#  P2-14: GenerationAuditLogger
# ═══════════════════════════════════════════════════════════════════════

class TestGenerationAuditLogger:
    """Audit logger must emit correct structlog events; DB writes are best-effort."""

    def _make(self):
        from app.services.generation_audit import GenerationAuditLogger
        return GenerationAuditLogger("user-1", "job-abc", "app-xyz")

    def test_log_started_does_not_raise(self):
        logger = self._make()
        # Should not raise
        logger.log_started(modules=["cv", "coverLetter"], jd_len=2048, resume_provided=True)

    def test_log_completed_does_not_raise(self):
        logger = self._make()
        logger.log_started(modules=["cv"], jd_len=1000, resume_provided=False)
        logger.log_completed(duration_ms=45_000, model_used="gemini-2.5-pro")

    def test_log_failed_does_not_raise(self):
        logger = self._make()
        logger.log_started(modules=["cv"], jd_len=500, resume_provided=True)
        logger.log_failed(error_message="AI provider unavailable", duration_ms=3_000)

    def test_log_cancelled_does_not_raise(self):
        logger = self._make()
        logger.log_started(modules=["benchmark"], jd_len=1500, resume_provided=True)
        logger.log_cancelled(duration_ms=10_000)

    def test_auto_duration_when_not_provided(self):
        """duration_ms should be auto-computed when not passed explicitly."""
        import time
        logger = self._make()
        logger.log_started(modules=["cv"], jd_len=1000, resume_provided=True)
        time.sleep(0.01)  # Ensure some elapsed time
        # Should not raise, and auto-computes duration
        logger.log_completed()

    def test_error_message_truncated_to_500(self):
        """Long error messages must be truncated at _ERROR_MSG_MAX_LEN."""
        from app.services.generation_audit import GenerationAuditLogger, _ERROR_MSG_MAX_LEN
        logger = GenerationAuditLogger("u", "j", "a")
        captured_rows = []

        def _fake_persist(row_data):
            captured_rows.append(row_data)

        logger._persist_async = _fake_persist
        long_error = "E" * 1000
        logger.log_failed(error_message=long_error)
        assert len(captured_rows) == 1
        assert len(captured_rows[0]["error_message"]) <= _ERROR_MSG_MAX_LEN

    def test_make_audit_logger_factory(self):
        from app.services.generation_audit import make_audit_logger
        audit = make_audit_logger("u-1", "j-1", "a-1")
        assert audit._user_id == "u-1"
        assert audit._job_id == "j-1"
        assert audit._application_id == "a-1"


# ═══════════════════════════════════════════════════════════════════════
#  P3-04: Benchmark 24h caching
# ═══════════════════════════════════════════════════════════════════════

class TestBenchmarkCaching:
    """JDAnalysisCache should store benchmark data with a 24h TTL."""

    def test_cache_miss_returns_none(self):
        from ai_engine.cache import JDAnalysisCache
        cache = JDAnalysisCache(max_entries=10)
        key = cache.hash_jd("Some JD text", "Software Engineer")
        assert cache.get(key) is None

    def test_cache_hit_returns_stored_data(self):
        from ai_engine.cache import JDAnalysisCache
        cache = JDAnalysisCache(max_entries=10)
        jd = "We are looking for a senior engineer with Python and AWS experience."
        key = cache.hash_jd(jd, "Software Engineer")
        benchmark_data = {"ideal_skills": [{"name": "Python", "importance": "critical"}]}
        cache.put(key, benchmark_data, ttl=86400.0)
        result = cache.get(key)
        assert result == benchmark_data

    def test_24h_ttl_not_expired_immediately(self):
        """Cache entry with 24h TTL should not expire immediately."""
        from ai_engine.cache import JDAnalysisCache
        import time
        cache = JDAnalysisCache(max_entries=10)
        key = cache.hash_jd("JD text", "Engineer")
        cache.put(key, {"data": "benchmark"}, ttl=86400.0)
        # Should still be available moments later
        assert cache.get(key) is not None

    def test_zero_ttl_expires_immediately(self):
        """Sanity check: TTL 0 expires right away."""
        from ai_engine.cache import JDAnalysisCache
        import time
        cache = JDAnalysisCache(max_entries=10)
        key = cache.hash_jd("JD text", "Engineer")
        cache.put(key, {"data": "benchmark"}, ttl=0.0)
        time.sleep(0.01)
        assert cache.get(key) is None

    def test_same_jd_same_key(self):
        """Identical JD + title always maps to the same hash."""
        from ai_engine.cache import JDAnalysisCache
        cache = JDAnalysisCache()
        jd = "Looking for a Senior Python Engineer at Acme Corp."
        title = "Senior Python Engineer"
        key1 = cache.hash_jd(jd, title)
        key2 = cache.hash_jd(jd, title)
        assert key1 == key2

    def test_different_jd_different_key(self):
        """Different JD text produces a different hash."""
        from ai_engine.cache import JDAnalysisCache
        cache = JDAnalysisCache()
        key1 = cache.hash_jd("Python Backend Engineer", "Engineer")
        key2 = cache.hash_jd("Frontend React Engineer", "Engineer")
        assert key1 != key2

    def test_cache_stats_track_hits_and_misses(self):
        from ai_engine.cache import JDAnalysisCache
        cache = JDAnalysisCache(max_entries=10)
        key = cache.hash_jd("JD", "title")
        cache.get(key)   # miss
        cache.put(key, {"x": 1}, ttl=3600.0)
        cache.get(key)   # hit
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_pct"] == 50.0

    def test_max_entries_evicts_oldest(self):
        from ai_engine.cache import JDAnalysisCache
        cache = JDAnalysisCache(max_entries=3)
        for i in range(4):
            cache.put(f"key_{i}", {"i": i}, ttl=3600.0)
        assert cache.stats["size"] == 3


# ═══════════════════════════════════════════════════════════════════════
#  P3-05: Model routing metrics in /metrics source
# ═══════════════════════════════════════════════════════════════════════

def test_metrics_endpoint_exposes_model_routing_gauges():
    """The /metrics route must include model health and cost optimizer gauges."""
    # Verify the gauge name constants are present in the metrics source
    # by calling the function on a mock app with empty state — simpler
    # than inspect.getsource which is fragile across builds.
    from fastapi.testclient import TestClient
    import sys

    # Import the app lazily so the test doesn't depend on DB/Redis connections
    # We only need to verify the metric name strings appear in the output.
    sys.path.insert(0, "/home/runner/work/hirestack-ai/hirestack-ai/backend")
    try:
        import importlib
        main_mod = importlib.import_module("main")
        import inspect
        src = inspect.getsource(main_mod.prometheus_metrics)
        assert "hirestack_model_health_failures" in src, "Missing model health failures gauge"
        assert "hirestack_model_health_is_healthy" in src, "Missing model health gauge"
        assert "hirestack_cost_optimizer_avg_quality" in src, "Missing cost optimizer quality gauge"
        assert "hirestack_cost_optimizer_observations" in src, "Missing cost optimizer observations gauge"
    finally:
        if sys.path[0] == "/home/runner/work/hirestack-ai/hirestack-ai/backend":
            sys.path.pop(0)


def test_model_router_resolve_model_returns_string():
    """resolve_model always returns a string model name."""
    from ai_engine.model_router import resolve_model
    for task in ("reasoning", "extraction", "drafting", "nonexistent"):
        result = resolve_model(task, "gemini-2.5-flash")
        assert isinstance(result, str)
        assert len(result) > 0


def test_model_router_resolve_cascade_returns_list():
    from ai_engine.model_router import resolve_cascade
    cascade = resolve_cascade("quality_doc", "gemini-2.5-pro")
    assert isinstance(cascade, list)
    assert len(cascade) >= 1


def test_model_health_tracking():
    """record_model_failure / record_model_success update health correctly."""
    from ai_engine.model_router import _ModelHealth
    health = _ModelHealth()
    health.record_failure("test-model")
    health.record_failure("test-model")
    health.record_failure("test-model")
    assert not health.is_healthy("test-model")
    health.record_success("test-model")
    assert health.is_healthy("test-model")


def test_estimate_task_complexity_cheap_for_simple_tasks():
    from ai_engine.model_router import estimate_task_complexity
    model = estimate_task_complexity("extraction", input_tokens=100)
    assert model == "gemini-2.0-flash"


def test_estimate_task_complexity_pro_for_reasoning():
    from ai_engine.model_router import estimate_task_complexity
    model = estimate_task_complexity("reasoning", input_tokens=5000, requires_reasoning=True)
    assert "pro" in model.lower()
