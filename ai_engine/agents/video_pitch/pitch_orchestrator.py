"""S17-P4 — End-to-end video pitch orchestration."""
from __future__ import annotations

import base64
import time
from typing import Any, Optional

from ai_engine.agents.interview_sim.tts_adapter import TTSAdapter

from .avatar_provider import AvatarProvider, get_provider
from .schemas import VideoPitchInput, VideoPitchPackage
from .script_writer import ScriptWriter


class PitchOrchestrator:
    def __init__(
        self,
        ai_client: Optional[Any] = None,
        provider: Optional[AvatarProvider] = None,
        tts: Optional[TTSAdapter] = None,
    ) -> None:
        self.writer = ScriptWriter(ai_client=ai_client)
        self.provider = provider or get_provider()
        self.tts = tts

    async def create(self, inp: VideoPitchInput) -> VideoPitchPackage:
        started = time.perf_counter()
        script = await self.writer.write(inp)
        manifest = await self.provider.submit(
            script=script, style=inp.avatar_style, voice_id=inp.voice_id,
        )
        audio_b64: Optional[str] = None
        if inp.include_audio:
            tts = self.tts or TTSAdapter()
            audio = await tts.synthesize(self.writer.to_speech_text(script))
            if audio:
                audio_b64 = base64.b64encode(audio).decode("ascii")
        return VideoPitchPackage(
            script=script,
            manifest=manifest,
            audio_b64=audio_b64,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
