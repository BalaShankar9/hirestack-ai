"""S18 — Intel fusion: merge N raw provider payloads → CompanyIntelV2.

Strategy:
  1. Per-field merge with cross-source confidence scoring:
     - >=2 sources agree → high
     - 1 source           → medium
     - LLM-derived only   → low
  2. LLM polish (optional) for free-text fields (description, work_style)
     with deterministic fallback on raise / missing payload.
  3. Compute completeness + high_confidence_count meta.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .schemas import CompanyIntelV2, IntelField, ProviderResult

logger = logging.getLogger(__name__)


# ─── per-field merge rules ────────────────────────────────────────

_SCALAR_FIELDS = {
    "legal_name", "website", "description", "industry", "headquarters",
    "founded_year", "company_stage", "total_funding_usd", "last_round",
    "last_round_date", "valuation_usd", "is_public", "ticker",
    "headcount", "eng_headcount", "open_roles_count", "repo_count",
    "patents_count", "glassdoor_rating", "twitter_handle",
    "twitter_sentiment", "work_style", "sec_revenue_usd",
}
_LIST_FIELDS = {
    "sub_industries", "investors", "leadership", "hiring_managers",
    "tech_stack", "products", "github_orgs", "languages",
    "competitors", "recent_news", "product_launches",
    "glassdoor_themes", "values", "benefits", "sec_risk_factors",
}


def _confidence(n_sources: int) -> str:
    if n_sources >= 2:
        return "high"
    if n_sources == 1:
        return "medium"
    return "unknown"


def _merge_scalar(values: List[tuple[Any, str]]) -> IntelField:
    if not values:
        return IntelField(value=None)
    counts: Dict[Any, List[str]] = defaultdict(list)
    for val, src in values:
        if val is None or val == "":
            continue
        key = val if not isinstance(val, list) else tuple(val)
        counts[key].append(src)
    if not counts:
        return IntelField(value=None)
    winner = max(counts.items(), key=lambda kv: len(kv[1]))
    return IntelField(
        value=winner[0] if not isinstance(winner[0], tuple) else list(winner[0]),
        confidence=_confidence(len(winner[1])),
        sources=sorted(set(winner[1])),
    )


def _merge_list(values: List[tuple[Any, str]]) -> IntelField:
    seen: Dict[str, List[str]] = defaultdict(list)
    items_meta: Dict[str, Any] = {}
    for raw, src in values:
        if not raw:
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            key = _list_item_key(item)
            if key in items_meta:
                seen[key].append(src)
                continue
            items_meta[key] = item
            seen[key].append(src)
    if not items_meta:
        return IntelField(value=[])
    merged = list(items_meta.values())
    distinct_sources = sorted({s for srcs in seen.values() for s in srcs})
    confidence = _confidence(len(distinct_sources))
    return IntelField(value=merged, confidence=confidence,
                      sources=distinct_sources)


def _list_item_key(item: Any) -> str:
    if isinstance(item, str):
        return item.lower().strip()
    if isinstance(item, dict):
        for prio in ("name", "title", "handle"):
            if prio in item and item[prio]:
                return f"{prio}:{str(item[prio]).lower().strip()}"
        try:
            import json
            return json.dumps(item, sort_keys=True, default=str).lower()
        except Exception:  # noqa: BLE001
            return str(item).lower()
    return str(item).lower()


# ─── core fusion ──────────────────────────────────────────────────

class IntelFusion:
    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self.ai_client = ai_client

    def _collect(self, results: List[ProviderResult]) -> Dict[str, List[tuple[Any, str]]]:
        bag: Dict[str, List[tuple[Any, str]]] = defaultdict(list)
        for r in results:
            if not r.success:
                continue
            for k, v in r.raw.items():
                bag[k].append((v, r.provider))
        return bag

    async def fuse(
        self,
        company: str,
        results: List[ProviderResult],
    ) -> CompanyIntelV2:
        bag = self._collect(results)
        intel = CompanyIntelV2(company=company)

        for field_name in _SCALAR_FIELDS:
            if field_name in bag:
                setattr(intel, field_name, _merge_scalar(bag[field_name]))
        for field_name in _LIST_FIELDS:
            if field_name in bag:
                setattr(intel, field_name, _merge_list(bag[field_name]))

        # Optional LLM polish for description (free-text) when not present
        if intel.description.value in (None, "") and self.ai_client:
            polished = await self._polish_description(company, bag)
            if polished:
                intel.description = IntelField(
                    value=polished, confidence="low", sources=["llm_synth"],
                )

        # Meta
        all_fields = list(_SCALAR_FIELDS) + list(_LIST_FIELDS)
        present = 0
        high = 0
        for fname in all_fields:
            f = getattr(intel, fname, None)
            if not isinstance(f, IntelField):
                continue
            v = f.value
            if v is None:
                continue
            if isinstance(v, (list, dict)) and not v:
                continue
            present += 1
            if f.confidence == "high":
                high += 1
        intel.field_count = present
        intel.high_confidence_count = high
        intel.profile_completeness = round(present / len(all_fields), 3)
        return intel

    async def _polish_description(
        self,
        company: str,
        bag: Dict[str, List[tuple[Any, str]]],
    ) -> Optional[str]:
        about = bag.get("raw_about_text") or []
        seed_text = about[0][0] if about else ""
        if not seed_text:
            return f"{company} is a technology company."
        prompt = (
            f"Rewrite the following snippet as a single 1-sentence "
            f"factual company description for {company}. Return JSON: "
            "{\"description\": ...}.\n\n"
            f"SNIPPET: {seed_text[:1500]}"
        )
        try:
            payload = await self.ai_client.complete_json(
                prompt=prompt,
                system="You write tasteful, factual company descriptions.",
                schema={
                    "type": "object",
                    "properties": {"description": {"type": "string"}},
                    "required": ["description"],
                },
                temperature=0.3,
                task_type="recon_description",
            )
            d = ((payload or {}).get("description") or "").strip()
            if d and len(d) <= 400:
                return d
        except Exception as exc:  # noqa: BLE001
            logger.info("intel description LLM fallback: %s", exc)
        # Deterministic fallback: first sentence of seed_text
        first = seed_text.split(".")[0].strip()
        return first[:300] if first else f"{company} is a technology company."
