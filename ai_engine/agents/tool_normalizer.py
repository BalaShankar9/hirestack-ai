"""
Tool output normalization adapter.

Normalizes raw tool outputs into a canonical shape before evidence
ingestion, so that evidence population is not dependent on drifting
tool key names.

Maps old/alternative key names to canonical ones:
  matches → matched_keywords
  gaps → missing_from_document
  flesch_score / score → flesch_reading_ease
"""
from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════
#  Key normalization maps per tool
# ═══════════════════════════════════════════════════════════════════════

_KEYWORD_OVERLAP_ALIASES = {
    "matches": "matched_keywords",
    "gaps": "missing_from_document",
}

_READABILITY_ALIASES = {
    "flesch_score": "flesch_reading_ease",
    "score": "flesch_reading_ease",
}


def normalize_tool_output(tool_name: str, raw: dict) -> dict:
    """Return a normalized copy of the tool output dict.

    Applies key-name alias resolution so downstream consumers
    (evidence module, agents) always see canonical keys.
    Does NOT mutate the input dict.
    """
    if not isinstance(raw, dict):
        return raw

    if tool_name == "compute_keyword_overlap":
        return _normalize_with_aliases(raw, _KEYWORD_OVERLAP_ALIASES)
    elif tool_name == "compute_readability":
        return _normalize_with_aliases(raw, _READABILITY_ALIASES)
    else:
        return dict(raw)


def _normalize_with_aliases(data: dict, aliases: dict[str, str]) -> dict:
    """Copy data, promoting aliased keys to canonical names.

    If the canonical key already exists, it takes precedence.
    """
    result = dict(data)
    for old_key, canonical_key in aliases.items():
        if old_key in result and canonical_key not in result:
            result[canonical_key] = result.pop(old_key)
        elif old_key in result and canonical_key in result:
            # Canonical key already present — drop the alias
            del result[old_key]
    return result


def normalize_all_tool_results(tool_results: dict[str, Any]) -> dict[str, Any]:
    """Normalize all tool results in a researcher's tool_results dict."""
    return {
        name: normalize_tool_output(name, output) if isinstance(output, dict) else output
        for name, output in tool_results.items()
    }
