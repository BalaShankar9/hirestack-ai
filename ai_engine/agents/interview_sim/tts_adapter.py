"""
TTS adapter — optional text-to-speech rendering for interview questions.

Default provider: OpenAI TTS (env: OPENAI_API_KEY) — cheaper, faster
than ElevenLabs and we already use OpenAI elsewhere.
Opt-in: ElevenLabs (env: ELEVENLABS_API_KEY).

Both adapters return raw MP3 bytes or None on failure. Never raises
into the orchestrator — failures are logged at debug.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


_TIMEOUT_S = 15.0


class TTSAdapter:
    """Provider-agnostic TTS facade."""

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        openai_key: Optional[str] = None,
        elevenlabs_key: Optional[str] = None,
        client: Optional[object] = None,
    ) -> None:
        self.provider = (provider or os.getenv("INTERVIEW_TTS_PROVIDER") or "openai").lower()
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")
        self.elevenlabs_key = elevenlabs_key or os.getenv("ELEVENLABS_API_KEY")
        self._client = client  # injectable httpx.AsyncClient for tests

    def has_provider(self) -> bool:
        if self.provider == "elevenlabs":
            return bool(self.elevenlabs_key)
        return bool(self.openai_key)

    async def synthesize(self, text: str) -> Optional[bytes]:
        if not text or not text.strip():
            return None
        if not self.has_provider():
            return None
        try:
            if self.provider == "elevenlabs":
                return await self._elevenlabs(text)
            return await self._openai(text)
        except Exception as exc:  # noqa: BLE001
            logger.debug("interview_tts_failed: %s", str(exc)[:200])
            return None

    # ─── providers ──────────────────────────────────────────────────────

    async def _openai(self, text: str) -> Optional[bytes]:
        client, owned = await self._get_client()
        try:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "voice": "alloy",
                    "input": text[:4000],
                    "format": "mp3",
                },
            )
            if resp.status_code != 200:
                logger.debug("openai_tts_status: %s", resp.status_code)
                return None
            data = resp.content
            return data if data and len(data) > 200 else None
        finally:
            if owned:
                await client.aclose()

    async def _elevenlabs(self, text: str) -> Optional[bytes]:
        client, owned = await self._get_client()
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        try:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.elevenlabs_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={"text": text[:4000], "model_id": "eleven_turbo_v2"},
            )
            if resp.status_code != 200:
                logger.debug("elevenlabs_tts_status: %s", resp.status_code)
                return None
            data = resp.content
            return data if data and len(data) > 200 else None
        finally:
            if owned:
                await client.aclose()

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return httpx.AsyncClient(timeout=_TIMEOUT_S), True
