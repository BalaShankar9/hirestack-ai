"""Voice Guard — deterministic banned-phrase detection for generated documents.

Wave 0 / V1 (tone reversal). Catches the formulaic phrases that make
AI-generated cover letters and CVs sound interchangeable. The presence
of any banned phrase deducts from `tone_match` and injects a high-severity
issue into the critic's feedback so the revision loop fixes it.

This is intentionally a pure-Python module with no AI client, so it runs
on every critic pass at ~0 cost and is fully unit-testable.

Voice presets:
- ``confident_selective`` (default): assumes mutual fit; no apologetics;
  no enthusiasm theatre.
- ``warm_eager``: legacy tone — keeps "excited", drops "passionate about".
- ``formal_traditional``: keeps "would welcome the opportunity"; drops
  "love" / "passionate".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable, Literal

VoicePreset = Literal["confident_selective", "warm_eager", "formal_traditional"]
DEFAULT_VOICE: VoicePreset = "confident_selective"

# Phrases that flatten every AI cover letter into the same letter.
# Matched case-insensitively at word boundaries.
_BANNED_BY_VOICE: dict[VoicePreset, tuple[str, ...]] = {
    "confident_selective": (
        "passionate about",
        "would love the opportunity",
        "would love to",
        "strong fit",
        "perfect fit",
        "excited to apply",
        "thrilled to apply",
        "hit the ground running",
        "team player",
        "results-oriented",
        "results-driven",
        "go-getter",
        "synergy",
        "synergies",
        "leverage my",
        "leveraging my",
        "i believe i would",
        "i feel i would",
        "my background aligns",
        "perfectly aligned with",
        "dynamic professional",
        "proven track record of success",
    ),
    "warm_eager": (
        "passionate about",
        "perfect fit",
        "hit the ground running",
        "synergy",
        "synergies",
        "go-getter",
        "results-oriented",
        "leverage my",
        "leveraging my",
    ),
    "formal_traditional": (
        "passionate about",
        "would love",
        "hit the ground running",
        "team player",
        "go-getter",
        "synergy",
        "synergies",
        "results-driven",
    ),
}


@dataclass(frozen=True)
class BannedPhraseHit:
    """A single banned-phrase occurrence."""
    phrase: str
    count: int
    severity: str = "high"  # 'high' for ≥1 hit; 'critical' if count ≥3

    def as_issue(self) -> dict:
        """Render as a critic feedback issue dict."""
        return {
            "dimension": "tone_match",
            "severity": "critical" if self.count >= 3 else self.severity,
            "issue": (
                f'Banned formulaic phrase "{self.phrase}" appears '
                f"{self.count}× — replace with concrete, specific language."
            ),
            "section": "voice",
            "expected_gain": min(15, 3 * self.count),
        }


def _strip_html(text: str) -> str:
    """Best-effort HTML→text. Avoids new dependencies."""
    if "<" not in text:
        return text

    class _Stripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    s = _Stripper()
    try:
        s.feed(text)
    except Exception:  # pragma: no cover — html.parser is permissive
        return text
    return " ".join(s.parts)


def _coerce_text(content) -> str:
    """Pull all string-shaped values out of a draft for scanning."""
    if content is None:
        return ""
    if isinstance(content, str):
        return _strip_html(content)
    if isinstance(content, dict):
        return " ".join(_coerce_text(v) for v in content.values())
    if isinstance(content, (list, tuple)):
        return " ".join(_coerce_text(v) for v in content)
    return ""


def banned_phrases_for(voice: VoicePreset | str | None) -> tuple[str, ...]:
    """Return the banned-phrase list for a voice preset.

    Unknown / falsy voices fall back to the default (``confident_selective``).
    """
    if not voice:
        voice = DEFAULT_VOICE
    return _BANNED_BY_VOICE.get(voice, _BANNED_BY_VOICE[DEFAULT_VOICE])  # type: ignore[index]


def scan_for_banned_phrases(
    draft_content,
    voice: VoicePreset | str | None = DEFAULT_VOICE,
    extra_banned: Iterable[str] | None = None,
) -> list[BannedPhraseHit]:
    """Scan a draft for banned formulaic phrases.

    Args:
        draft_content: HTML, plain text, dict, or list of any of the above.
        voice: User's selected voice preset. Determines the banned set.
        extra_banned: Optional user-supplied additions (e.g. from
            ``user_profile.prompt_overrides.banned_phrases``).

    Returns:
        A list of :class:`BannedPhraseHit`, one per distinct phrase found.
    """
    text = _coerce_text(draft_content)
    if not text:
        return []

    phrases: list[str] = list(banned_phrases_for(voice))
    if extra_banned:
        phrases.extend(p.strip() for p in extra_banned if p and p.strip())

    hits: list[BannedPhraseHit] = []
    seen: set[str] = set()
    for phrase in phrases:
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        # Word-boundary match; phrase may contain spaces — re.escape keeps it safe.
        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        n = len(pattern.findall(text))
        if n > 0:
            hits.append(BannedPhraseHit(phrase=phrase, count=n))
    return hits


def tone_penalty(hits: list[BannedPhraseHit]) -> int:
    """Compute the tone_match score deduction for a set of hits.

    5 points per distinct phrase, +2 per repeat occurrence, capped at 40.
    """
    if not hits:
        return 0
    penalty = 0
    for h in hits:
        penalty += 5 + 2 * max(0, h.count - 1)
    return min(penalty, 40)
