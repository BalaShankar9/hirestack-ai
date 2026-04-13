"""Tests for operations hardening round 2: circuit breaker, token cache, rate limits, exception handling."""
import asyncio
import time
import pytest


# ═══════════════════════════════════════════════════════════════════════
#  Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    """Circuit breaker state machine tests."""

    def _make_breaker(self, **kwargs):
        from app.core.circuit_breaker import CircuitBreaker
        return CircuitBreaker(name="test", **kwargs)

    @pytest.mark.asyncio
    async def test_starts_closed(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_stays_closed_under_threshold(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=3)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 2

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        from app.core.circuit_breaker import CircuitBreakerOpen
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=60.0)
        await cb.record_failure()
        await cb.record_failure()
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await cb._before_call()
        assert "test" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=0.01)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.02)
        await cb._before_call()  # Should transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=0.01)
        await cb.record_failure()
        await cb.record_failure()
        await asyncio.sleep(0.02)
        await cb._before_call()  # HALF_OPEN
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=0.01)
        await cb.record_failure()
        await cb.record_failure()
        await asyncio.sleep(0.02)
        await cb._before_call()  # HALF_OPEN
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_reset(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=2)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        await cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        from app.core.circuit_breaker import CircuitState
        cb = self._make_breaker(failure_threshold=3)
        await cb.record_failure()
        async with cb:
            pass  # success
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_context_manager_failure(self):
        cb = self._make_breaker(failure_threshold=3)
        with pytest.raises(ValueError):
            async with cb:
                raise ValueError("test error")
        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_context_manager_rejects_when_open(self):
        from app.core.circuit_breaker import CircuitBreakerOpen
        cb = self._make_breaker(failure_threshold=2, recovery_timeout=60.0)
        await cb.record_failure()
        await cb.record_failure()
        with pytest.raises(CircuitBreakerOpen):
            async with cb:
                pass  # Should never run


class TestCircuitBreakerRegistry:
    """Test the global breaker registry."""

    def test_get_breaker_sync_creates(self):
        from app.core.circuit_breaker import get_breaker_sync, reset_all_breakers
        reset_all_breakers()
        b1 = get_breaker_sync("test_sync")
        b2 = get_breaker_sync("test_sync")
        assert b1 is b2

    def test_different_names_different_breakers(self):
        from app.core.circuit_breaker import get_breaker_sync, reset_all_breakers
        reset_all_breakers()
        b1 = get_breaker_sync("a")
        b2 = get_breaker_sync("b")
        assert b1 is not b2

    @pytest.mark.asyncio
    async def test_get_breaker_async(self):
        from app.core.circuit_breaker import get_breaker, reset_all_breakers
        reset_all_breakers()
        b1 = await get_breaker("test_async")
        b2 = await get_breaker("test_async")
        assert b1 is b2

    def test_reset_all(self):
        from app.core.circuit_breaker import get_breaker_sync, reset_all_breakers, _breakers
        get_breaker_sync("x")
        get_breaker_sync("y")
        reset_all_breakers()
        assert len(_breakers) == 0


# ═══════════════════════════════════════════════════════════════════════
#  Token Verification Cache
# ═══════════════════════════════════════════════════════════════════════

class TestTokenCache:
    """Test the LRU token verification cache."""

    def _make_cache(self, max_size=10):
        from app.core.database import _TokenCache
        return _TokenCache(max_size=max_size)

    def test_miss_returns_none(self):
        cache = self._make_cache()
        assert cache.get("nonexistent-token") is None

    def test_put_and_get(self):
        cache = self._make_cache()
        claims = {"sub": "user-1", "email": "a@b.com", "exp": time.time() + 300}
        cache.put("token-abc", claims)
        result = cache.get("token-abc")
        assert result is not None
        assert result["sub"] == "user-1"

    def test_expired_token_returns_none(self):
        cache = self._make_cache()
        claims = {"sub": "user-1", "exp": time.time() - 10}  # Already expired
        cache.put("expired-token", claims)
        result = cache.get("expired-token")
        assert result is None

    def test_eviction_on_max_size(self):
        cache = self._make_cache(max_size=2)
        cache.put("token-1", {"sub": "1", "exp": time.time() + 300})
        cache.put("token-2", {"sub": "2", "exp": time.time() + 300})
        cache.put("token-3", {"sub": "3", "exp": time.time() + 300})  # Should evict token-1
        assert cache.get("token-1") is None
        assert cache.get("token-2") is not None
        assert cache.get("token-3") is not None

    def test_lru_ordering(self):
        cache = self._make_cache(max_size=2)
        cache.put("token-a", {"sub": "a", "exp": time.time() + 300})
        cache.put("token-b", {"sub": "b", "exp": time.time() + 300})
        # Access token-a to make it recently used
        cache.get("token-a")
        cache.put("token-c", {"sub": "c", "exp": time.time() + 300})  # Should evict token-b
        assert cache.get("token-a") is not None
        assert cache.get("token-b") is None
        assert cache.get("token-c") is not None

    def test_invalidate(self):
        cache = self._make_cache()
        cache.put("token-x", {"sub": "x", "exp": time.time() + 300})
        cache.invalidate("token-x")
        assert cache.get("token-x") is None

    def test_clear(self):
        cache = self._make_cache()
        cache.put("t1", {"sub": "1", "exp": time.time() + 300})
        cache.put("t2", {"sub": "2", "exp": time.time() + 300})
        cache.clear()
        assert cache.get("t1") is None
        assert cache.get("t2") is None

    def test_no_exp_uses_default_ttl(self):
        cache = self._make_cache()
        # No exp claim — should default to ~5 min expiry
        cache.put("no-exp", {"sub": "noexp"})
        result = cache.get("no-exp")
        assert result is not None
        assert result["sub"] == "noexp"

    def test_key_is_hashed_not_plaintext(self):
        cache = self._make_cache()
        cache.put("secret-token-123", {"sub": "u", "exp": time.time() + 300})
        # The internal keys should be hashes, not the raw token
        for key in cache._cache.keys():
            assert "secret-token-123" not in key


# ═══════════════════════════════════════════════════════════════════════
#  Circuit Breaker Integration with AI Client
# ═══════════════════════════════════════════════════════════════════════

class TestAIClientCircuitBreaker:
    """Test that AIClient uses per-model circuit breakers."""

    def test_client_has_breaker(self):
        from ai_engine.client import _get_model_breaker
        breaker = _get_model_breaker("gemini-2.5-pro")
        assert breaker is not None
        assert "gemini" in breaker.name

    def test_breaker_failure_threshold(self):
        from ai_engine.client import _get_model_breaker
        breaker = _get_model_breaker("gemini-2.5-flash")
        assert breaker.failure_threshold == 5


# ═══════════════════════════════════════════════════════════════════════
#  CircuitBreakerOpen HTTP Response
# ═══════════════════════════════════════════════════════════════════════

class TestCircuitBreakerHTTPResponse:
    """Test that circuit breaker open errors produce proper error messages."""

    def test_error_message(self):
        from app.core.circuit_breaker import CircuitBreakerOpen
        err = CircuitBreakerOpen("ai_provider", 45.0)
        assert "ai_provider" in str(err)
        assert err.remaining_s == 45.0

    def test_error_attributes(self):
        from app.core.circuit_breaker import CircuitBreakerOpen
        err = CircuitBreakerOpen("gemini", 30.5)
        assert err.name == "gemini"
        assert err.remaining_s == 30.5


# ═══════════════════════════════════════════════════════════════════════
#  UUID Validation on Job Endpoints
# ═══════════════════════════════════════════════════════════════════════

class TestJobUUIDValidation:
    """Test that job_id parameters are validated as UUIDs."""

    def test_valid_uuid(self):
        from app.api.deps import validate_uuid
        result = validate_uuid("d82916b4-99ea-43e2-b6e9-fc503f54ea7c")
        assert result == "d82916b4-99ea-43e2-b6e9-fc503f54ea7c"

    def test_invalid_uuid_raises(self):
        from fastapi import HTTPException
        from app.api.deps import validate_uuid
        with pytest.raises(HTTPException) as exc_info:
            validate_uuid("not-a-uuid")
        assert exc_info.value.status_code == 422

    def test_empty_string_raises(self):
        from fastapi import HTTPException
        from app.api.deps import validate_uuid
        with pytest.raises(HTTPException):
            validate_uuid("")

    def test_sql_injection_attempt_rejected(self):
        from fastapi import HTTPException
        from app.api.deps import validate_uuid
        with pytest.raises(HTTPException):
            validate_uuid("'; DROP TABLE users; --")


# ═══════════════════════════════════════════════════════════════════════
#  Bare Exception Handler Fixes
# ═══════════════════════════════════════════════════════════════════════

class TestBareExceptionHandlerFixes:
    """Verify that previously-bare exception handlers now log properly."""

    def test_classify_ai_error_returns_none_for_unknown(self):
        """_classify_ai_error should return None for non-AI errors."""
        import sys
        sys.path.insert(0, ".")
        from app.api.routes.generate import _classify_ai_error
        result = _classify_ai_error(RuntimeError("some random error"))
        assert result is None

    def test_classify_ai_error_detects_rate_limit(self):
        from app.api.routes.generate import _classify_ai_error
        result = _classify_ai_error(Exception("429 Resource exhausted"))
        assert result is not None
        assert result["code"] == 429

    def test_classify_ai_error_detects_auth(self):
        from app.api.routes.generate import _classify_ai_error
        result = _classify_ai_error(Exception("API key not valid"))
        assert result is not None
        assert result["code"] == 401

    def test_classify_ai_error_detects_permission(self):
        from app.api.routes.generate import _classify_ai_error
        result = _classify_ai_error(Exception("Permission denied for this model"))
        assert result is not None
        assert result["code"] == 403
