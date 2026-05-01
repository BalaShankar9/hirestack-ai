"""S17-P4 — Pitch script writer (LLM-first, deterministic fallback)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from .schemas import PitchScript, VideoPitchInput

logger = logging.getLogger(__name__)

# Approx speaking rate ≈ 145 wpm → ~2.4 wpsec.
_WORDS_PER_SECOND = 2.4


def _target_word_count(seconds: int) -> int:
    return max(40, min(420, int(seconds * _WORDS_PER_SECOND)))


def _word_count(text: str) -> int:
    return len([w for w in (text or "").split() if w.strip()])


class ScriptWriter:
    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self.ai_client = ai_client

    def _fallback(self, inp: VideoPitchInput) -> PitchScript:
        intro = f"Hi, I'm {inp.candidate_name}."
        hook = (
            f"I'm reaching out about the {inp.role_target} role because "
            + (inp.value_prop or "I see a strong fit between my work and your priorities.")
        )
        wins = inp.key_wins or [
            "delivered measurable outcomes in past roles",
            "operated as both a builder and an operator",
            "kept teams shipping under tight constraints",
        ]
        key_points = [w.strip().rstrip(".") + "." for w in wins[:4]]
        cta = (
            "If this resonates, I'd love a 15-minute conversation to "
            "explore how I can contribute."
        )
        total = _word_count(intro) + _word_count(hook) \
            + sum(_word_count(p) for p in key_points) + _word_count(cta)
        return PitchScript(
            intro=intro, hook=hook, key_points=key_points,
            cta=cta, total_word_count=total,
        )

    async def write(self, inp: VideoPitchInput) -> PitchScript:
        if not inp.candidate_name.strip():
            raise ValueError("candidate_name is required")
        if not inp.role_target.strip():
            raise ValueError("role_target is required")
        target_words = _target_word_count(inp.duration_seconds)
        if not self.ai_client:
            return self._fallback(inp)
        prompt = (
            "Write a concise executive video-pitch script. Return JSON: "
            "{intro, hook, key_points (3-4 strings), cta}. Target ~"
            f"{target_words} total words.\n"
            f"Candidate: {inp.candidate_name}\n"
            f"Role: {inp.role_target}\n"
            f"Value prop: {inp.value_prop}\n"
            f"Key wins: {inp.key_wins}\n"
            f"Style: {inp.avatar_style}\n"
        )
        try:
            payload = await self.ai_client.complete_json(
                prompt=prompt,
                system="You write concise, factual exec pitch scripts.",
                schema={
                    "type": "object",
                    "properties": {
                        "intro": {"type": "string"},
                        "hook": {"type": "string"},
                        "key_points": {"type": "array",
                                        "items": {"type": "string"}},
                        "cta": {"type": "string"},
                    },
                    "required": ["intro", "hook", "key_points", "cta"],
                },
                temperature=0.5,
                task_type="video_pitch_script",
            )
        except Exception as exc:
            logger.info("video pitch LLM fallback: %s", exc)
            return self._fallback(inp)
        intro = (payload or {}).get("intro", "").strip()
        hook = (payload or {}).get("hook", "").strip()
        key_points = [
            str(p).strip() for p in (payload or {}).get("key_points", [])
            if str(p).strip()
        ]
        cta = (payload or {}).get("cta", "").strip()
        if not intro or not hook or not key_points or not cta:
            return self._fallback(inp)
        total = _word_count(intro) + _word_count(hook) \
            + sum(_word_count(p) for p in key_points) + _word_count(cta)
        return PitchScript(
            intro=intro, hook=hook, key_points=key_points[:4],
            cta=cta, total_word_count=total,
        )

    def to_speech_text(self, script: PitchScript) -> str:
        parts = [script.intro, script.hook]
        parts.extend(script.key_points)
        parts.append(script.cta)
        return " ".join(p.strip() for p in parts if p.strip())
