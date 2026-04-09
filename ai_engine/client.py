"""
HireStack AI Client — Gemini Provider (Paid Tier)
Uses the Google Gemini API for all AI operations.
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
    wait_exponential,
    retry_if_exception,
)

from app.core.config import settings

logger = logging.getLogger("hirestack.ai_client")

# ── Retry logic ────────────────────────────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    """Return True only for errors worth retrying (rate-limit, server, network)."""
    err_str = str(exc).lower()
    # Don't retry auth/config errors
    if any(k in err_str for k in (
        "api key not valid", "permission denied",
        "not found", "invalid argument", "api_key_invalid",
    )):
        return False
    return True


_RETRY_KWARGS: Dict[str, Any] = dict(
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


# ═══════════════════════════════════════════════════════════════════════
#  Gemini Provider
# ═══════════════════════════════════════════════════════════════════════

class _GeminiProvider:
    """Google Gemini backend using the google.genai SDK."""

    def __init__(self):
        self._client = None
        self.model_name = settings.gemini_model
        self.max_tokens = settings.gemini_max_tokens
        # Throttle interval between API calls (ms). Paid tier can handle
        # much higher throughput — set to 500ms as a light safety buffer.
        self._min_interval_s = max(0.0, float(os.getenv("GEMINI_MIN_INTERVAL_MS", "500")) / 1000.0)
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
        response = await self._generate_content_throttled(contents=prompt, config=config)
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
        )
        return response.text or ""


# ═══════════════════════════════════════════════════════════════════════
#  Unified AIClient — Gemini only (paid tier)
# ═══════════════════════════════════════════════════════════════════════

class AIClient:
    """Unified AI client — delegates all calls to Google Gemini (paid tier)."""

    def __init__(self):
        self._provider = _GeminiProvider()
        self.provider_name = "gemini"
        self.model = self._provider.model_name
        self.max_tokens = self._provider.max_tokens

    async def complete(self, prompt: str, system: Optional[str] = None,
                       max_tokens: Optional[int] = None, temperature: float = 0.7,
                       response_format: str = "text",
                       task_type: Optional[str] = None,
                       model: Optional[str] = None) -> str:
        return await self._provider.complete(
            prompt=prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, response_format=response_format,
            model=model,
        )

    async def complete_json(self, prompt: str, system: Optional[str] = None,
                            max_tokens: Optional[int] = None,
                            temperature: float = 0.3,
                            schema: Optional[Dict[str, Any]] = None,
                            task_type: Optional[str] = None,
                            model: Optional[str] = None) -> Dict[str, Any]:
        return await self._provider.complete_json(
            prompt=prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, schema=schema, model=model,
        )

    async def chat(self, messages: List[Dict[str, str]], system: Optional[str] = None,
                   max_tokens: Optional[int] = None,
                   temperature: float = 0.7,
                   task_type: Optional[str] = None,
                   model: Optional[str] = None) -> str:
        return await self._provider.chat(
            messages=messages, system=system, max_tokens=max_tokens,
            temperature=temperature, model=model,
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
