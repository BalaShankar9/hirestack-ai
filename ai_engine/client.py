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


# ── Circuit breaker for AI provider ───────────────────────────────────
def _get_ai_breaker():
    """Lazy import to avoid circular dependency at module load."""
    from app.core.circuit_breaker import get_breaker_sync
    return get_breaker_sync("ai_provider", failure_threshold=5, recovery_timeout=60.0)

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
            try:
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


class AIClient:
    """
    Unified AI client — delegates to Gemini provider.

    Integrates a circuit breaker that trips after repeated failures,
    preventing thundering-herd retries against a degraded AI backend.

    Token tracking: every call records prompt/completion token estimates
    accessible via `token_usage` property and `reset_token_usage()`.
    """

    def __init__(self):
        self._provider = _GeminiProvider()
        self.provider_name = "gemini"
        self.model = self._provider.model_name
        self.max_tokens = self._provider.max_tokens
        self._breaker = _get_ai_breaker()
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
        """Rough cost estimate in USD cents based on Gemini 1.5 pricing."""
        # Gemini 1.5 Flash: ~$0.075/1M input, ~$0.30/1M output
        # Gemini 1.5 Pro:   ~$1.25/1M input,  ~$5.00/1M output
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

    def _track_usage(self, prompt: str, response_text: str) -> None:
        """Track token usage after a successful call."""
        self._prompt_tokens += self._estimate_tokens(prompt)
        self._completion_tokens += self._estimate_tokens(response_text)
        self._call_count += 1

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

    @property
    def default_model(self) -> str:
        """The configured default model name."""
        return self._provider.model_name

    async def complete(self, prompt: str, system: Optional[str] = None,
                       max_tokens: Optional[int] = None, temperature: float = 0.7,
                       response_format: str = "text",
                       task_type: Optional[str] = None,
                       model: Optional[str] = None) -> str:
        resolved = self._resolve_model(task_type, model)
        async with self._breaker:
            result = await self._provider.complete(
                prompt=prompt, system=system, max_tokens=max_tokens,
                temperature=temperature, response_format=response_format,
                model=resolved,
            )
            self._track_usage(prompt + (system or ""), result)
            return result

    async def complete_json(self, prompt: str, system: Optional[str] = None,
                            max_tokens: Optional[int] = None,
                            temperature: float = 0.3,
                            schema: Optional[Dict[str, Any]] = None,
                            task_type: Optional[str] = None,
                            model: Optional[str] = None) -> Dict[str, Any]:
        resolved = self._resolve_model(task_type, model)
        async with self._breaker:
            result = await self._provider.complete_json(
                prompt=prompt, system=system, max_tokens=max_tokens,
                temperature=temperature, schema=schema, model=resolved,
            )
            self._track_usage(prompt + (system or ""), json.dumps(result))
            return result

    async def chat(self, messages: List[Dict[str, str]], system: Optional[str] = None,
                   max_tokens: Optional[int] = None,
                   temperature: float = 0.7,
                   task_type: Optional[str] = None,
                   model: Optional[str] = None) -> str:
        resolved = self._resolve_model(task_type, model)
        all_text = " ".join(m.get("content", "") for m in messages)
        async with self._breaker:
            result = await self._provider.chat(
                messages=messages, system=system, max_tokens=max_tokens,
                temperature=temperature, model=resolved,
            )
            self._track_usage(all_text + (system or ""), result)
            return result


# ── JSON helpers ───────────────────────────────────────────────────────

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

    raise ValueError(f"Failed to parse JSON response after repair attempts")


# ── Singleton ──────────────────────────────────────────────────────────
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get singleton AI client instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
