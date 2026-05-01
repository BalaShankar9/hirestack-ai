"""S17-P1 — Pure-python personalization scorer for outreach drafts.

Returns 0.0–1.0 reflecting how tailored the email feels:
- target name presence
- shared context tokens reused in body
- target role/company referenced
- contains a specific CTA / question (not generic "let's chat")
- length within 80–180 words for an initial outreach
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import OutreachContext

_GENERIC_PHRASES = (
    "let's connect",
    "let me know if you have time",
    "would love to chat",
    "pick your brain",
    "circle back",
)
_QUESTION_RE = re.compile(r"\?")
_WORD_RE = re.compile(r"\b\w+\b")


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def score_personalization(body: str, ctx: "OutreachContext") -> float:
    """Score how personalized `body` is for `ctx`. Range 0.0–1.0."""
    body_l = (body or "").lower()
    score = 0.0

    if ctx.target_name and ctx.target_name.split()[0].lower() in body_l:
        score += 0.20

    if ctx.shared_context:
        tokens = [
            t.lower()
            for t in _WORD_RE.findall(ctx.shared_context)
            if len(t) > 4
        ]
        if tokens:
            hits = sum(1 for t in tokens if t in body_l)
            score += 0.25 * min(1.0, hits / max(1, len(tokens)))

    if ctx.target_company and ctx.target_company.lower() in body_l:
        score += 0.15
    if ctx.target_role and any(
        w.lower() in body_l for w in ctx.target_role.split() if len(w) > 3
    ):
        score += 0.10

    if _QUESTION_RE.search(body or ""):
        score += 0.15

    wc = _word_count(body)
    if 80 <= wc <= 180:
        score += 0.15
    elif 60 <= wc < 80 or 180 < wc <= 220:
        score += 0.07

    if any(p in body_l for p in _GENERIC_PHRASES):
        score -= 0.10

    return max(0.0, min(1.0, round(score, 3)))
