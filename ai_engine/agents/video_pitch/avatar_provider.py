"""S17-P4 — Avatar provider abstraction (HeyGen + offline stub)."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Optional, Protocol

from .schemas import AvatarManifest, AvatarStyle, PitchScript

logger = logging.getLogger(__name__)


class AvatarProvider(Protocol):
    name: str

    async def submit(
        self,
        *,
        script: PitchScript,
        style: AvatarStyle,
        voice_id: Optional[str] = None,
    ) -> AvatarManifest:
        ...


class StubProvider:
    """Deterministic offline provider. Always returns status=queued."""
    name = "stub"

    async def submit(
        self,
        *,
        script: PitchScript,
        style: AvatarStyle,
        voice_id: Optional[str] = None,
    ) -> AvatarManifest:
        digest = hashlib.sha1(
            (script.intro + script.cta + style).encode("utf-8")
        ).hexdigest()[:12]
        return AvatarManifest(
            provider=self.name,
            avatar_id=f"stub-{style}-{digest}",
            voice_id=voice_id or "stub-voice",
            style=style,
            status="queued",
            job_id=f"stub-job-{digest}",
        )


_HEYGEN_AVATAR_BY_STYLE = {
    "professional": "Daisy-inskirt-20220818",
    "friendly": "Daisy-inskirt-20220818",
    "executive": "Daisy-inskirt-20220818",
    "creative": "Daisy-inskirt-20220818",
}
_HEYGEN_TIMEOUT_S = 20.0


class HeyGenProvider:
    """HeyGen v2 video.generate provider (queued submission)."""
    name = "heygen"

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("HEYGEN_API_KEY", "")
        self._client = client

    def has_credentials(self) -> bool:
        return bool(self.api_key)

    async def submit(
        self,
        *,
        script: PitchScript,
        style: AvatarStyle,
        voice_id: Optional[str] = None,
    ) -> AvatarManifest:
        avatar_id = _HEYGEN_AVATAR_BY_STYLE.get(style,
                                                _HEYGEN_AVATAR_BY_STYLE["professional"])
        text = " ".join([script.intro, script.hook, *script.key_points, script.cta])[:1500]
        if not self.has_credentials():
            return AvatarManifest(
                provider=self.name, avatar_id=avatar_id, voice_id=voice_id,
                style=style, status="failed",
                error="missing HEYGEN_API_KEY",
            )
        client, owned = await self._get_client()
        try:
            resp = await client.post(
                "https://api.heygen.com/v2/video/generate",
                headers={
                    "X-Api-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "video_inputs": [
                        {
                            "character": {
                                "type": "avatar",
                                "avatar_id": avatar_id,
                                "avatar_style": "normal",
                            },
                            "voice": {
                                "type": "text",
                                "input_text": text,
                                "voice_id": voice_id or "1bd001e7e50f421d891986aad5158bc8",
                            },
                        }
                    ],
                    "dimension": {"width": 1280, "height": 720},
                },
            )
            if resp.status_code >= 300:
                return AvatarManifest(
                    provider=self.name, avatar_id=avatar_id,
                    voice_id=voice_id, style=style, status="failed",
                    error=f"heygen_status={resp.status_code}",
                )
            data = resp.json()
            video_id = (data.get("data") or {}).get("video_id")
            return AvatarManifest(
                provider=self.name,
                avatar_id=avatar_id,
                voice_id=voice_id,
                style=style,
                status="queued",
                job_id=video_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("heygen submit failed: %s", exc)
            return AvatarManifest(
                provider=self.name, avatar_id=avatar_id,
                voice_id=voice_id, style=style, status="failed",
                error=str(exc)[:200],
            )
        finally:
            if owned:
                await client.aclose()

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return httpx.AsyncClient(timeout=_HEYGEN_TIMEOUT_S), True


def get_provider(name: Optional[str] = None) -> AvatarProvider:
    name = (name or os.getenv("VIDEO_AVATAR_PROVIDER") or "stub").lower()
    if name == "heygen":
        return HeyGenProvider()
    return StubProvider()
