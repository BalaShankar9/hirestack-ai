"""S17-P4 — Video pitch Pydantic v2 schemas."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AvatarStyle = Literal["professional", "friendly", "executive", "creative"]
ManifestStatus = Literal["queued", "ready", "failed"]


class PitchScript(BaseModel):
    model_config = ConfigDict(extra="ignore")
    intro: str
    hook: str
    key_points: List[str]
    cta: str
    total_word_count: int


class VideoPitchInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    candidate_name: str
    role_target: str
    value_prop: str = ""
    key_wins: List[str] = Field(default_factory=list)
    duration_seconds: int = Field(60, ge=15, le=180)
    avatar_style: AvatarStyle = "professional"
    voice_id: Optional[str] = None
    include_audio: bool = False


class AvatarManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    provider: str
    avatar_id: str
    voice_id: Optional[str] = None
    style: AvatarStyle
    status: ManifestStatus
    video_url: Optional[str] = None
    job_id: Optional[str] = None
    error: Optional[str] = None


class VideoPitchPackage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    script: PitchScript
    manifest: AvatarManifest
    audio_b64: Optional[str] = None
    latency_ms: int = 0
