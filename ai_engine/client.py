"""
Claude AI Client
Handles all interactions with the Anthropic Claude API
"""
import json
from typing import Optional, Dict, Any, List
import asyncio

from anthropic import Anthropic, AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class AIClient:
    """Client for Claude API interactions."""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
        self.max_tokens = settings.anthropic_max_tokens

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
        """Send a completion request to Claude."""
        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            system=system or "You are a helpful AI assistant.",
            messages=messages
        )

        content = response.content[0].text

        if response_format == "json":
            # Try to extract JSON from the response
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

        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages
        )

        content = response.content[0].text
        return self._parse_json(content)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7
    ) -> str:
        """Send a chat completion request with message history."""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            system=system or "You are a helpful AI assistant.",
            messages=messages
        )

        return response.content[0].text

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
