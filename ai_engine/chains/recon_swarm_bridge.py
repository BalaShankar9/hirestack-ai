"""S18 — Recon Swarm v2 → CompanyIntelChain bridge.

Maps a `ReconSwarmReport` into the existing intel-report shape consumed
by `adaptive_document.py` and `generate/helpers.py`. The merge is
ADDITIVE only: existing keys win when present, swarm fills gaps and
appends to list fields without dedup-overrun.

Activation (caller-side): env `INTEL_USE_RECON_SWARM=1`. Default OFF.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    return (os.getenv("INTEL_USE_RECON_SWARM") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _append_unique(target: List[Any], values: List[Any], cap: int = 20) -> None:
    """Append items not already present (case-insensitive for strings)."""
    seen_lower = {
        v.strip().lower() for v in target if isinstance(v, str) and v.strip()
    }
    for v in values or []:
        if not v:
            continue
        if isinstance(v, str):
            key = v.strip().lower()
            if not key or key in seen_lower:
                continue
            seen_lower.add(key)
        target.append(v)
        if len(target) >= cap:
            return


def _intel_value(field: Any) -> Any:
    """Extract `.value` from an `IntelField` dict or pass through scalar."""
    if isinstance(field, dict) and "value" in field and "confidence" in field:
        return field.get("value")
    return field


def merge_swarm_into_intel(
    intel: Dict[str, Any],
    swarm_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a Recon Swarm v2 report (model_dump) into an existing intel dict.

    Existing scalar values win; swarm only fills empty/missing fields.
    List fields append unique items up to a cap. Application kit feeds
    `application_strategy.{cover_letter_hooks,interview_prep_topics,
    things_to_avoid,keywords_to_use}`.
    """
    if not isinstance(intel, dict) or not isinstance(swarm_report, dict):
        return intel
    swarm_intel = swarm_report.get("intel") or {}
    kit = swarm_report.get("application_kit") or {}

    intel.setdefault("company_overview", {})
    intel.setdefault("tech_and_engineering", {})
    intel.setdefault("market_position", {})
    intel.setdefault("recent_developments", {})
    intel.setdefault("hiring_intelligence", {})
    intel.setdefault("application_strategy", {})

    # ─── company_overview ───────────────────────────────────────────
    co = intel["company_overview"]
    for src_key, dst_key in [
        ("legal_name", "legal_name"),
        ("website", "website"),
        ("description", "description"),
        ("industry", "industry"),
        ("headquarters", "headquarters"),
        ("founded_year", "founded_year"),
        ("company_stage", "stage"),
        ("headcount", "headcount"),
        ("ticker", "ticker"),
    ]:
        v = _intel_value(swarm_intel.get(src_key))
        if v and not co.get(dst_key):
            co[dst_key] = v

    # ─── tech_and_engineering ───────────────────────────────────────
    te = intel["tech_and_engineering"]
    stack = _intel_value(swarm_intel.get("tech_stack")) or []
    if isinstance(stack, list) and stack:
        existing = te.setdefault("tech_stack", [])
        if isinstance(existing, list):
            _append_unique(existing, stack, cap=30)
    repo_count = _intel_value(swarm_intel.get("repo_count"))
    if repo_count and not te.get("repo_count"):
        te["repo_count"] = repo_count
    languages = _intel_value(swarm_intel.get("languages")) or []
    if isinstance(languages, list) and languages:
        existing_lang = te.setdefault("languages", [])
        if isinstance(existing_lang, list):
            _append_unique(existing_lang, languages, cap=15)

    # ─── market_position ────────────────────────────────────────────
    mp = intel["market_position"]
    competitors = _intel_value(swarm_intel.get("competitors")) or []
    if isinstance(competitors, list) and competitors:
        existing_comp = mp.setdefault("competitors", [])
        if isinstance(existing_comp, list):
            _append_unique(existing_comp, competitors, cap=15)
    valuation = _intel_value(swarm_intel.get("valuation_usd"))
    if valuation and not mp.get("valuation_usd"):
        mp["valuation_usd"] = valuation
    funding = _intel_value(swarm_intel.get("total_funding_usd"))
    if funding and not mp.get("total_funding_usd"):
        mp["total_funding_usd"] = funding
    last_round = _intel_value(swarm_intel.get("last_round"))
    if last_round and not mp.get("last_round"):
        mp["last_round"] = last_round

    # ─── recent_developments ────────────────────────────────────────
    rd = intel["recent_developments"]
    news = _intel_value(swarm_intel.get("recent_news")) or []
    if isinstance(news, list) and news:
        existing_news = rd.setdefault("news_items", [])
        if isinstance(existing_news, list):
            # News are dicts; dedup by title lowercased.
            seen_titles = {
                (n.get("title") or "").strip().lower()
                for n in existing_news if isinstance(n, dict)
            }
            for item in news:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "").strip().lower()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                existing_news.append(item)
                if len(existing_news) >= 20:
                    break

    # ─── hiring_intelligence ────────────────────────────────────────
    hi = intel["hiring_intelligence"]
    open_roles = _intel_value(swarm_intel.get("open_roles_count"))
    if open_roles and not hi.get("estimated_open_roles"):
        hi["estimated_open_roles"] = open_roles

    # ─── application_strategy ← ApplicationKit ──────────────────────
    s = intel["application_strategy"]
    s.setdefault("cover_letter_hooks", [])
    s.setdefault("interview_prep_topics", [])
    s.setdefault("things_to_avoid", [])
    s.setdefault("keywords_to_use", [])
    s.setdefault("things_to_mention", [])

    if isinstance(s["cover_letter_hooks"], list):
        _append_unique(s["cover_letter_hooks"],
                       kit.get("cover_letter_hooks") or [], cap=10)
    if isinstance(s["interview_prep_topics"], list):
        _append_unique(s["interview_prep_topics"],
                       kit.get("interview_questions") or [], cap=15)
    if isinstance(s["things_to_avoid"], list):
        _append_unique(s["things_to_avoid"],
                       kit.get("red_flags") or [], cap=10)
    if isinstance(s["keywords_to_use"], list):
        _append_unique(s["keywords_to_use"],
                       kit.get("tech_stack_matches") or [], cap=20)
    if isinstance(s["things_to_mention"], list):
        _append_unique(s["things_to_mention"],
                       kit.get("talking_points") or [], cap=10)

    # ─── data_sources / completeness flag ───────────────────────────
    ds = intel.setdefault("data_sources", [])
    if isinstance(ds, list) and "recon_swarm_v2" not in ds:
        ds.append("recon_swarm_v2")
    intel.setdefault("data_completeness", {})
    if isinstance(intel["data_completeness"], dict):
        intel["data_completeness"]["recon_swarm"] = True
        intel["data_completeness"]["recon_swarm_field_count"] = (
            swarm_intel.get("field_count") or 0
        )
        intel["data_completeness"]["recon_swarm_completeness"] = (
            swarm_intel.get("profile_completeness") or 0
        )

    return intel


async def augment_with_recon_swarm(
    intel: Dict[str, Any],
    *,
    company: str,
    job_title: str,
    company_url: str = "",
    ai_client: Any = None,
) -> Dict[str, Any]:
    """Run Recon Swarm v2 and merge its report into the existing intel.

    Always env-gated (`INTEL_USE_RECON_SWARM=1`). Any failure logs and
    returns the original intel unchanged — never raises.
    """
    if not _is_enabled():
        return intel
    try:
        from ai_engine.agents.sub_agents.recon_swarm import (
            ReconSwarmCoordinator, ReconSwarmRequest,
        )
        coord = ReconSwarmCoordinator(ai_client=ai_client)
        req = ReconSwarmRequest(
            company=company,
            role_target=job_title or "",
            website=company_url or "",
            budget_seconds=int(os.getenv("INTEL_RECON_BUDGET_S") or 60),
            use_cache=True,
        )
        report = await coord.run(req)
        return merge_swarm_into_intel(intel, report.model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.info("recon_swarm augment failed company=%s exc=%s",
                    company, exc)
        return intel
