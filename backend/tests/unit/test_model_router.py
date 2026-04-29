"""S6-F1 — Pin ai_engine/model_router.py contracts.

Model routing is on the hot path of every chain call:
- A regression in resolve_model() either bills Pro for everything
  (cost blowout) or routes Pro tasks to Flash (quality blowout).
- A regression in cascade health filtering means a degraded model
  retries 3+ times before recovery, blowing the latency budget.
- A regression in resolve_cost_optimized() either over-routes to
  Flash (quality drop) or under-routes (cost drop missed).

Tests pin the behaviour BEFORE any refactor. Pure logic, zero
LLM calls, zero DB calls (the DB persist branches are best-effort
and tested via mocking only when relevant).
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from ai_engine import model_router


# ────────────────────────────────────────────────────────────────────
# Fixture: reset module-level singletons between tests so env-var
# overrides and quality observations don't leak.
# ────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_router_state():
    model_router.reload_routes()
    # Reset health
    model_router._model_health._failures.clear()
    model_router._model_health._last_failure.clear()
    # Reset cost optimizer cache
    model_router._quality_observations.clear()
    yield
    model_router.reload_routes()
    model_router._model_health._failures.clear()
    model_router._model_health._last_failure.clear()
    model_router._quality_observations.clear()


# ════════════════════════════════════════════════════════════════════
# resolve_model — primary task → model mapping
# ════════════════════════════════════════════════════════════════════
class TestResolveModel:
    def test_tier1_pro_only_tasks_route_to_pro(self):
        for task in ("reasoning", "fact_checking", "quality_doc"):
            assert model_router.resolve_model(task, "default") == "gemini-2.5-pro"

    def test_tier2_tasks_route_to_flash(self):
        for task in ("research", "structured_output", "optimization",
                     "creative", "drafting", "critique", "synthesis",
                     "validation", "general"):
            assert model_router.resolve_model(task, "default") == "gemini-2.5-flash"

    def test_tier3_extraction_tasks_route_to_2_0_flash(self):
        for task in ("extraction", "classification", "fast_doc",
                     "summarization", "formatting"):
            assert model_router.resolve_model(task, "default") == "gemini-2.0-flash"

    def test_brief_computation_routes_to_2_5_flash(self):
        # brief_computation lives in the tier-3 block but is intentionally
        # 2.5-flash, not 2.0 — pin the exception.
        assert model_router.resolve_model("brief_computation", "x") == "gemini-2.5-flash"

    def test_unknown_task_returns_default(self):
        assert model_router.resolve_model("nonexistent_task", "fallback") == "fallback"

    def test_none_task_returns_default(self):
        assert model_router.resolve_model(None, "fallback") == "fallback"

    def test_empty_string_task_returns_default(self):
        # Falsy task type is treated as "use default"
        assert model_router.resolve_model("", "fallback") == "fallback"

    def test_env_override_merges_with_defaults(self):
        with patch.dict(os.environ, {"MODEL_ROUTES": json.dumps({"reasoning": "custom-model"})}):
            model_router.reload_routes()
            assert model_router.resolve_model("reasoning", "x") == "custom-model"
            # Other defaults still apply
            assert model_router.resolve_model("creative", "x") == "gemini-2.5-flash"

    def test_env_override_invalid_json_falls_back_to_defaults(self):
        with patch.dict(os.environ, {"MODEL_ROUTES": "{not valid json"}):
            model_router.reload_routes()
            assert model_router.resolve_model("reasoning", "x") == "gemini-2.5-pro"

    def test_env_override_non_dict_ignored(self):
        with patch.dict(os.environ, {"MODEL_ROUTES": json.dumps(["not", "a", "dict"])}):
            model_router.reload_routes()
            assert model_router.resolve_model("reasoning", "x") == "gemini-2.5-pro"


# ════════════════════════════════════════════════════════════════════
# resolve_cascade — fallback ordering with health filtering
# ════════════════════════════════════════════════════════════════════
class TestResolveCascade:
    def test_tier1_cascade_pro_then_flash(self):
        # Pass a default that's already in the cascade so it isn't appended.
        cascade = model_router.resolve_cascade("reasoning", "gemini-2.5-pro")
        assert cascade == ["gemini-2.5-pro", "gemini-2.5-flash"]

    def test_tier2_cascade_flash_then_pro(self):
        cascade = model_router.resolve_cascade("creative", "gemini-2.5-flash")
        assert cascade == ["gemini-2.5-flash", "gemini-2.5-pro"]

    def test_tier3_extraction_3_step_cascade(self):
        cascade = model_router.resolve_cascade("extraction", "gemini-2.0-flash")
        assert cascade == ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"]

    def test_unknown_task_uses_general_cascade(self):
        # "general" cascade is flash → pro
        cascade = model_router.resolve_cascade("nonexistent_xyz", "fallback-default")
        # Should fall back to "general" cascade + fallback default appended
        assert "fallback-default" in cascade

    def test_default_appended_if_not_in_cascade(self):
        cascade = model_router.resolve_cascade("reasoning", "totally-new-model")
        assert "totally-new-model" in cascade
        # Default goes to the end (lowest priority)
        assert cascade[-1] == "totally-new-model"

    def test_unhealthy_models_filtered(self):
        # Mark Pro as unhealthy
        for _ in range(model_router._ModelHealth.FAILURE_THRESHOLD):
            model_router.record_model_failure("gemini-2.5-pro")
        cascade = model_router.resolve_cascade("reasoning", "default")
        # Pro should be gone, Flash remains
        assert "gemini-2.5-pro" not in cascade
        assert "gemini-2.5-flash" in cascade

    def test_all_unhealthy_returns_full_list_as_last_resort(self):
        # Mark every model in the cascade unhealthy (the appended default
        # too, so the all-unhealthy branch is hit).
        for model in ("gemini-2.5-pro", "gemini-2.5-flash"):
            for _ in range(model_router._ModelHealth.FAILURE_THRESHOLD):
                model_router.record_model_failure(model)
        cascade = model_router.resolve_cascade("reasoning", "gemini-2.5-pro")
        # All-unhealthy fallback returns full list (incl. unhealthy)
        assert "gemini-2.5-pro" in cascade
        assert "gemini-2.5-flash" in cascade


# ════════════════════════════════════════════════════════════════════
# _ModelHealth — auto-recovery state machine
# ════════════════════════════════════════════════════════════════════
class TestModelHealth:
    def test_healthy_by_default(self):
        h = model_router._ModelHealth()
        assert h.is_healthy("any-model") is True

    def test_below_threshold_stays_healthy(self):
        h = model_router._ModelHealth()
        for _ in range(h.FAILURE_THRESHOLD - 1):
            h.record_failure("m")
        assert h.is_healthy("m") is True

    def test_at_threshold_becomes_unhealthy(self):
        h = model_router._ModelHealth()
        for _ in range(h.FAILURE_THRESHOLD):
            h.record_failure("m")
        assert h.is_healthy("m") is False

    def test_record_success_resets_failure_count(self):
        h = model_router._ModelHealth()
        for _ in range(h.FAILURE_THRESHOLD):
            h.record_failure("m")
        h.record_success("m")
        assert h.is_healthy("m") is True

    def test_recovery_timeout_re_probes(self, monkeypatch):
        h = model_router._ModelHealth()
        for _ in range(h.FAILURE_THRESHOLD):
            h.record_failure("m")
        assert h.is_healthy("m") is False
        # Fast-forward past recovery timeout
        import time
        original = h._last_failure["m"]
        h._last_failure["m"] = original - h.RECOVERY_TIMEOUT - 1
        assert h.is_healthy("m") is True

    def test_get_status_only_includes_failures(self):
        h = model_router._ModelHealth()
        h.record_failure("bad-model")
        h.record_success("good-model")  # zero count
        status = h.get_status()
        assert "bad-model" in status
        assert "good-model" not in status

    def test_get_status_shape(self):
        h = model_router._ModelHealth()
        h.record_failure("m")
        h.record_failure("m")
        status = h.get_status()
        assert status["m"] == {"failures": 2, "healthy": True}


# ════════════════════════════════════════════════════════════════════
# Public health interface
# ════════════════════════════════════════════════════════════════════
class TestPublicHealthInterface:
    def test_record_model_success_resets_module_singleton(self):
        for _ in range(5):
            model_router.record_model_failure("m")
        model_router.record_model_success("m")
        assert model_router._model_health.is_healthy("m") is True

    def test_get_model_health_returns_dict(self):
        model_router.record_model_failure("m")
        health = model_router.get_model_health()
        assert isinstance(health, dict)
        assert "m" in health


# ════════════════════════════════════════════════════════════════════
# available_task_types — surface lookup
# ════════════════════════════════════════════════════════════════════
class TestAvailableTaskTypes:
    def test_returns_all_default_task_types(self):
        types = model_router.available_task_types()
        # Spot-check the contract — we expose all 19 task types
        for required in ("reasoning", "creative", "extraction",
                         "brief_computation", "general"):
            assert required in types

    def test_count_matches_default_routes(self):
        # Lock the count; new task types require updating this test.
        assert len(model_router.available_task_types()) == len(model_router._DEFAULT_ROUTES)


# ════════════════════════════════════════════════════════════════════
# Cost optimizer — record_quality_observation + resolve_cost_optimized
# ════════════════════════════════════════════════════════════════════
class TestCostOptimizer:
    def _record(self, task_type, model, scores):
        # Bypass DB persist by patching it
        with patch.object(model_router, "_persist_quality_observation"):
            for s in scores:
                model_router.record_quality_observation(task_type, model, s)

    def test_below_5_observations_falls_back_to_standard(self):
        # Only 4 observations — not enough to trust
        self._record("creative", "gemini-2.5-flash", [95.0] * 4)
        result = model_router.resolve_cost_optimized("creative", min_quality=70.0)
        # Falls back to resolve_model("creative") = flash
        assert result == "gemini-2.5-flash"

    def test_5_plus_observations_above_threshold_routes_to_flash(self):
        self._record("reasoning", "gemini-2.5-flash", [85.0] * 5)
        result = model_router.resolve_cost_optimized(
            "reasoning", min_quality=70.0, default="gemini-2.5-pro",
        )
        assert result == "gemini-2.5-flash"

    def test_5_plus_observations_below_threshold_does_not_route(self):
        # Flash is consistently below threshold for this task
        self._record("reasoning", "gemini-2.5-flash", [50.0] * 5)
        result = model_router.resolve_cost_optimized(
            "reasoning", min_quality=70.0, default="gemini-2.5-pro",
        )
        # Should fall through to resolve_model("reasoning") = pro
        assert result == "gemini-2.5-pro"

    def test_unhealthy_flash_skipped_even_with_good_scores(self):
        self._record("reasoning", "gemini-2.5-flash", [95.0] * 10)
        for _ in range(model_router._ModelHealth.FAILURE_THRESHOLD):
            model_router.record_model_failure("gemini-2.5-flash")
        result = model_router.resolve_cost_optimized(
            "reasoning", min_quality=70.0, default="gemini-2.5-pro",
        )
        # Flash is unhealthy → skip → try pro → pro has no observations
        # → fall back to resolve_model("reasoning") = pro
        assert result == "gemini-2.5-pro"

    def test_rolling_window_cap(self):
        self._record("creative", "gemini-2.5-flash",
                     [50.0] * (model_router._MAX_OBSERVATIONS + 20))
        scores = model_router._quality_observations[("creative", "gemini-2.5-flash")]
        assert len(scores) == model_router._MAX_OBSERVATIONS

    def test_record_persists_to_db_best_effort(self):
        # Persistence should not raise even if DB is unavailable.
        with patch.object(model_router, "_persist_quality_observation"):
            model_router.record_quality_observation("creative", "gemini-2.5-flash", 85.0)
        # Did not raise; observation in cache
        assert ("creative", "gemini-2.5-flash") in model_router._quality_observations


class TestCostOptimizerStats:
    def test_empty_cache_returns_empty(self):
        assert model_router.get_cost_optimizer_stats() == {}

    def test_stats_shape(self):
        with patch.object(model_router, "_persist_quality_observation"):
            for s in [80.0, 90.0, 100.0]:
                model_router.record_quality_observation("creative", "gemini-2.5-flash", s)
        stats = model_router.get_cost_optimizer_stats()
        assert "creative:gemini-2.5-flash" in stats
        entry = stats["creative:gemini-2.5-flash"]
        assert entry == {
            "observations": 3,
            "avg_quality": 90.0,
            "min_quality": 80.0,
            "max_quality": 100.0,
        }


# ════════════════════════════════════════════════════════════════════
# Cascade env override
# ════════════════════════════════════════════════════════════════════
class TestCascadeEnvOverride:
    def test_cascade_env_override_merges(self):
        with patch.dict(os.environ, {"MODEL_CASCADE": json.dumps({"reasoning": ["custom-1", "custom-2"]})}):
            model_router.reload_routes()
            cascade = model_router.resolve_cascade("reasoning", "fallback")
            assert "custom-1" in cascade and "custom-2" in cascade

    def test_invalid_cascade_json_falls_back_to_defaults(self):
        with patch.dict(os.environ, {"MODEL_CASCADE": "{broken"}):
            model_router.reload_routes()
            cascade = model_router.resolve_cascade("reasoning", "default")
            assert cascade[0] == "gemini-2.5-pro"


# ════════════════════════════════════════════════════════════════════
# estimate_task_complexity — input-aware routing
# ════════════════════════════════════════════════════════════════════
class TestEstimateTaskComplexity:
    def test_reasoning_with_requirement_forces_pro(self):
        result = model_router.estimate_task_complexity(
            "reasoning", input_tokens=10000, requires_reasoning=True,
        )
        assert result == "gemini-2.5-pro"

    def test_extraction_always_cheap(self):
        result = model_router.estimate_task_complexity(
            "extraction", input_tokens=50000, requires_reasoning=True,
        )
        assert result == "gemini-2.0-flash"

    def test_classification_always_cheap(self):
        assert model_router.estimate_task_complexity(
            "classification", input_tokens=100,
        ) == "gemini-2.0-flash"

    def test_short_input_no_reasoning_uses_cheapest(self):
        result = model_router.estimate_task_complexity(
            "creative", input_tokens=400, requires_reasoning=False,
        )
        assert result == "gemini-2.0-flash"

    def test_medium_input_no_reasoning_uses_2_5_flash(self):
        result = model_router.estimate_task_complexity(
            "creative", input_tokens=1500, requires_reasoning=False,
        )
        assert result == "gemini-2.5-flash"

    def test_large_input_uses_task_default_route(self):
        # 5000 tokens, not in special blocks → falls through to resolve_model
        result = model_router.estimate_task_complexity(
            "creative", input_tokens=5000, requires_reasoning=False,
        )
        assert result == "gemini-2.5-flash"  # creative routes to flash

    def test_reasoning_task_without_explicit_reasoning_flag_falls_through(self):
        # reasoning task type but requires_reasoning=False → falls through
        # to standard routing (still pro per defaults)
        result = model_router.estimate_task_complexity(
            "reasoning", input_tokens=5000, requires_reasoning=False,
        )
        assert result == "gemini-2.5-pro"


# ════════════════════════════════════════════════════════════════════
# estimate_call_cost — USD math
# ════════════════════════════════════════════════════════════════════
class TestEstimateCallCost:
    def test_zero_tokens_zero_cost(self):
        assert model_router.estimate_call_cost("gemini-2.5-flash", 0, 0) == 0.0

    def test_2_5_flash_input_only(self):
        # 1M input tokens at $0.075 = $0.075
        assert model_router.estimate_call_cost(
            "gemini-2.5-flash", 1_000_000, 0,
        ) == pytest.approx(0.075, rel=1e-6)

    def test_2_5_pro_premium_pricing(self):
        # 1M input tokens at $1.25 = $1.25
        assert model_router.estimate_call_cost(
            "gemini-2.5-pro", 1_000_000, 0,
        ) == pytest.approx(1.25, rel=1e-6)

    def test_2_0_flash_cheapest(self):
        # 1M input tokens at $0.04
        assert model_router.estimate_call_cost(
            "gemini-2.0-flash", 1_000_000, 0,
        ) == pytest.approx(0.04, rel=1e-6)

    def test_unknown_model_uses_pro_pricing_default(self):
        # Unknown model defaults to $1.25/M input — safe over-estimate
        result = model_router.estimate_call_cost(
            "fictional-model", 1_000_000, 0,
        )
        assert result == pytest.approx(1.25, rel=1e-6)

    def test_output_tokens_priced_separately(self):
        # 2.5-flash: input $0.075/M, output ratio 0.30/0.075 = 4x → $0.30/M
        cost = model_router.estimate_call_cost("gemini-2.5-flash", 0, 1_000_000)
        assert cost == pytest.approx(0.30, rel=1e-6)

    def test_2_5_pro_output_5_dollars_per_million(self):
        cost = model_router.estimate_call_cost("gemini-2.5-pro", 0, 1_000_000)
        assert cost == pytest.approx(5.00, rel=1e-6)


# ════════════════════════════════════════════════════════════════════
# reload_routes — env-var override pattern reset
# ════════════════════════════════════════════════════════════════════
class TestReloadRoutes:
    def test_reload_picks_up_new_env_vars(self):
        # First load with no override
        assert model_router.resolve_model("reasoning", "x") == "gemini-2.5-pro"
        # Set override and reload
        with patch.dict(os.environ, {"MODEL_ROUTES": json.dumps({"reasoning": "new-model"})}):
            model_router.reload_routes()
            assert model_router.resolve_model("reasoning", "x") == "new-model"
