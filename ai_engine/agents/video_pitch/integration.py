"""S17-P4 — Video pitch integration: intent + tools + helpers."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ai_engine.agents.tools import AgentTool, ToolRegistry

from .pitch_orchestrator import PitchOrchestrator
from .schemas import VideoPitchInput, VideoPitchPackage

_INTENT_RE = re.compile(
    r"\b(video|avatar)\b.*\b(pitch|intro|introduction|message)\b"
    r"|\b(record|generate|create|make)\b.*\b(video pitch|avatar)\b"
    r"|\bexecutive (video )?pitch\b",
    re.IGNORECASE,
)


def detect_video_pitch_intent(text: str) -> Optional[str]:
    if not text:
        return None
    m = _INTENT_RE.search(text)
    return m.group(0) if m else None


async def create_video_pitch(
    payload: Dict[str, Any],
    ai_client: Optional[Any] = None,
) -> VideoPitchPackage:
    inp = payload if isinstance(payload, VideoPitchInput) \
        else VideoPitchInput(**(payload or {}))
    return await PitchOrchestrator(ai_client=ai_client).create(inp)


async def _create_tool(**kwargs: Any) -> Dict[str, Any]:
    pkg = await create_video_pitch(kwargs.get("input") or kwargs)
    return {"package": pkg.model_dump()}


def build_video_pitch_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        AgentTool(
            name="create_executive_video_pitch",
            description=(
                "Generate a short executive video pitch (script + avatar "
                "manifest + optional TTS audio). Avatar provider is "
                "pluggable (stub default, HeyGen optional)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "description": (
                            "VideoPitchInput with candidate_name, role_target, "
                            "value_prop, key_wins, duration_seconds, "
                            "avatar_style, voice_id, include_audio."
                        ),
                    },
                },
                "required": ["input"],
            },
            fn=_create_tool,
        )
    )
    return reg
