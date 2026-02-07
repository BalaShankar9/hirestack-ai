"""
OpenAI AI Client
Handles all interactions with the OpenAI API (GPT-4o / GPT-4.1)
"""
import json
from typing import Optional, Dict, Any, List
import asyncio

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class AIClient:
    """Client for OpenAI API interactions."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.max_tokens = settings.openai_max_tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        response_format: str = "text"
    ) -> str:
        """Send a completion request to OpenAI."""
        messages = [
            {"role": "system", "content": system or "You are a helpful AI assistant."},
            {"role": "user", "content": prompt},
        ]

        kwargs: Dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=messages,
        )

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content or ""

        if response_format == "json":
            content = self._extract_json(content)

        return content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def complete_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Send a completion request expecting JSON response."""
        system_prompt = system or "You are a helpful AI assistant."
        system_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanations, just pure JSON."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=messages,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or ""
        return self._parse_json(content)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7
    ) -> str:
        """Send a chat completion request with message history."""
        chat_messages: List[Dict[str, str]] = [
            {"role": "system", "content": system or "You are a helpful AI assistant."},
            *messages,
        ]

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=chat_messages,
        )

        return response.choices[0].message.content or ""

    def _extract_json(self, content: str) -> str:
        """Extract JSON from response that may contain markdown."""
        content = content.strip()

        # Try to find JSON in code blocks
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

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Parse JSON from response."""
        content = self._extract_json(content)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Try to fix common issues
            content = content.replace("'", '"')
            content = content.replace("None", "null")
            content = content.replace("True", "true")
            content = content.replace("False", "false")

            try:
                return json.loads(content)
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse JSON response: {str(e)}")


# Singleton instance
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get singleton AI client instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
