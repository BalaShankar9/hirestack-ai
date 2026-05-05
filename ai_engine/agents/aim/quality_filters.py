"""
AIM \u2014 Anti-Low-Quality Filters (deterministic).

Runs *before* the Reviewer LLM. Cheap, fast, and rule-based:

* Blocked-phrase scanner \u2014 phrases that signal generic AI prose / weak student
  writing. Case-insensitive substring match.
* Sentence-pattern repetition detector \u2014 catches templatey "X is Y. X is Z."
  rhythms via shingle Jaccard.
* Surface-summary detector \u2014 returns True when the text contains zero
  critique markers (\"however\", \"in contrast\", \"the limitation is\", ...).

These are intentionally strict so that filler-heavy drafts are caught
without spending a Reviewer LLM call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


BANNED_PHRASES: tuple[str, ...] = (
    "in today's world",
    "in today\u2019s world",
    "in conclusion,",
    "it is important to note",
    "since the dawn of",
    "plays a crucial role",
    "plays a pivotal role",
    "a wide range of",
    "navigate the complex landscape",
    "in the modern era",
    "rapidly evolving",
    "ever-changing",
    "ever-evolving",
    "delve into",
    "delve deeper into",
    "shed light on",
    "stand the test of time",
    "at its core",
    "the world we live in",
    "as we move forward",
    "in this essay, i will",
    "in this assignment, i will",
    "from time immemorial",
)

CRITIQUE_MARKERS: tuple[str, ...] = (
    "however", "whereas", "in contrast", "by contrast", "nevertheless",
    "nonetheless", "on the other hand", "the limitation is", "this overlooks",
    "this neglects", "fails to account", "challenges this view",
    "calls into question", "is contested by", "critics argue", "is undermined by",
    "is problematic because", "yet", "although", "while this",
)


@dataclass(frozen=True)
class FilterHit:
    kind: str           # "banned_phrase" | "repetition" | "no_critique"
    detail: str
    severity: str       # critical | high | medium

    def as_issue(self) -> dict:
        return {
            "severity": self.severity,
            "dimension": "academic_tone" if self.kind == "banned_phrase"
                         else ("structure" if self.kind == "repetition"
                               else "analytical_depth"),
            "issue": self.detail,
            "where": "deterministic-scan",
            "suggested_fix": self._fix_for(),
            "expected_gain": 8 if self.severity == "critical" else 4,
        }

    def _fix_for(self) -> str:
        if self.kind == "banned_phrase":
            return f"Remove the banned phrase \"{self.detail}\" and replace with a specific, content-bearing clause."
        if self.kind == "repetition":
            return "Vary sentence openers and structure; the current passage repeats the same shingle pattern."
        return "Add at least one critique marker (however, in contrast, the limitation is, ...) and engage a counterpoint."


def scan_banned_phrases(text: str) -> list[FilterHit]:
    if not text:
        return []
    lowered = text.lower()
    hits: list[FilterHit] = []
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            hits.append(FilterHit(
                kind="banned_phrase",
                detail=phrase,
                severity="critical",
            ))
    return hits


_WS = re.compile(r"\s+")


def _shingles(text: str, n: int = 4) -> set[tuple[str, ...]]:
    tokens = _WS.split(text.lower().strip())
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def detect_repetition(text: str, threshold: float = 0.18) -> list[FilterHit]:
    """Cross-sentence shingle Jaccard; flags when any pair > threshold."""
    if not text:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) < 4:
        return []
    shingles = [_shingles(s) for s in sentences]
    flagged: list[tuple[int, int, float]] = []
    for i in range(len(sentences)):
        if not shingles[i]:
            continue
        for j in range(i + 1, len(sentences)):
            if not shingles[j]:
                continue
            inter = len(shingles[i] & shingles[j])
            union = len(shingles[i] | shingles[j])
            if union == 0:
                continue
            jacc = inter / union
            if jacc >= threshold:
                flagged.append((i, j, jacc))
    if not flagged:
        return []
    flagged.sort(key=lambda t: t[2], reverse=True)
    top = flagged[:3]
    return [
        FilterHit(
            kind="repetition",
            detail=f"sentences {i + 1} and {j + 1} share Jaccard={j_:.2f} (templatey rhythm)",
            severity="high",
        )
        for (i, j, j_) in top
    ]


def detect_no_critique(text: str) -> list[FilterHit]:
    """Flag when text has no critique markers \u2014 i.e., descriptive only."""
    if not text:
        return []
    lowered = text.lower()
    if any(marker in lowered for marker in CRITIQUE_MARKERS):
        return []
    return [FilterHit(
        kind="no_critique",
        detail="no critique markers detected; section reads as descriptive rather than analytical",
        severity="critical",
    )]


def run_all_filters(text: str) -> list[FilterHit]:
    return (
        scan_banned_phrases(text)
        + detect_repetition(text)
        + detect_no_critique(text)
    )


def deterministic_penalty(hits: list[FilterHit]) -> int:
    """Total points to subtract from sub-scores given the deterministic hits."""
    return sum(h.as_issue()["expected_gain"] for h in hits)


__all__ = [
    "BANNED_PHRASES",
    "CRITIQUE_MARKERS",
    "FilterHit",
    "scan_banned_phrases",
    "detect_repetition",
    "detect_no_critique",
    "run_all_filters",
    "deterministic_penalty",
]
