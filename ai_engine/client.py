"""HireStack AI Client — Gemini-backed client facade.

The runtime currently uses Gemini as the sole provider. Retry behavior is still
provider-agnostic so transient transport and quota-related failures are handled
consistently in one place.
"""
import json
import logging
import os
import time
from typing import Optional, Dict, Any, List
import asyncio

from tenacity import (
    retry,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

from app.core.config import settings

logger = logging.getLogger("hirestack.ai_client")


# ── Prompt-injection guardrails ────────────────────────────────────────
# These patterns are stripped from user-supplied content before it enters LLM prompts.
# They defend against common prompt injection attacks where adversarial JD/resume
# content tries to override system instructions.
import re as _re

_INJECTION_PATTERNS = _re.compile(
    r"(?i)"
    r"(?:ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions)"
    r"|(?:you\s+are\s+now\s+(?:a|an)\s+)"
    r"|(?:disregard\s+(?:all\s+)?(?:previous|system)\s+)"
    r"|(?:forget\s+(?:all\s+)?(?:your|previous)\s+instructions)"
    r"|(?:override\s+(?:system|safety)\s+)"
    r"|(?:new\s+instructions?:)"
    r"|(?:system\s*:\s*you\s+are)"
)


def _sanitize_prompt_input(text: str) -> str:
    """Strip known prompt-injection phrases from user-supplied text.

    Does NOT alter legitimate content — only removes adversarial override
    attempts. Applied to user-supplied fields (JD text, resume text) before
    they're interpolated into prompts.
    """
    if not text:
        return text
    cleaned = _INJECTION_PATTERNS.sub("[FILTERED]", text)
    if cleaned != text:
        logger.warning("prompt_injection_attempt_detected", original_length=len(text))
    return cleaned


# ── Per-model circuit breakers ─────────────────────────────────────────
def _get_model_breaker(model_name: str):
    """Return a per-model circuit breaker (lazy import to avoid circular dep)."""
    from app.core.circuit_breaker import get_breaker_sync
    safe_name = model_name.replace("/", "_").replace(".", "_")
    return get_breaker_sync(f"ai_model_{safe_name}", failure_threshold=5, recovery_timeout=60.0)

# ── Provider-agnostic retry logic ──────────────────────────────────────

def _is_quota_exhausted(exc: BaseException) -> bool:
    """Return True if this looks like a hard quota exhaustion (not worth retrying)."""
    err_str = str(exc).lower()
    return any(k in err_str for k in (
        # OpenAI
        "insufficient_quota",
        "exceeded your current quota",
        # Gemini
        "generaterequestsperday",
        "perdayperprojectpermodel",
        "generate_content_free_tier_requests, limit: 0",
    ))


def _is_retryable(exc: BaseException) -> bool:
    """Return True only for errors worth retrying (rate-limit, server, network)."""
    # Don't retry hard quota exhaustion — fall back to another provider instead.
    if _is_quota_exhausted(exc):
        return False

    # OpenAI non-retryable
    try:
        import openai as _oai
        if isinstance(exc, (
            _oai.AuthenticationError,
            _oai.PermissionDeniedError,
            _oai.NotFoundError,
            _oai.BadRequestError,
        )):
            return False
    except ImportError:
        pass

    # Gemini non-retryable (string matching for SDK exceptions)
    err_str = str(exc).lower()
    if any(k in err_str for k in (
        "api key not valid", "permission denied",
        "not found", "invalid argument", "api_key_invalid",
    )):
        return False

    return True


_RETRY_KWARGS: Dict[str, Any] = dict(
    # Gemini free-tier often returns RetryInfo delays in the 30–60s range.
    # Give the SDK time to recover rather than failing the whole pipeline.
    # Stop after 6 attempts OR 120s total — whichever comes first.
    stop=(stop_after_attempt(6) | stop_after_delay(120)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(_is_retryable),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ═══════════════════════════════════════════════════════════════════════
#  Gemini Provider (sole supported backend)
# ═══════════════════════════════════════════════════════════════════════

class _GeminiProvider:
    """Google Gemini backend using the google.genai SDK."""

    def __init__(self):
        self._client = None
        self.model_name = settings.gemini_model
        self.max_tokens = settings.gemini_max_tokens
        # Avoid bursty requests (common cause of 429s on free-tier keys).
        # Default lowered to 100ms for paid-tier; set GEMINI_MIN_INTERVAL_MS=3500 to restore old behaviour.
        self._min_interval_s = max(0.0, float(os.getenv("GEMINI_MIN_INTERVAL_MS", "100")) / 1000.0)
        self._throttle_lock: Optional[asyncio.Lock] = None
        self._last_call_started = 0.0

    def _get_client(self):
        if self._client is None:
            from google import genai
            if settings.gemini_use_vertexai:
                project = (settings.gemini_vertex_project or "").strip()
                location = (settings.gemini_vertex_location or "").strip()
                if not project or not location:
                    raise ValueError(
                        "Gemini Vertex AI is enabled but missing configuration. "
                        "Set GEMINI_VERTEX_PROJECT and GEMINI_VERTEX_LOCATION in backend/.env."
                    )
                self._client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=location,
                )
            else:
                api_key = settings.gemini_api_key
                if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                    raise ValueError(
                        "Gemini API key is not configured. "
                        "Set GEMINI_API_KEY in your backend/.env file."
                    )
                self._client = genai.Client(api_key=api_key, vertexai=False)
        return self._client

    async def _generate_content_throttled(
        self, *, contents: Any, config: Any, model: Optional[str] = None,
    ):
        effective_model = model or self.model_name
        if self._throttle_lock is None:
            # Create lock inside the running loop (py3.9 asyncio primitives can be loop-bound).
            self._throttle_lock = asyncio.Lock()

        # ── Circuit breaker (W8 follow-up) ──────────────────────────
        # Was previously imported but never invoked. Wire it now so a fully
        # down provider fast-fails after _failure_threshold_ consecutive
        # errors instead of cascading retries through every caller.
        # Quota-exhaustion is NOT counted as a breaker failure (handled by
        # routed-model fallback below) — we re-raise as-is to skip the
        # __aexit__ failure recording path.
        _breaker = _get_model_breaker(effective_model)

        async with self._throttle_lock:
            if self._min_interval_s > 0:
                now = time.monotonic()
                wait_s = self._min_interval_s - (now - self._last_call_started)
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
                self._last_call_started = time.monotonic()

            logger.debug(
                "gemini_request: model=%s default_model=%s routed=%s",
                effective_model,
                self.model_name,
                effective_model != self.model_name,
            )
            # Gate the actual SDK call through the breaker. The context
            # manager records success on clean exit and failure on any
            # exception (including CircuitBreakerOpen propagation upstream).
            try:
                async with _breaker:
                    return await asyncio.to_thread(
                        self._get_client().models.generate_content,
                        model=effective_model,
                        contents=contents,
                        config=config,
                    )
            except Exception as exc:
                # Fallback to the default model when the routed model is
                # unavailable or quota-exhausted.  Only attempt fallback
                # when we actually routed to a different model.
                if effective_model != self.model_name and _is_quota_exhausted(exc):
                    logger.warning(
                        "routed_model_fallback: failed_model=%s fallback_model=%s reason=%s",
                        effective_model,
                        self.model_name,
                        str(exc)[:200],
                    )
                    return await asyncio.to_thread(
                        self._get_client().models.generate_content,
                        model=self.model_name,
                        contents=contents,
                        config=config,
                    )
                raise

    @retry(**_RETRY_KWARGS)
    async def complete(
        self, prompt: str, system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.7,
        response_format: str = "text", model: Optional[str] = None,
    ) -> str:
        from google.genai import types
        _modality = getattr(types, "MediaModality", None) or getattr(types, "Modality", None)
        max_out = max(int(max_tokens or self.max_tokens), 64)
        config: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_out,
        }
        if _modality is not None:
            config["response_modalities"] = [_modality.TEXT]
        if system:
            config["system_instruction"] = system
        if response_format == "json":
            config["response_mime_type"] = "application/json"

        response = await self._generate_content_throttled(
            contents=prompt,
            config=types.GenerateContentConfig(**config),
            model=model,
        )
        return response.text or ""

    @retry(**_RETRY_KWARGS)
    async def complete_json(
        self, prompt: str, system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.3,
        schema: Optional[Dict[str, Any]] = None, model: Optional[str] = None,
    ) -> Dict[str, Any]:
        from google.genai import types
        _modality = getattr(types, "MediaModality", None) or getattr(types, "Modality", None)
        max_out = max(int(max_tokens or self.max_tokens), 64)
        system_prompt = (system or "You are a helpful AI assistant.")
        system_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanations, just pure JSON."

        config_kwargs: Dict[str, Any] = dict(
            temperature=temperature,
            max_output_tokens=max_out,
            system_instruction=system_prompt,
            response_mime_type="application/json",
        )
        if _modality is not None:
            config_kwargs["response_modalities"] = [_modality.TEXT]
        if schema:
            try:
                config_kwargs["response_schema"] = schema
            except Exception:
                pass
        config = types.GenerateContentConfig(**config_kwargs)
        response = await self._generate_content_throttled(
            contents=prompt, config=config, model=model,
        )
        content = response.text or ""
        return _parse_json(content)

    async def chat(
        self, messages: List[Dict[str, str]], system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        from google.genai import types
        _modality = getattr(types, "MediaModality", None) or getattr(types, "Modality", None)
        max_out = max(int(max_tokens or self.max_tokens), 64)
        config: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_out,
        }
        if _modality is not None:
            config["response_modalities"] = [_modality.TEXT]
        if system:
            config["system_instruction"] = system

        # Convert OpenAI-style messages to Gemini content format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part(text=msg["content"])],
            ))

        response = await self._generate_content_throttled(
            contents=contents,
            config=types.GenerateContentConfig(**config),
            model=model,
        )
        return response.text or ""


# ═══════════════════════════════════════════════════════════════════════
#  Unified AIClient facade
# ═══════════════════════════════════════════════════════════════════════

def _is_auth_or_permission_error(exc: BaseException) -> bool:
    """Return True if the error is an auth/permission issue (key invalid, leaked, etc.)."""
    err_str = str(exc).lower()
    if any(k in err_str for k in ("resource_exhausted", "resource exhausted", "rate limit", "too many requests", "429")):
        return False
    return any(k in err_str for k in (
        "api key not valid",
        "permission denied",
        "api_key_invalid",
        "unauthenticated",
        "credentials_missing",
        "not configured",
        "missing configuration",
        "leaked",
        "forbidden",
        "401",
        "403",
    ))


class BudgetExceededError(Exception):
    """Raised when the daily token budget is exhausted."""
    pass


class _DailyUsageTracker:
    """Tracks token usage per calendar day for budget enforcement."""

    def __init__(self) -> None:
        self._date: str = ""
        self._tokens: int = 0
        self._cost_usd: float = 0.0
        self._calls: int = 0
        self._cache_hits: int = 0
        self._by_model: Dict[str, Dict[str, Any]] = {}

    def _rotate_if_needed(self) -> None:
        import datetime
        today = datetime.date.today().isoformat()
        if today != self._date:
            if self._date:
                logger.info(
                    "daily_usage_reset: prev_date=%s tokens=%d cost_usd=%.4f calls=%d cache_hits=%d",
                    self._date, self._tokens, self._cost_usd, self._calls, self._cache_hits,
                )
            self._date = today
            self._tokens = 0
            self._cost_usd = 0.0
            self._calls = 0
            self._cache_hits = 0
            self._by_model = {}

    def record(
        self, model: str, input_tokens: int, output_tokens: int,
        task_type: str, chain: str = "",
    ) -> None:
        self._rotate_if_needed()
        total = input_tokens + output_tokens
        self._tokens += total
        self._calls += 1

        # Cost calculation (Gemini 2.5 pricing)
        is_pro = "pro" in model.lower()
        if is_pro:
            cost = (input_tokens * 1.25 / 1_000_000) + (output_tokens * 5.00 / 1_000_000)
        else:
            cost = (input_tokens * 0.075 / 1_000_000) + (output_tokens * 0.30 / 1_000_000)
        self._cost_usd += cost

        # Per-model tracking
        if model not in self._by_model:
            self._by_model[model] = {"tokens": 0, "calls": 0, "cost_usd": 0.0}
        self._by_model[model]["tokens"] += total
        self._by_model[model]["calls"] += 1
        self._by_model[model]["cost_usd"] += cost

        # Structured log for every call (enables cost dashboards)
        logger.info(
            "ai_usage: model=%s task=%s chain=%s in_tok=%d out_tok=%d cost_usd=%.5f daily_total_usd=%.4f",
            model, task_type or "unknown", chain or "-",
            input_tokens, output_tokens, cost, self._cost_usd,
        )

        # Cost alert
        try:
            threshold = settings.ai_cost_alert_threshold_usd
            if self._cost_usd > threshold and (self._cost_usd - cost) <= threshold:
                logger.warning(
                    "COST_ALERT: daily_cost=%.2f exceeds threshold=%.2f",
                    self._cost_usd, threshold,
                )
        except Exception:
            pass

    def record_cache_hit(self) -> None:
        self._rotate_if_needed()
        self._cache_hits += 1

    def is_budget_exceeded(self) -> bool:
        self._rotate_if_needed()
        try:
            limit = settings.ai_max_tokens_per_day
            if limit and limit > 0 and self._tokens >= limit:
                return True
        except Exception:
            pass
        return False

    @property
    def stats(self) -> Dict[str, Any]:
        self._rotate_if_needed()
        return {
            "date": self._date,
            "total_tokens": self._tokens,
            "total_calls": self._calls,
            "total_cost_usd": round(self._cost_usd, 4),
            "cache_hits": self._cache_hits,
            "by_model": dict(self._by_model),
        }


_daily_tracker = _DailyUsageTracker()


def get_daily_usage() -> Dict[str, Any]:
    """Get current daily usage stats (for API endpoints / monitoring)."""
    return _daily_tracker.stats


class AIClient:
    """
    Unified AI client — delegates to Gemini provider.

    Features:
    - Circuit breaker per model (prevents thundering-herd retries)
    - Semantic response cache (SHA-256 dedup, saves 30-50% cost)
    - Per-model cascade failover
    - Daily token budget enforcement
    - Structured cost logging per call
    - Input truncation for overlong contexts
    """

    def __init__(self):
        self._provider = _GeminiProvider()
        self.provider_name = "gemini"
        self.model = self._provider.model_name
        self.max_tokens = self._provider.max_tokens
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._call_count = 0

    @property
    def token_usage(self) -> Dict[str, int]:
        """Current accumulated token usage for this client instance."""
        return {
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "total_tokens": self._prompt_tokens + self._completion_tokens,
            "call_count": self._call_count,
            "estimated_cost_usd_cents": self._estimate_cost_cents(),
        }

    def reset_token_usage(self) -> Dict[str, int]:
        """Reset token counters and return the final snapshot."""
        snapshot = self.token_usage
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._call_count = 0
        return snapshot

    def _estimate_cost_cents(self) -> int:
        """Rough cost estimate in USD cents based on Gemini 2.5 pricing."""
        # Gemini 2.5 Flash: ~$0.075/1M input, ~$0.30/1M output
        # Gemini 2.5 Pro:   ~$1.25/1M input,  ~$5.00/1M output
        is_pro = "pro" in self.model.lower()
        if is_pro:
            input_rate = 1.25 / 1_000_000
            output_rate = 5.00 / 1_000_000
        else:
            input_rate = 0.075 / 1_000_000
            output_rate = 0.30 / 1_000_000
        cost_usd = (self._prompt_tokens * input_rate) + (self._completion_tokens * output_rate)
        return max(0, int(cost_usd * 100))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate (~4 chars per token for English text)."""
        return max(1, len(text) // 4)

    def _track_usage(
        self, prompt: str, response_text: str,
        model: str = "", task_type: str = "", chain: str = "",
    ) -> None:
        """Track token usage after a successful call."""
        in_tok = self._estimate_tokens(prompt)
        out_tok = self._estimate_tokens(response_text)
        self._prompt_tokens += in_tok
        self._completion_tokens += out_tok
        self._call_count += 1
        _daily_tracker.record(
            model=model or self.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            task_type=task_type,
            chain=chain,
        )
        # ── W3 observability: structured per-call audit log ───────────
        # Hashes (not contents) so we can correlate identical prompts/
        # responses across runs without leaking PII into the log stream.
        try:
            import hashlib
            phash = hashlib.sha256((prompt or "").encode("utf-8", "replace")).hexdigest()[:12]
            rhash = hashlib.sha256((response_text or "").encode("utf-8", "replace")).hexdigest()[:12]
            try:
                from app.core.metrics import MetricsCollector
                MetricsCollector.get().record_llm_call(
                    model=model or self.model,
                    task_type=task_type or "unknown",
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                )
            except Exception:
                pass
            logger.info(
                "ai_call_audit: model=%s task=%s in_tok=%d out_tok=%d "
                "prompt_hash=%s response_hash=%s",
                model or self.model, task_type or "unknown",
                in_tok, out_tok, phash, rhash,
            )
        except Exception:
            pass

    @staticmethod
    def _truncate_input(text: str, max_tokens: Optional[int] = None) -> str:
        """Truncate input text if it exceeds the configured max input token limit."""
        try:
            limit = max_tokens or settings.ai_max_input_tokens
        except Exception:
            limit = 50_000
        if limit <= 0:
            return text
        max_chars = limit * 4  # ~4 chars per token
        if len(text) <= max_chars:
            return text
        # Keep first 80% and last 20% to preserve context boundaries
        keep_start = int(max_chars * 0.8)
        keep_end = int(max_chars * 0.2)
        truncated = text[:keep_start] + "\n\n[... content truncated for cost optimization ...]\n\n" + text[-keep_end:]
        logger.info(
            "input_truncated: original_chars=%d truncated_chars=%d limit_tokens=%d",
            len(text), len(truncated), limit,
        )
        return truncated

    def _check_budget(self) -> None:
        """Raise if daily token budget is exceeded."""
        if _daily_tracker.is_budget_exceeded():
            raise BudgetExceededError(
                f"Daily token budget exceeded ({_daily_tracker.stats['total_tokens']:,} tokens). "
                "Requests are paused until the next calendar day."
            )

    def _resolve_model(self, task_type: Optional[str], model: Optional[str]) -> Optional[str]:
        """Resolve model name from task_type or explicit model param."""
        if model:
            return model
        if task_type:
            from ai_engine.model_router import resolve_model
            default = self._provider.model_name
            resolved = resolve_model(task_type, default)
            if resolved != default:
                logger.info(
                    "model_routed: task_type=%s resolved_model=%s default_model=%s",
                    task_type,
                    resolved,
                    default,
                )
            return resolved
        return None

    def _resolve_cascade(self, task_type: Optional[str], model: Optional[str]) -> List[str]:
        """Resolve ordered list of models to try (with failover)."""
        if model:
            return [model]
        if task_type:
            from ai_engine.model_router import resolve_cascade
            return resolve_cascade(task_type, self._provider.model_name)
        return [self._provider.model_name]

    @property
    def default_model(self) -> str:
        """The configured default model name."""
        return self._provider.model_name

    async def complete(self, prompt: str, system: Optional[str] = None,
                       max_tokens: Optional[int] = None, temperature: float = 0.7,
                       response_format: str = "text",
                       task_type: Optional[str] = None,
                       model: Optional[str] = None) -> str:
        self._check_budget()
        prompt = _sanitize_prompt_input(prompt)
        prompt = self._truncate_input(prompt)

        # Cache lookup
        from ai_engine.cache import get_ai_cache
        cache = get_ai_cache()
        cache_model = self._resolve_model(task_type, model) or self.model
        cached = cache.get(
            prompt=prompt, system=system, model=cache_model,
            schema=None, temperature=temperature, max_tokens=max_tokens,
        )
        if cached is not None:
            _daily_tracker.record_cache_hit()
            logger.debug("cache_hit: task_type=%s model=%s", task_type, cache_model)
            return cached

        from ai_engine.model_router import record_model_success, record_model_failure
        from app.core.circuit_breaker import CircuitBreakerOpen
        models = self._resolve_cascade(task_type, model)
        last_exc: Optional[Exception] = None
        for i, candidate_model in enumerate(models):
            breaker = _get_model_breaker(candidate_model)
            try:
                async with breaker:
                    result = await self._provider.complete(
                        prompt=prompt, system=system, max_tokens=max_tokens,
                        temperature=temperature, response_format=response_format,
                        model=candidate_model,
                    )
                    self._track_usage(
                        prompt + (system or ""), result,
                        model=candidate_model, task_type=task_type or "",
                    )
                    record_model_success(candidate_model)
                    # Cache the result
                    cache.put(
                        prompt=prompt, system=system, model=candidate_model,
                        schema=None, temperature=temperature, max_tokens=max_tokens,
                        response=result,
                    )
                    return result
            except CircuitBreakerOpen:
                # Breaker open for this model — skip to next without counting as provider failure
                logger.info("model_breaker_open: skipping=%s", candidate_model)
                if i < len(models) - 1:
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                record_model_failure(candidate_model)
                if i < len(models) - 1:
                    logger.warning(
                        "model_cascade_failover: failed=%s next=%s error=%s",
                        candidate_model, models[i + 1], str(exc)[:200],
                    )
                    try:
                        from app.core.metrics import MetricsCollector
                        MetricsCollector.get().record_model_failover(candidate_model, models[i + 1], str(exc))
                    except Exception:
                        pass
                    continue
                raise

        raise last_exc  # unreachable but satisfies type checker

    async def complete_json(self, prompt: str, system: Optional[str] = None,
                            max_tokens: Optional[int] = None,
                            temperature: float = 0.3,
                            schema: Optional[Dict[str, Any]] = None,
                            task_type: Optional[str] = None,
                            model: Optional[str] = None) -> Dict[str, Any]:
        self._check_budget()
        prompt = _sanitize_prompt_input(prompt)
        prompt = self._truncate_input(prompt)

        # Telemetry helpers (best-effort; never raise into the agent).
        from ai_engine.agent_events import (
            emit_tool_call,
            emit_tool_result,
            emit_policy_decision,
        )
        tool_label = f"ai.{task_type}" if task_type else "ai.complete_json"
        _t0 = time.monotonic()
        emit_tool_call(
            tool_label,
            {"task_type": task_type, "model": model, "temperature": temperature},
        )

        # Cache lookup
        from ai_engine.cache import get_ai_cache
        cache = get_ai_cache()
        cache_model = self._resolve_model(task_type, model) or self.model
        cached = cache.get(
            prompt=prompt, system=system, model=cache_model,
            schema=schema, temperature=temperature, max_tokens=max_tokens,
        )
        if cached is not None:
            _daily_tracker.record_cache_hit()
            logger.debug("cache_hit_json: task_type=%s model=%s", task_type, cache_model)
            emit_tool_result(
                tool_label,
                {"keys": list(cached.keys()) if isinstance(cached, dict) else None},
                latency_ms=int((time.monotonic() - _t0) * 1000),
                cache_hit=True,
                success=True,
            )
            return cached

        from ai_engine.model_router import record_model_success, record_model_failure
        from app.core.circuit_breaker import CircuitBreakerOpen
        models = self._resolve_cascade(task_type, model)
        last_exc: Optional[Exception] = None
        for i, candidate_model in enumerate(models):
            breaker = _get_model_breaker(candidate_model)
            try:
                async with breaker:
                    result = await self._provider.complete_json(
                        prompt=prompt, system=system, max_tokens=max_tokens,
                        temperature=temperature, schema=schema, model=candidate_model,
                    )
                    # Validate response against schema if provided
                    result = _validate_json_response(result, schema)
                    self._track_usage(
                        prompt + (system or ""), json.dumps(result),
                        model=candidate_model, task_type=task_type or "",
                    )
                    record_model_success(candidate_model)
                    # Cache the result
                    cache.put(
                        prompt=prompt, system=system, model=candidate_model,
                        schema=schema, temperature=temperature, max_tokens=max_tokens,
                        response=result,
                    )
                    emit_tool_result(
                        tool_label,
                        {
                            "model": candidate_model,
                            "keys": list(result.keys()) if isinstance(result, dict) else None,
                        },
                        latency_ms=int((time.monotonic() - _t0) * 1000),
                        cache_hit=False,
                        success=True,
                    )
                    return result
            except CircuitBreakerOpen:
                logger.info("model_breaker_open: skipping=%s", candidate_model)
                if i < len(models) - 1:
                    emit_policy_decision(
                        "model_breaker_open",
                        reason=f"breaker open on {candidate_model}, skipping to next",
                        metadata={"failed": candidate_model, "next": models[i + 1]},
                    )
                    continue
                emit_tool_result(
                    tool_label, latency_ms=int((time.monotonic() - _t0) * 1000),
                    success=False, error=f"circuit_breaker_open: {candidate_model}",
                )
                raise
            except Exception as exc:
                last_exc = exc
                record_model_failure(candidate_model)
                if i < len(models) - 1:
                    logger.warning(
                        "model_cascade_failover_json: failed=%s next=%s error=%s",
                        candidate_model, models[i + 1], str(exc)[:200],
                    )
                    emit_policy_decision(
                        "model_cascade_failover",
                        reason=f"{candidate_model} failed → trying {models[i + 1]}",
                        metadata={
                            "failed": candidate_model,
                            "next": models[i + 1],
                            "error": str(exc)[:160],
                        },
                    )
                    try:
                        from app.core.metrics import MetricsCollector
                        MetricsCollector.get().record_model_failover(candidate_model, models[i + 1], str(exc))
                    except Exception:
                        pass
                    continue
                emit_tool_result(
                    tool_label, latency_ms=int((time.monotonic() - _t0) * 1000),
                    success=False, error=str(exc)[:240],
                )
                raise

        raise last_exc

    async def chat(self, messages: List[Dict[str, str]], system: Optional[str] = None,
                   max_tokens: Optional[int] = None,
                   temperature: float = 0.7,
                   task_type: Optional[str] = None,
                   model: Optional[str] = None) -> str:
        self._check_budget()
        # Sanitize user-role messages only (system messages are trusted)
        messages = [
            {**m, "content": _sanitize_prompt_input(m.get("content", ""))} if m.get("role") == "user" else m
            for m in messages
        ]
        from ai_engine.model_router import record_model_success, record_model_failure
        from app.core.circuit_breaker import CircuitBreakerOpen
        models = self._resolve_cascade(task_type, model)
        all_text = " ".join(m.get("content", "") for m in messages)
        last_exc: Optional[Exception] = None
        for i, candidate_model in enumerate(models):
            breaker = _get_model_breaker(candidate_model)
            try:
                async with breaker:
                    result = await self._provider.chat(
                        messages=messages, system=system, max_tokens=max_tokens,
                        temperature=temperature, model=candidate_model,
                    )
                    self._track_usage(
                        all_text + (system or ""), result,
                        model=candidate_model, task_type=task_type or "",
                    )
                    record_model_success(candidate_model)
                    return result
            except CircuitBreakerOpen:
                logger.info("model_breaker_open: skipping=%s", candidate_model)
                if i < len(models) - 1:
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                record_model_failure(candidate_model)
                if i < len(models) - 1:
                    logger.warning(
                        "model_cascade_failover_chat: failed=%s next=%s error=%s",
                        candidate_model, models[i + 1], str(exc)[:200],
                    )
                    try:
                        from app.core.metrics import MetricsCollector
                        MetricsCollector.get().record_model_failover(candidate_model, models[i + 1], str(exc))
                    except Exception:
                        pass
                    continue
                raise

        raise last_exc


# ── JSON helpers ───────────────────────────────────────────────────────

def _validate_json_response(result: Dict[str, Any], schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Light validation of LLM JSON response against the expected schema.

    Fills missing required keys with sensible defaults so downstream code
    never blows up on a ``KeyError``.  Does NOT reject the response — an
    imperfect answer is better than no answer.
    """
    if not schema or not isinstance(result, dict):
        return result

    properties = schema.get("properties", {})
    required = schema.get("required", list(properties.keys()))

    for key in required:
        if key not in result:
            prop_def = properties.get(key, {})
            prop_type = prop_def.get("type", "string")
            if prop_type == "array":
                result[key] = []
            elif prop_type in ("object", "dict"):
                result[key] = {}
            elif prop_type in ("integer", "number"):
                result[key] = 0
            elif prop_type == "boolean":
                result[key] = False
            else:
                result[key] = ""
            logger.debug("json_validation: filled missing key=%s type=%s", key, prop_type)

    return result


def _extract_json(content: str) -> str:
    """Extract JSON from response that may contain markdown."""
    content = content.strip()
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            return content[start:end].strip()
    if "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        if end > start:
            return content[start:end].strip()
    return content


def _parse_json(content: str) -> Dict[str, Any]:
    """Parse JSON from response, including repair of truncated LLM output."""
    content = _extract_json(content)
    if not content or not content.strip():
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try Python-style replacements first
    fixed = content.replace("'", '"').replace("None", "null")
    fixed = fixed.replace("True", "true").replace("False", "false")
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Use json_repair for truncated / malformed LLM responses
    try:
        from json_repair import repair_json
        repaired = repair_json(content, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
        if isinstance(repaired, list):
            return repaired[0] if repaired and isinstance(repaired[0], dict) else {}
        if isinstance(repaired, str):
            return json.loads(repaired)
    except Exception:
        pass

    raise ValueError("Failed to parse JSON response after repair attempts")


# ── Singleton ──────────────────────────────────────────────────────────
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get singleton AI client instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
