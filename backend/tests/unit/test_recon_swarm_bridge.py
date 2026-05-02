"""Tests for ai_engine.chains.recon_swarm_bridge — S18 wiring."""
from __future__ import annotations

import pytest

from ai_engine.chains.recon_swarm_bridge import (
    _append_unique,
    _intel_value,
    augment_with_recon_swarm,
    merge_swarm_into_intel,
)


def _make_swarm_report() -> dict:
    """Minimal swarm report shape (mirrors ReconSwarmReport.model_dump)."""
    return {
        "company": "Stripe",
        "intel": {
            "company": "Stripe",
            "legal_name": {"value": "Stripe, Inc.",
                           "confidence": "high",
                           "sources": ["sec", "crunchbase_stub"]},
            "industry": {"value": "Payments", "confidence": "medium",
                         "sources": ["crunchbase_stub"]},
            "tech_stack": {"value": ["Ruby", "Go", "TypeScript"],
                           "confidence": "high",
                           "sources": ["builtwith_stub"]},
            "languages": {"value": ["Ruby", "Go"], "confidence": "medium",
                          "sources": ["github_stub"]},
            "competitors": {"value": ["Square", "Adyen"],
                            "confidence": "medium",
                            "sources": ["crunchbase_stub"]},
            "open_roles_count": {"value": 42, "confidence": "medium",
                                 "sources": ["careers_stub"]},
            "recent_news": {
                "value": [
                    {"title": "Stripe launches AI tool",
                     "date": "2026-04-14", "source": "TechCrunch"},
                    {"title": "Stripe expands in Dublin",
                     "date": "2026-04-10", "source": "TechCrunch"},
                ],
                "confidence": "high",
                "sources": ["google_news"],
            },
            "field_count": 7,
            "high_confidence_count": 3,
            "profile_completeness": 0.42,
        },
        "application_kit": {
            "cover_letter_hooks": [
                "Mention recent AI launch",
                "Anchor on Dublin engineering expansion",
            ],
            "interview_questions": [
                "How does Stripe approach payment latency?",
                "Tell me about your Go services architecture.",
            ],
            "tech_stack_matches": ["Ruby", "Go"],
            "talking_points": ["Payments scale", "Developer experience"],
            "red_flags": ["Watch for burnout signals"],
            "differentiation_angles": [],
            "resume_bullet_hooks": [],
        },
        "provider_results": [],
        "layers_completed": [1, 2, 3, 4, 5],
        "cache_hit": False,
        "total_latency_ms": 1234,
        "budget_seconds": 60,
    }


def test_append_unique_dedupes_case_insensitive():
    target = ["Python", "Go"]
    _append_unique(target, ["python", "rust", "GO", "Rust"])
    assert target == ["Python", "Go", "rust"]


def test_append_unique_respects_cap():
    target = []
    _append_unique(target, [str(i) for i in range(50)], cap=5)
    assert len(target) == 5


def test_intel_value_unwraps_field_dict():
    assert _intel_value({"value": "X", "confidence": "high",
                         "sources": []}) == "X"
    assert _intel_value("plain") == "plain"
    assert _intel_value(None) is None


def test_merge_swarm_fills_empty_intel():
    intel = {}
    report = _make_swarm_report()
    merged = merge_swarm_into_intel(intel, report)
    assert merged["company_overview"]["legal_name"] == "Stripe, Inc."
    assert merged["company_overview"]["industry"] == "Payments"
    assert "Ruby" in merged["tech_and_engineering"]["tech_stack"]
    assert "Go" in merged["tech_and_engineering"]["tech_stack"]
    assert "Square" in merged["market_position"]["competitors"]
    assert merged["hiring_intelligence"]["estimated_open_roles"] == 42
    titles = {n["title"] for n in
              merged["recent_developments"]["news_items"]}
    assert "Stripe launches AI tool" in titles
    s = merged["application_strategy"]
    assert "Mention recent AI launch" in s["cover_letter_hooks"]
    assert any("payment latency" in q.lower()
               for q in s["interview_prep_topics"])
    assert "Watch for burnout signals" in s["things_to_avoid"]
    assert "Ruby" in s["keywords_to_use"]
    assert "Payments scale" in s["things_to_mention"]
    assert "recon_swarm_v2" in merged["data_sources"]
    assert merged["data_completeness"]["recon_swarm"] is True
    assert merged["data_completeness"]["recon_swarm_field_count"] == 7


def test_merge_swarm_existing_scalars_win():
    intel = {
        "company_overview": {
            "legal_name": "Existing Stripe Legal",
            "industry": "Existing Industry",
        },
    }
    merged = merge_swarm_into_intel(intel, _make_swarm_report())
    assert merged["company_overview"]["legal_name"] == "Existing Stripe Legal"
    assert merged["company_overview"]["industry"] == "Existing Industry"


def test_merge_swarm_lists_dedupe_with_existing():
    intel = {
        "tech_and_engineering": {"tech_stack": ["ruby", "Python"]},
        "application_strategy": {"keywords_to_use": ["ruby"]},
    }
    merged = merge_swarm_into_intel(intel, _make_swarm_report())
    stack = [s.lower() for s in merged["tech_and_engineering"]["tech_stack"]]
    # Ruby should not appear twice
    assert stack.count("ruby") == 1
    assert "go" in stack
    assert "python" in stack
    kw = [k.lower() for k in merged["application_strategy"]["keywords_to_use"]]
    assert kw.count("ruby") == 1


def test_merge_swarm_news_dedupes_by_title():
    intel = {
        "recent_developments": {
            "news_items": [
                {"title": "Stripe launches AI tool",
                 "date": "2026-04-14", "source": "Other"},
            ],
        },
    }
    merged = merge_swarm_into_intel(intel, _make_swarm_report())
    titles = [n["title"] for n in
              merged["recent_developments"]["news_items"]]
    assert titles.count("Stripe launches AI tool") == 1
    assert "Stripe expands in Dublin" in titles


def test_merge_swarm_handles_empty_report():
    intel = {"existing": "stays"}
    merged = merge_swarm_into_intel(intel, {})
    assert merged["existing"] == "stays"
    # data_sources marker still set since we passed a dict
    assert "recon_swarm_v2" in merged["data_sources"]


def test_merge_swarm_rejects_non_dicts():
    intel = {"existing": "stays"}
    assert merge_swarm_into_intel(intel, None) is intel
    assert merge_swarm_into_intel(None, _make_swarm_report()) is None


@pytest.mark.asyncio
async def test_augment_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INTEL_USE_RECON_SWARM", raising=False)
    intel = {"company_overview": {}}
    out = await augment_with_recon_swarm(
        intel, company="Stripe", job_title="Eng", ai_client=None,
    )
    # Disabled → identity, no swarm marker added.
    assert out is intel
    assert "data_sources" not in out


@pytest.mark.asyncio
async def test_augment_enabled_runs_swarm_with_stubs(monkeypatch):
    monkeypatch.setenv("INTEL_USE_RECON_SWARM", "1")
    intel = {}
    out = await augment_with_recon_swarm(
        intel, company="Stripe", job_title="Eng",
        company_url="https://stripe.com", ai_client=None,
    )
    # Stub providers always succeed → swarm marker should be set.
    assert "recon_swarm_v2" in out.get("data_sources", [])
    assert out["data_completeness"]["recon_swarm"] is True


@pytest.mark.asyncio
async def test_augment_failure_returns_original_intel(monkeypatch):
    monkeypatch.setenv("INTEL_USE_RECON_SWARM", "1")

    # Force ReconSwarmCoordinator import path to fail by injecting
    # a module-level shim. Easier: use empty company → coordinator raises.
    intel = {"existing": "stays"}
    out = await augment_with_recon_swarm(
        intel, company="", job_title="Eng", ai_client=None,
    )
    assert out is intel


# ─── Extended field mappings (Wikipedia/leadership/reputation) ─────

def _make_extended_swarm_report() -> dict:
    """Swarm report with the long-tail fields the bridge now wires."""
    return {
        "company": "Acme",
        "intel": {
            "company": "Acme",
            "legal_name": {"value": "Acme Inc.", "confidence": "high",
                           "sources": ["wikipedia"]},
            "is_public": {"value": True, "confidence": "high",
                          "sources": ["sec"]},
            "wikipedia_url": {
                "value": "https://en.wikipedia.org/wiki/Acme_Inc.",
                "confidence": "medium", "sources": ["wikipedia"],
            },
            "eng_headcount": {"value": 320, "confidence": "medium",
                              "sources": ["linkedin_stub"]},
            "work_style": {"value": "hybrid", "confidence": "medium",
                           "sources": ["careers_stub"]},
            "sub_industries": {"value": ["FinTech", "Payments"],
                               "confidence": "medium",
                               "sources": ["wikipedia"]},
            "values": {"value": ["customer obsession", "ownership"],
                       "confidence": "medium",
                       "sources": ["website_crawl_stub"]},
            "benefits": {"value": ["unlimited PTO", "remote-first"],
                         "confidence": "medium",
                         "sources": ["website_crawl_stub"]},
            "investors": {"value": ["Sequoia", "a16z"],
                          "confidence": "high",
                          "sources": ["crunchbase_stub"]},
            "last_round_date": {"value": "2025-09-01",
                                "confidence": "medium",
                                "sources": ["crunchbase_stub"]},
            "products": {"value": ["Acme API", "Acme Pay"],
                         "confidence": "medium",
                         "sources": ["website_crawl_stub"]},
            "product_launches": {
                "value": [{"name": "Acme v3", "date": "2026-04-15"}],
                "confidence": "medium",
                "sources": ["product_hunt_stub"],
            },
            "github_orgs": {"value": ["acme", "acme-labs"],
                            "confidence": "high",
                            "sources": ["github"]},
            "patents_count": {"value": 14, "confidence": "medium",
                              "sources": ["patent_stub"]},
            "leadership": {
                "value": [
                    {"name": "Jane Doe", "title": "CEO"},
                    {"name": "Sam Park", "title": "CTO"},
                ],
                "confidence": "medium",
                "sources": ["linkedin_stub"],
            },
            "hiring_managers": {"value": ["Alex Lee"],
                                "confidence": "low",
                                "sources": ["careers_stub"]},
            "glassdoor_rating": {"value": 4.2, "confidence": "medium",
                                 "sources": ["glassdoor_stub"]},
            "glassdoor_themes": {"value": ["fast-paced", "smart team"],
                                 "confidence": "medium",
                                 "sources": ["glassdoor_stub"]},
            "twitter_handle": {"value": "@acme",
                               "confidence": "high",
                               "sources": ["twitter_stub"]},
            "twitter_sentiment": {"value": "positive",
                                  "confidence": "low",
                                  "sources": ["twitter_stub"]},
            "field_count": 20,
            "high_confidence_count": 5,
            "profile_completeness": 0.55,
        },
        "application_kit": {
            "cover_letter_hooks": [],
            "interview_questions": [],
            "tech_stack_matches": [],
            "talking_points": [],
            "red_flags": [],
            "differentiation_angles": [],
            "resume_bullet_hooks": [],
        },
        "provider_results": [],
        "layers_completed": [1, 2, 3, 4, 5],
        "cache_hit": False,
        "total_latency_ms": 1234,
        "budget_seconds": 60,
    }


def test_merge_swarm_wires_wikipedia_and_overview_extras():
    intel = {}
    merged = merge_swarm_into_intel(intel, _make_extended_swarm_report())
    co = merged["company_overview"]
    assert co["legal_name"] == "Acme Inc."
    assert co["is_public"] is True
    assert co["wikipedia_url"].endswith("Acme_Inc.")
    assert co["eng_headcount"] == 320
    assert co["work_style"] == "hybrid"
    assert "FinTech" in co["sub_industries"]
    assert "customer obsession" in co["values"]
    assert "unlimited PTO" in co["benefits"]


def test_merge_swarm_wires_market_position_extras():
    merged = merge_swarm_into_intel({}, _make_extended_swarm_report())
    mp = merged["market_position"]
    assert "Sequoia" in mp["investors"]
    assert "a16z" in mp["investors"]
    assert mp["last_round_date"] == "2025-09-01"
    assert "Acme API" in mp["products"]
    assert any(p.get("name") == "Acme v3"
               for p in mp["product_launches"])


def test_merge_swarm_wires_tech_extras():
    merged = merge_swarm_into_intel({}, _make_extended_swarm_report())
    te = merged["tech_and_engineering"]
    assert "acme" in te["github_orgs"]
    assert "acme-labs" in te["github_orgs"]
    assert te["patents_count"] == 14


def test_merge_swarm_wires_hiring_leadership():
    merged = merge_swarm_into_intel({}, _make_extended_swarm_report())
    hi = merged["hiring_intelligence"]
    names = {p["name"] for p in hi["leadership"]}
    assert names == {"Jane Doe", "Sam Park"}
    assert "Alex Lee" in hi["hiring_managers"]


def test_merge_swarm_wires_reputation_block():
    merged = merge_swarm_into_intel({}, _make_extended_swarm_report())
    rep = merged["reputation"]
    assert rep["glassdoor_rating"] == 4.2
    assert "fast-paced" in rep["glassdoor_themes"]
    assert rep["twitter_handle"] == "@acme"
    assert rep["twitter_sentiment"] == "positive"


def test_merge_swarm_existing_reputation_scalars_win():
    intel = {"reputation": {"glassdoor_rating": 4.9,
                            "twitter_handle": "@acme_official"}}
    merged = merge_swarm_into_intel(intel, _make_extended_swarm_report())
    assert merged["reputation"]["glassdoor_rating"] == 4.9
    assert merged["reputation"]["twitter_handle"] == "@acme_official"
    # twitter_sentiment was unset → swarm value fills it
    assert merged["reputation"]["twitter_sentiment"] == "positive"


def test_merge_swarm_leadership_dedupes_by_name():
    intel = {"hiring_intelligence": {"leadership": [
        {"name": "Jane Doe", "title": "Co-Founder"},
    ]}}
    merged = merge_swarm_into_intel(intel, _make_extended_swarm_report())
    leadership = merged["hiring_intelligence"]["leadership"]
    names = [p["name"] for p in leadership]
    assert names.count("Jane Doe") == 1
    # Existing entry should win → title stays "Co-Founder"
    jane = next(p for p in leadership if p["name"] == "Jane Doe")
    assert jane["title"] == "Co-Founder"
    # Sam Park appended fresh
    assert any(p["name"] == "Sam Park" for p in leadership)


def test_merge_swarm_product_launches_dedupes_by_name():
    intel = {"market_position": {"product_launches": [
        {"name": "Acme v3", "date": "2025-12-01"},
    ]}}
    merged = merge_swarm_into_intel(intel, _make_extended_swarm_report())
    launches = merged["market_position"]["product_launches"]
    assert len(launches) == 1
    # existing entry wins
    assert launches[0]["date"] == "2025-12-01"
