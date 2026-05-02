"""ATLAS impact extractor — quantitative claim mining.

Pulls measurable impact statements out of a candidate's narrative text
(resume bullets, LinkedIn summary, project descriptions). Two passes:

1. **Regex pass** — cheap, deterministic, covers ~70% of common claims
   (e.g. ``"served 10M+ users"``, ``"team of 12"``, ``"reduced latency
   by 40%"``). Confidence 0.7.

2. **LLM fallback** — single ``AIClient.complete_json`` call with a
   strict JSON schema, fired *only* when the regex pass returns zero
   hits AND a client is injected. Confidence 0.5. Failures (network,
   parse, missing key) degrade silently to the regex result.

Returns ``List[ImpactSignal]`` — see ``artifact_contracts.py``.
Pure module; no global state; no side effects beyond the optional LLM
call. Safe to import without ``google.genai`` installed (LLM fallback
is opt-in via injected client).
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

from ai_engine.agents.artifact_contracts import ImpactSignal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Capture: quantity (with optional K/M/B suffix and + sign) + unit noun.
_QTY_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?[KMB]?\+?)\s*"
    r"(users|customers|clients|requests|downloads|signups|sign-ups|"
    r"orders|transactions|sessions|visitors|installs|subscribers|"
    r"developers|engineers)\b",
    re.IGNORECASE,
)

# Capture: optional $ + quantity + monetary unit (revenue / ARR / MRR / etc.)
_MONEY_RE = re.compile(
    r"\$?(\d+(?:[.,]\d+)?[KMB]?\+?)\s*(?:in\s+)?"
    r"(revenue|ARR|MRR|sales|funding|GMV|profit|savings|budget|cost\s+savings)\b",
    re.IGNORECASE,
)

# Capture: team-size phrases.
_TEAM_RE = re.compile(
    r"(?:team\s+of|managed|led|directed|supervised|mentored)\s+"
    r"(\d+)\s*"
    r"(engineers|developers|people|reports|members|interns|staff)?",
    re.IGNORECASE,
)

# Capture: directional verb + percent delta.
_PERCENT_DELTA_RE = re.compile(
    r"(grew|increased|reduced|decreased|improved|cut|boosted|dropped|"
    r"raised|lowered|saved|accelerated)\b[^.]{0,80}?"
    r"(\d+(?:\.\d+)?\s*%)",
    re.IGNORECASE,
)

# Map a matched verb to a metric label.
_VERB_TO_METRIC = {
    "grew": "growth_pct",
    "increased": "growth_pct",
    "boosted": "growth_pct",
    "raised": "growth_pct",
    "improved": "improvement_pct",
    "accelerated": "improvement_pct",
    "reduced": "reduction_pct",
    "decreased": "reduction_pct",
    "cut": "reduction_pct",
    "dropped": "reduction_pct",
    "lowered": "reduction_pct",
    "saved": "savings_pct",
}

# Sentence boundary helper — splits on . ! ? followed by space or EOS.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_REGEX_CONFIDENCE = 0.7
_LLM_CONFIDENCE = 0.5


def _evidence_for(text: str, span_start: int, span_end: int) -> str:
    """Return the sentence containing ``text[span_start:span_end]``."""
    # Find sentence boundary before / after the match.
    before = text.rfind(".", 0, span_start)
    if before < 0:
        before = -1
    after = text.find(".", span_end)
    if after < 0:
        after = len(text)
    sentence = text[before + 1 : after + 1].strip()
    # Cap to a sane length to keep payloads small.
    return sentence[:280]


def _normalize_metric(unit: str) -> str:
    """Lowercase + strip + collapse synonyms."""
    u = unit.strip().lower()
    u = u.replace("sign-ups", "signups").replace(" ", "_")
    return u


def _scan_regex(text: str, source: str) -> List[ImpactSignal]:
    """Run all four regex passes and return de-duplicated signals."""
    out: List[ImpactSignal] = []
    seen: set = set()

    def _add(metric: str, value: str, evidence: str) -> None:
        key = (metric, value, evidence[:60])
        if key in seen:
            return
        seen.add(key)
        out.append(
            ImpactSignal(
                metric=metric,
                value=value,
                confidence=_REGEX_CONFIDENCE,
                source=source,
                evidence=evidence,
            )
        )

    for m in _QTY_UNIT_RE.finditer(text):
        _add(_normalize_metric(m.group(2)), m.group(1), _evidence_for(text, *m.span()))

    for m in _MONEY_RE.finditer(text):
        # Skip pure numbers that already matched as user counts (overlap).
        raw = m.group(0)
        # Heuristic: require either a $ prefix or an explicit money unit.
        if "$" not in raw and m.group(2) is None:
            continue
        unit = m.group(2) or "revenue"
        _add(_normalize_metric(unit), m.group(1), _evidence_for(text, *m.span()))

    for m in _TEAM_RE.finditer(text):
        _add("team_size", m.group(1), _evidence_for(text, *m.span()))

    for m in _PERCENT_DELTA_RE.finditer(text):
        verb = m.group(1).lower()
        metric = _VERB_TO_METRIC.get(verb, "delta_pct")
        value = re.sub(r"\s+", "", m.group(2))  # "40 %" → "40%"
        _add(metric, value, _evidence_for(text, *m.span()))

    return out


# ---------------------------------------------------------------------------
# LLM fallback schema
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "You extract quantitative impact claims from a candidate's "
    "professional narrative. Return ONLY claims that include a "
    "specific number (count, percent, currency, or duration). "
    "Skip vague statements."
)

_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["metric", "value"],
            },
        }
    },
    "required": ["signals"],
}


def _build_llm_prompt(text: str) -> str:
    return (
        "Extract quantitative impact claims from the text below. "
        "Return JSON of shape "
        '{"signals":[{"metric":"...","value":"...","evidence":"..."}]}.\n\n'
        "Text:\n"
        f"{text[:6000]}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ImpactExtractor:
    """Hybrid regex + LLM extractor for ``ImpactSignal``s."""

    def __init__(self, ai_client: Any = None) -> None:
        # ai_client is optional; only consulted when regex returns 0 hits.
        self._client = ai_client

    async def extract(self, text: str, source: str = "resume") -> List[ImpactSignal]:
        """Return all impact signals found in ``text``.

        Always returns a list (possibly empty). Never raises.
        """
        if not text or not text.strip():
            return []

        try:
            regex_hits = _scan_regex(text, source=source)
        except Exception as exc:  # defensive: regex shouldn't raise but be safe
            logger.warning("ImpactExtractor regex pass failed: %s", exc)
            regex_hits = []

        if regex_hits:
            return regex_hits

        if self._client is None:
            return []

        return await self._llm_extract(text, source=source)

    async def _llm_extract(self, text: str, *, source: str) -> List[ImpactSignal]:
        try:
            payload = await self._client.complete_json(
                prompt=_build_llm_prompt(text),
                system=_LLM_SYSTEM,
                schema=_LLM_SCHEMA,
                temperature=0.0,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.warning("ImpactExtractor LLM fallback failed: %s", exc)
            return []

        signals_raw = []
        if isinstance(payload, dict):
            signals_raw = payload.get("signals") or []
        if not isinstance(signals_raw, list):
            return []

        out: List[ImpactSignal] = []
        for item in signals_raw:
            if not isinstance(item, dict):
                continue
            metric = str(item.get("metric") or "").strip()
            value = str(item.get("value") or "").strip()
            if not metric or not value:
                continue
            evidence = str(item.get("evidence") or "").strip()[:280]
            out.append(
                ImpactSignal(
                    metric=_normalize_metric(metric),
                    value=value,
                    confidence=_LLM_CONFIDENCE,
                    source=source,
                    evidence=evidence,
                )
            )
        return out
