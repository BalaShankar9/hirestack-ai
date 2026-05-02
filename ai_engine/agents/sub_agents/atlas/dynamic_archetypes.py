"""ATLAS dynamic archetype generator.

Given a job description + optional company / role context, asks the
LLM to generate **exactly three** target candidate archetypes that
collectively span the realistic talent pool for the role. Returns
``List[Archetype]`` (see ``artifact_contracts.py``).

Each archetype carries:
* ``name`` (human-readable, e.g. "Stripe Senior Eng")
* ``must_have_skills`` / ``nice_to_have_skills``
* ``years_min`` / ``years_max``
* ``salary_band`` (placeholder ``{}`` until Slice 2.3 wires in
  ``levels.fyi``)
* ``cultural_signals``
* ``rationale``

Caching: 7-day in-process LRU keyed by
``(role_target, company_industry)`` hash. No on-disk persistence.

Pure async; one LLM call per cache miss; never raises (failures
return an empty list and log at WARNING).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from ai_engine.agents.artifact_contracts import Archetype

logger = logging.getLogger(__name__)


_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60      # 7 days
_TARGET_ARCHETYPE_COUNT = 3
_LLM_TEMPERATURE = 0.4
_LLM_MAX_TOKENS = 2048

_LLM_SYSTEM = (
    "You are a senior technical recruiter. Given a job posting and "
    "company context, return EXACTLY three distinct candidate "
    "archetypes that cover the realistic hiring funnel for this "
    "role. Each archetype represents a different background pattern "
    "(e.g. big-tech alum vs scrappy startup builder vs domain "
    "expert). Be specific. Avoid vague labels."
)

_LLM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "archetypes": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "must_have_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "nice_to_have_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "years_min": {"type": "integer"},
                    "years_max": {"type": "integer"},
                    "cultural_signals": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["name", "must_have_skills", "rationale"],
            },
        }
    },
    "required": ["archetypes"],
}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE: Dict[str, Any] = {}   # key -> {"expires_at": float, "value": List[dict]}


def _cache_key(role_target: str, company_industry: str, job_signature: str) -> str:
    raw = f"{role_target}|{company_industry}|{job_signature}".lower()
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _cache_get(key: str) -> Optional[List[dict]]:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if entry["expires_at"] < time.time():
        _CACHE.pop(key, None)
        return None
    return entry["value"]


def _cache_set(key: str, value: List[dict]) -> None:
    _CACHE[key] = {
        "expires_at": time.time() + _CACHE_TTL_SECONDS,
        "value": value,
    }


def reset_cache() -> None:
    """Test hook to clear the in-process cache."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def _build_prompt(
    *,
    job_description: str,
    role_target: str,
    company_industry: str,
    company_name: str,
) -> str:
    parts = [
        f"ROLE TARGET: {role_target or 'unspecified'}",
        f"COMPANY: {company_name or 'unspecified'}",
        f"INDUSTRY: {company_industry or 'unspecified'}",
        "",
        "JOB DESCRIPTION:",
        (job_description or "")[:6000],
        "",
        (
            "Return JSON of shape "
            '{"archetypes":[{"name":"...","must_have_skills":[...],'
            '"nice_to_have_skills":[...],"years_min":N,"years_max":N,'
            '"cultural_signals":[...],"rationale":"..."}]} with EXACTLY '
            "three entries. Make the three archetypes meaningfully "
            "different (varied seniority, varied background pattern, "
            "or varied specialization)."
        ),
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _coerce_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _coerce_str_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _parse_archetypes(payload: Any) -> List[Archetype]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("archetypes")
    if not isinstance(raw, list):
        return []

    out: List[Archetype] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        must = _coerce_str_list(item.get("must_have_skills"))
        nice = _coerce_str_list(item.get("nice_to_have_skills"))
        years_min = _coerce_int(item.get("years_min"))
        years_max = _coerce_int(item.get("years_max"))
        if years_max < years_min:
            years_max = years_min
        cultural = _coerce_str_list(item.get("cultural_signals"))
        rationale = str(item.get("rationale") or "").strip()
        out.append(
            Archetype(
                name=name,
                must_have_skills=must,
                nice_to_have_skills=nice,
                years_min=years_min,
                years_max=years_max,
                salary_band={},
                cultural_signals=cultural,
                rationale=rationale,
            )
        )
        if len(out) >= _TARGET_ARCHETYPE_COUNT:
            break
    return out


def _archetype_to_dict(a: Archetype) -> Dict[str, Any]:
    return a.model_dump()


def _dict_to_archetype(d: Dict[str, Any]) -> Archetype:
    return Archetype(**d)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ArchetypeGenerator:
    """LLM-driven generator that returns exactly 3 :class:`Archetype`s."""

    def __init__(self, ai_client: Any) -> None:
        if ai_client is None:
            raise ValueError("ArchetypeGenerator requires an ai_client")
        self._client = ai_client

    async def generate(
        self,
        *,
        job_description: str,
        role_target: str = "",
        company_industry: str = "",
        company_name: str = "",
        use_cache: bool = True,
    ) -> List[Archetype]:
        """Return exactly three archetypes (or ``[]`` on hard failure)."""
        if not job_description or not job_description.strip():
            return []

        # Cache key uses a stable digest of the JD so identical postings
        # collapse onto one cache entry.
        jd_sig = hashlib.sha256(
            job_description[:6000].encode("utf-8", errors="ignore")
        ).hexdigest()[:16]
        key = _cache_key(role_target, company_industry, jd_sig)

        if use_cache:
            cached = _cache_get(key)
            if cached is not None:
                try:
                    return [_dict_to_archetype(d) for d in cached]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "ArchetypeGenerator cache deserialize failed: %s", exc
                    )

        prompt = _build_prompt(
            job_description=job_description,
            role_target=role_target,
            company_industry=company_industry,
            company_name=company_name,
        )

        try:
            payload = await self._client.complete_json(
                prompt=prompt,
                system=_LLM_SYSTEM,
                schema=_LLM_SCHEMA,
                temperature=_LLM_TEMPERATURE,
                max_tokens=_LLM_MAX_TOKENS,
            )
        except Exception as exc:
            logger.warning("ArchetypeGenerator LLM call failed: %s", exc)
            return []

        archetypes = _parse_archetypes(payload)
        if len(archetypes) != _TARGET_ARCHETYPE_COUNT:
            logger.warning(
                "ArchetypeGenerator expected %d archetypes, got %d",
                _TARGET_ARCHETYPE_COUNT,
                len(archetypes),
            )
            return archetypes  # caller may still consume a partial list

        if use_cache:
            try:
                _cache_set(key, [_archetype_to_dict(a) for a in archetypes])
            except Exception as exc:  # pragma: no cover
                logger.warning("ArchetypeGenerator cache write failed: %s", exc)

        return archetypes
