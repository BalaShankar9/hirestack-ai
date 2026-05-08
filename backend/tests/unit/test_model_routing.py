# backend/tests/unit/test_model_routing.py
"""Tests for real model routing — verifies resolved models reach the provider."""
import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
#  Model Router unit tests
# ═══════════════════════════════════════════════════════════════════════

class TestModelRouter:
    def test_resolve_model_returns_route(self):
        from ai_engine.api import resolve_model
        result = resolve_model("reasoning", "fallback-model")
        assert result != "fallback-model"

    def test_resolve_model_returns_default_for_unknown_task(self):
        from ai_engine.api import resolve_model
        result = resolve_model("nonexistent_task_type", "fallback-model")
        assert result == "fallback-model"

    def test_resolve_model_returns_default_for_none(self):
        from ai_engine.api import resolve_model
        result = resolve_model(None, "fallback-model")
        assert result == "fallback-model"

    def test_available_task_types_not_empty(self):
        from ai_engine.model_router import available_task_types
        types = available_task_types()
        assert len(types) > 0
        assert "reasoning" in types
        assert "general" in types


# ═══════════════════════════════════════════════════════════════════════
#  AIClient routing integration tests
# ═══════════════════════════════════════════════════════════════════════

def _make_fake_response(text="mock response"):
    resp = MagicMock()
    resp.text = text
    return resp


class TestAIClientRouting:
    """Verify that AIClient threads the resolved model to the provider."""

    @pytest.mark.asyncio
    async def test_complete_passes_routed_model_to_provider(self):
        """When task_type is given, the resolved model must reach generate_content."""
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "default-model"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import _GeminiProvider

            provider = _GeminiProvider()

            # Patch _generate_content_throttled to capture the model arg
            captured = {}

            async def _fake_throttled(*, contents, config, model=None):
                captured["model"] = model
                return _make_fake_response()

            provider._generate_content_throttled = _fake_throttled

            # Call complete with an explicit model override
            result = await provider.complete(
                prompt="test", model="routed-model-x"
            )
            assert captured["model"] == "routed-model-x"
            assert result == "mock response"

    @pytest.mark.asyncio
    async def test_complete_json_passes_routed_model_to_provider(self):
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "default-model"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import _GeminiProvider

            provider = _GeminiProvider()

            captured = {}

            async def _fake_throttled(*, contents, config, model=None):
                captured["model"] = model
                return _make_fake_response('{"key": "value"}')

            provider._generate_content_throttled = _fake_throttled

            result = await provider.complete_json(
                prompt="test", model="routed-json-model"
            )
            assert captured["model"] == "routed-json-model"
            assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_chat_passes_routed_model_to_provider(self):
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "default-model"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import _GeminiProvider

            provider = _GeminiProvider()

            captured = {}

            async def _fake_throttled(*, contents, config, model=None):
                captured["model"] = model
                return _make_fake_response("chat response")

            provider._generate_content_throttled = _fake_throttled

            result = await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="routed-chat-model",
            )
            assert captured["model"] == "routed-chat-model"
            assert result == "chat response"

    @pytest.mark.asyncio
    async def test_none_model_uses_default(self):
        """When no task_type or model is given, default model is used."""
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "default-model"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import _GeminiProvider

            provider = _GeminiProvider()

            captured = {}

            async def _fake_throttled(*, contents, config, model=None):
                captured["model"] = model
                return _make_fake_response()

            provider._generate_content_throttled = _fake_throttled

            await provider.complete(prompt="test", model=None)
            # When model is None, _generate_content_throttled uses
            # effective_model = self.model_name
            assert captured["model"] is None

    @pytest.mark.asyncio
    async def test_aiclient_resolve_model_with_task_type(self):
        """AIClient._resolve_model returns router result for known task_type."""
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "default-model"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import AIClient

            client = AIClient()
            resolved = client._resolve_model("reasoning", None)
            assert resolved is not None
            assert resolved != "default-model"

    @pytest.mark.asyncio
    async def test_aiclient_default_model_property(self):
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "test-default-model"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import AIClient

            client = AIClient()
            assert client.default_model == "test-default-model"


class TestModelRoutingFallback:
    """Verify fallback to default model when routed model fails with quota error."""

    @pytest.mark.asyncio
    async def test_fallback_on_quota_exhaustion(self):
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "safe-default"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import _GeminiProvider

            provider = _GeminiProvider()

            call_count = 0
            models_called = []

            fake_client = MagicMock()

            def fake_generate(*, model, contents, config):
                nonlocal call_count
                call_count += 1
                models_called.append(model)
                if model != "safe-default":
                    raise Exception("exceeded your current quota")
                resp = MagicMock()
                resp.text = "fallback response"
                return resp

            fake_client.models.generate_content = fake_generate
            provider._client = fake_client
            provider._min_interval_s = 0  # disable throttling for test

            result = await provider._generate_content_throttled(
                contents="test",
                config=MagicMock(),
                model="expensive-routed-model",
            )
            assert result.text == "fallback response"
            assert "expensive-routed-model" in models_called
            assert "safe-default" in models_called
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_fallback_when_default_model_fails(self):
        """If the default model itself is quota-exhausted, don't fallback (would loop)."""
        with patch("ai_engine.client.settings") as mock_settings:
            mock_settings.gemini_model = "safe-default"
            mock_settings.gemini_max_tokens = 8192
            mock_settings.gemini_api_key = "test-key"
            mock_settings.gemini_use_vertexai = False

            from ai_engine.client import _GeminiProvider

            provider = _GeminiProvider()

            fake_client = MagicMock()

            def fake_generate(*, model, contents, config):
                raise Exception("exceeded your current quota")

            fake_client.models.generate_content = fake_generate
            provider._client = fake_client
            provider._min_interval_s = 0

            with pytest.raises(Exception, match="exceeded your current quota"):
                await provider._generate_content_throttled(
                    contents="test",
                    config=MagicMock(),
                    model=None,
                )


# ═══════════════════════════════════════════════════════════════════════
#  PR m7-pr28 (ADR-0031): Multi-provider dispatch
# ═══════════════════════════════════════════════════════════════════════

class TestProviderSelection:
    """Verify ``AIClient._select_provider`` dispatches by model name prefix."""

    def test_select_provider_routes_claude_to_anthropic(self):
        from ai_engine.client import AIClient, _AnthropicProvider
        client = AIClient()
        provider = client._select_provider("claude-3-5-sonnet-20241022")
        assert isinstance(provider, _AnthropicProvider)

    def test_select_provider_routes_gemini_to_default(self):
        from ai_engine.client import AIClient
        client = AIClient()
        provider = client._select_provider("gemini-2.5-pro")
        assert provider is client._provider

    def test_select_provider_routes_none_to_default(self):
        from ai_engine.client import AIClient
        client = AIClient()
        provider = client._select_provider(None)
        assert provider is client._provider


class TestCascadeFlagGating:
    """Verify cascade resolver strips claude-* when ff_anthropic_provider is OFF."""

    def test_resolve_cascade_strips_claude_when_flag_off(self):
        from ai_engine.model_router import resolve_cascade
        with patch("ai_engine.model_router._anthropic_enabled", return_value=False):
            cascade = resolve_cascade("reasoning", "gemini-2.5-flash")
        assert cascade
        assert all(not m.startswith("claude-") for m in cascade)

    def test_resolve_cascade_keeps_claude_when_flag_on(self):
        from ai_engine.model_router import resolve_cascade, _model_health
        # Mark claude as healthy so it isn't filtered for an unrelated reason
        with patch("ai_engine.model_router._anthropic_enabled", return_value=True), \
             patch.object(_model_health, "is_healthy", return_value=True):
            cascade = resolve_cascade("reasoning", "gemini-2.5-flash")
        assert any(m.startswith("claude-") for m in cascade)


class TestChaosGeminiToAnthropicFailover:
    """End-to-end: every Gemini SKU exhausts quota → Anthropic completes."""

    @pytest.mark.asyncio
    async def test_chaos_gemini_quota_exhausted_anthropic_succeeds(self):
        from unittest.mock import AsyncMock
        from ai_engine.client import AIClient

        client = AIClient()
        # Force the cascade to a known sequence Gemini → Gemini → Anthropic
        client._resolve_cascade = lambda task_type, model: [  # type: ignore[method-assign]
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "claude-3-5-sonnet-20241022",
        ]

        # Gemini provider raises quota on every attempt
        gemini_calls = []

        async def gemini_complete(**kwargs):
            gemini_calls.append(kwargs.get("model"))
            raise Exception("exceeded your current quota for model")

        client._provider.complete = gemini_complete  # type: ignore[method-assign]

        # Anthropic provider succeeds
        from ai_engine.client import _AnthropicProvider
        anthropic = _AnthropicProvider()
        anthropic.complete = AsyncMock(return_value="ok-from-anthropic")  # type: ignore[method-assign]
        client._anthropic_provider = anthropic

        # Disable the cache so the call actually hits the provider
        from ai_engine.cache import get_ai_cache
        cache = get_ai_cache()
        with patch.object(cache, "get", return_value=None), \
             patch.object(cache, "put"):
            result = await client.complete(prompt="test", task_type="reasoning")

        assert result == "ok-from-anthropic"
        # Both Gemini SKUs were tried in order before Anthropic took over
        assert gemini_calls == ["gemini-2.5-pro", "gemini-2.5-flash"]
        anthropic.complete.assert_awaited_once()
        assert anthropic.complete.await_args.kwargs["model"] == "claude-3-5-sonnet-20241022"
