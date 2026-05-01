"""S17-P2 — Pure-python culture signal extractor.

Scans company-supplied text (about page, careers page, leadership
posts, glassdoor blurbs the user pastes) for keyword cues mapped to
value dimensions. Emits weighted CultureSignal entries.

Deterministic, deployable without an LLM. The extractor is
intentionally conservative — it only fires on explicit phrases so
a downstream coach can be honest about evidence.
"""
from __future__ import annotations

import re
from typing import List

from .schemas import CultureSignal, ValueDimension

_KEYWORD_MAP: dict[ValueDimension, tuple[str, ...]] = {
    "ownership": (
        r"\bown(ers?h?ip|ers?)\b",
        r"\bend[- ]to[- ]end\b",
        r"\bdriver(s)? of\b",
        r"\bbias for action\b",
    ),
    "collaboration": (
        r"\bcollaborat\w+\b",
        r"\bcross[- ]functional\b",
        r"\bone team\b",
        r"\bteam[- ]first\b",
    ),
    "customer_obsession": (
        r"\bcustomer obsess\w+\b",
        r"\bcustomer[- ]first\b",
        r"\buser[- ]centric\b",
        r"\bobsess\w*\s+(over|about)\s+(customers?|users?)\b",
    ),
    "innovation": (
        r"\binnovat\w+\b",
        r"\binvent\w+\b",
        r"\bfirst principles\b",
        r"\b0[- ]to[- ]1\b",
    ),
    "execution_speed": (
        r"\bship fast\b",
        r"\bmove fast\b",
        r"\bvelocity\b",
        r"\bbias to ship\b",
        r"\bweekly releases?\b",
    ),
    "craft_quality": (
        r"\bcraft\b",
        r"\bquality bar\b",
        r"\bhigh standards?\b",
        r"\bpixel[- ]perfect\b",
    ),
    "transparency": (
        r"\btransparen\w+\b",
        r"\bopen by default\b",
        r"\bradical candor\b",
    ),
    "diversity_inclusion": (
        r"\b(diversity|inclusion|belonging)\b",
        r"\bequit(y|able)\b",
        r"\bunderrepresented\b",
    ),
    "long_term_thinking": (
        r"\blong[- ]term\b",
        r"\bdecades?\b",
        r"\bgenerational\b",
    ),
    "frugality": (
        r"\bfrugal\w*\b",
        r"\bdo more with less\b",
        r"\blean\b",
    ),
    "learning_growth": (
        r"\blearn(ing|ers?)\b",
        r"\bgrowth mindset\b",
        r"\bcurious\b",
    ),
    "wellbeing": (
        r"\bwell[- ]being\b",
        r"\bsustainable pace\b",
        r"\bwork[- ]life balance\b",
    ),
}


def _snippet(text: str, span: tuple[int, int], pad: int = 60) -> str:
    a = max(0, span[0] - pad)
    b = min(len(text), span[1] + pad)
    s = text[a:b].strip()
    return re.sub(r"\s+", " ", s)


def extract_culture_signals(
    text: str, source: str = "company_text"
) -> List[CultureSignal]:
    """Return weighted signals matched in `text`."""
    if not text:
        return []
    signals: List[CultureSignal] = []
    for dim, patterns in _KEYWORD_MAP.items():
        hits = 0
        first_evidence = ""
        for pat in patterns:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                hits += 1
                if not first_evidence:
                    first_evidence = _snippet(text, m.span())
        if hits:
            weight = min(3.0, 1.0 + 0.5 * (hits - 1))
            signals.append(
                CultureSignal(
                    dimension=dim,
                    evidence=first_evidence,
                    weight=round(weight, 2),
                    source=source,
                )
            )
    return signals
