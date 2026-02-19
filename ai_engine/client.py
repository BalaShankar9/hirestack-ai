"""
HireStack AI Client — Multi-provider (Gemini + OpenAI + Ollama) with Automatic Fallback
Tries the configured primary provider first; on auth/permission or quota/rate-limit
errors, automatically retries with the next available provider (prefers local
Ollama as the first fallback).
"""
import json
import logging
import os
import time
from typing import Optional, Dict, Any, List
import asyncio

import httpx

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

from app.core.config import settings

logger = logging.getLogger("hirestack.ai_client")

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
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


# ═══════════════════════════════════════════════════════════════════════
#  OpenAI Provider
# ═══════════════════════════════════════════════════════════════════════

class _OpenAIProvider:
    """OpenAI ChatCompletions backend."""

    def __init__(self):
        if not (settings.openai_api_key or "").strip():
            raise ValueError("OpenAI API key is not configured (set OPENAI_API_KEY).")
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.max_tokens = settings.openai_max_tokens

    @retry(**_RETRY_KWARGS)
    async def complete(
        self, prompt: str, system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.7,
        response_format: str = "text",
    ) -> str:
        messages = [
            {"role": "system", "content": system or "You are a helpful AI assistant."},
            {"role": "user", "content": prompt},
        ]
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            max_completion_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=messages,
        )
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    @retry(**_RETRY_KWARGS)
    async def complete_json(
        self, prompt: str, system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.3,
    ) -> Dict[str, Any]:
        system_prompt = (system or "You are a helpful AI assistant.")
        system_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanations, just pure JSON."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        response = await self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return _parse_json(content)

    async def chat(
        self, messages: List[Dict[str, str]], system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.7,
    ) -> str:
        chat_messages = [
            {"role": "system", "content": system or "You are a helpful AI assistant."},
            *messages,
        ]
        response = await self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=chat_messages,
        )
        return response.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════════════════
#  Gemini Provider
# ═══════════════════════════════════════════════════════════════════════

class _GeminiProvider:
    """Google Gemini backend using the google.genai SDK."""

    def __init__(self):
        self._client = None
        self.model_name = settings.gemini_model
        self.max_tokens = settings.gemini_max_tokens
        # Avoid bursty requests (common cause of 429s on free-tier keys).
        # Set to 0 to disable throttling.
        self._min_interval_s = max(0.0, float(os.getenv("GEMINI_MIN_INTERVAL_MS", "3500")) / 1000.0)
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

    async def _generate_content_throttled(self, *, contents: Any, config: Any):
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

            return await asyncio.to_thread(
                self._get_client().models.generate_content,
                model=self.model_name,
                contents=contents,
                config=config,
            )

    @retry(**_RETRY_KWARGS)
    async def complete(
        self, prompt: str, system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.7,
        response_format: str = "text",
    ) -> str:
        from google.genai import types
        # google-genai renamed Modality → MediaModality in newer releases.
        _modality = getattr(types, "MediaModality", None) or getattr(types, "Modality", None)
        max_out = max(int(max_tokens or self.max_tokens), 64)
        config: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_out,
        }
        if _modality is not None:
            # Some Gemini models may return "thoughts" only unless we explicitly request TEXT output.
            config["response_modalities"] = [_modality.TEXT]
        if system:
            config["system_instruction"] = system
        if response_format == "json":
            config["response_mime_type"] = "application/json"

        response = await self._generate_content_throttled(
            contents=prompt,
            config=types.GenerateContentConfig(**config),
        )
        return response.text or ""

    @retry(**_RETRY_KWARGS)
    async def complete_json(
        self, prompt: str, system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.3,
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
        config = types.GenerateContentConfig(**config_kwargs)
        response = await self._generate_content_throttled(contents=prompt, config=config)
        content = response.text or ""
        return _parse_json(content)

    async def chat(
        self, messages: List[Dict[str, str]], system: Optional[str] = None,
        max_tokens: Optional[int] = None, temperature: float = 0.7,
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
        )
        return response.text or ""


class _OllamaProvider:
    """Local Ollama backend (http://127.0.0.1:11434) for offline development."""

    def __init__(self):
        self.base_url = (settings.ollama_base_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = (settings.ollama_model or "qwen3:4b").strip()
        self.max_tokens = int(settings.ollama_max_tokens or 2048)
        self._timeout_s = float(os.getenv("OLLAMA_TIMEOUT_S", "180"))

    async def _chat_once(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        response_format: str,
    ) -> str:
        num_predict = int(max_tokens or self.max_tokens)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": float(temperature),
                "num_predict": num_predict,
            },
        }
        if response_format == "json":
            payload["format"] = "json"

        timeout = httpx.Timeout(self._timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = (e.response.text or "").replace("\n", " ")[:500]
                raise RuntimeError(f"Ollama HTTP {e.response.status_code}: {body}") from e
            except httpx.RequestError as e:
                raise RuntimeError(f"Ollama request failed: {type(e).__name__}: {str(e)[:200]}") from e

            data = resp.json()
            msg = (data.get("message") or {}).get("content") or ""
            return str(msg)

    @retry(**_RETRY_KWARGS)
    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        response_format: str = "text",
    ) -> str:
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return (await self._chat_once(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )).strip()

    @retry(**_RETRY_KWARGS)
    async def complete_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        system_prompt = (system or "You are a helpful AI assistant.")
        system_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanations, just pure JSON."
        content = await self.complete(
            prompt,
            system=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format="json",
        )
        return _parse_json(content)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> str:
        chat_messages: List[Dict[str, str]] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        for msg in messages:
            role = msg.get("role", "user")
            if role not in ("system", "user", "assistant"):
                role = "user" if role == "model" else "assistant"
            chat_messages.append({"role": role, "content": msg.get("content", "")})
        return (await self._chat_once(
            messages=chat_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="text",
        )).strip()


# ═══════════════════════════════════════════════════════════════════════
#  Unified AIClient facade with automatic fallback
# ═══════════════════════════════════════════════════════════════════════

def _is_auth_or_permission_error(exc: BaseException) -> bool:
    """Return True if the error is an auth/permission issue (key invalid, leaked, etc.)."""
    # OpenAI auth errors
    try:
        import openai as _oai
        if isinstance(exc, (_oai.AuthenticationError, _oai.PermissionDeniedError)):
            return True
    except ImportError:
        pass
    # Gemini / generic auth errors (string matching)
    err_str = str(exc).lower()
    # Never treat rate limits / quota exhaustion as auth errors — falling back
    # would just double the calls and worsen throttling.
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


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True if this looks like a quota/rate-limit issue (fallback may help)."""
    err_str = str(exc).lower()
    return (
        any(k in err_str for k in (
            "resource_exhausted",
            "resource exhausted",
            "rate limit",
            "too many requests",
            "429",
        ))
        or _is_quota_exhausted(exc)
    )


def _is_json_parse_error(exc: BaseException) -> bool:
    """Return True if the provider returned invalid/truncated JSON."""
    return isinstance(exc, ValueError) and "parse json" in str(exc).lower()


class AIClient:
    """
    Unified AI client — delegates to the configured provider and automatically
    falls back to the next available provider on:
      - auth/permission/config errors
      - quota/rate-limit errors
      - invalid/truncated JSON (for JSON calls)

    Provider order:
      1) `AI_PROVIDER` (default: gemini)
      2) `ollama` (local) if not primary
      3) the remaining cloud provider
    """

    def __init__(self):
        provider = (settings.ai_provider or "gemini").lower().strip()
        if provider not in ("gemini", "openai", "ollama"):
            logger.warning("unknown_ai_provider=%s; defaulting_to=gemini", provider)
            provider = "gemini"

        def build(name: str):
            if name == "gemini":
                return _GeminiProvider()
            if name == "openai":
                return _OpenAIProvider()
            if name == "ollama":
                return _OllamaProvider()
            raise ValueError(f"Unknown provider: {name}")

        order: List[str] = [provider]
        # Prefer local Ollama as the first fallback.
        if provider != "ollama":
            order.append("ollama")
        for name in ("gemini", "openai"):
            if name != provider:
                order.append(name)

        self._providers: List[tuple[str, Any]] = []
        for name in dict.fromkeys(order):  # preserve order, drop dupes
            try:
                self._providers.append((name, build(name)))
            except Exception as e:
                logger.warning("provider_init_failed (%s): %s", name, str(e).replace("\n", " ")[:200])

        if not self._providers:
            raise RuntimeError("No AI providers available. Configure keys or enable Ollama.")

        active = self._providers[0][1]
        self.provider_name = self._providers[0][0]
        self.model = getattr(active, "model", None) or getattr(active, "model_name", "unknown")
        self.max_tokens = getattr(active, "max_tokens", 4096)

    async def _call_with_fallback(self, method_name: str, **kwargs):
        """Try providers in order; fall back on auth, quota/rate-limit, or parse errors."""
        last_error: Optional[BaseException] = None
        for idx, (name, prov) in enumerate(self._providers):
            try:
                method = getattr(prov, method_name)
                result = await method(**kwargs)
                if idx > 0:
                    logger.info("fallback_success: %s → %s", self._providers[0][0], name)
                self.provider_name = name
                self.model = getattr(prov, "model", None) or getattr(prov, "model_name", self.model)
                self.max_tokens = getattr(prov, "max_tokens", self.max_tokens)
                return result
            except Exception as e:
                last_error = e
                is_last = idx >= (len(self._providers) - 1)
                if is_last:
                    raise

                if _is_auth_or_permission_error(e) or _is_rate_limit_error(e) or _is_json_parse_error(e):
                    logger.warning(
                        "provider_failed (%s): %s — trying next provider (%s)",
                        name, str(e).replace("\n", " ")[:140], self._providers[idx + 1][0],
                    )
                    continue

                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("AI call failed unexpectedly.")

    async def complete(self, prompt: str, system: Optional[str] = None,
                       max_tokens: Optional[int] = None, temperature: float = 0.7,
                       response_format: str = "text") -> str:
        return await self._call_with_fallback(
            "complete", prompt=prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, response_format=response_format,
        )

    async def complete_json(self, prompt: str, system: Optional[str] = None,
                            max_tokens: Optional[int] = None,
                            temperature: float = 0.3) -> Dict[str, Any]:
        return await self._call_with_fallback(
            "complete_json", prompt=prompt, system=system, max_tokens=max_tokens,
            temperature=temperature,
        )

    async def chat(self, messages: List[Dict[str, str]], system: Optional[str] = None,
                   max_tokens: Optional[int] = None,
                   temperature: float = 0.7) -> str:
        return await self._call_with_fallback(
            "chat", messages=messages, system=system, max_tokens=max_tokens,
            temperature=temperature,
        )


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
    """Parse JSON from response."""
    content = _extract_json(content)
    if not content or not content.strip():
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        content = content.replace("'", '"').replace("None", "null")
        content = content.replace("True", "true").replace("False", "false")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse JSON response: {str(e)}")


# ── Singleton ──────────────────────────────────────────────────────────
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get singleton AI client instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
