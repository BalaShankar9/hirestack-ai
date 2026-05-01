"""S17-P4 — Exec Video Pitch (avatar add-on) surface."""
from __future__ import annotations

from .avatar_provider import AvatarProvider, HeyGenProvider, StubProvider, get_provider
from .integration import (
    build_video_pitch_tools,
    create_video_pitch,
    detect_video_pitch_intent,
)
from .pitch_orchestrator import PitchOrchestrator
from .schemas import (
    AvatarManifest,
    PitchScript,
    VideoPitchInput,
    VideoPitchPackage,
)
from .script_writer import ScriptWriter

__all__ = [
    "AvatarManifest",
    "AvatarProvider",
    "HeyGenProvider",
    "PitchOrchestrator",
    "PitchScript",
    "ScriptWriter",
    "StubProvider",
    "VideoPitchInput",
    "VideoPitchPackage",
    "build_video_pitch_tools",
    "create_video_pitch",
    "detect_video_pitch_intent",
    "get_provider",
]
