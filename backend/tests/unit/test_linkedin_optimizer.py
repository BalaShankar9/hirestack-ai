"""S16-P2 — LinkedIn Profile Optimizer tests."""
from __future__ import annotations

import pytest

from ai_engine.agents.linkedin import (
    LinkedInOptimizer,
    LinkedInProfile,
    build_linkedin_tools,
    detect_linkedin_intent,
    score_profile,
    score_section,
)
from ai_engine.agents.linkedin.schemas import ExperienceItem


# ─── stubs ──────────────────────────────────────────────────────────

class _StubClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def complete_json(self, **kwargs):
        self.calls += 1
        return self._payload


class _RaisingClient:
    async def complete_json(self, **kwargs):
        raise RuntimeError("no llm")


def _weak_profile() -> LinkedInProfile:
    return LinkedInProfile(headline="SWE", about="I write code.", skills=["python"])


def _strong_profile() -> LinkedInProfile:
    return LinkedInProfile(
        headline="Senior Software Engineer | Distributed systems leader who scaled platform to 10M users",
        about=(
            "Senior software engineer with 8 years of experience leading "
            "distributed systems teams. I shipped a checkout rewrite that "
            "reduced latency by 30%, scaled an analytics pipeline to 10M "
            "events per minute, and mentored 5 engineers into senior roles. "
            "I lead with clear writing, fast iteration, and measurable "
            "outcomes. Recent wins include reducing on-call pages by 40%, "
            "growing API adoption by 25%, and launching a multi-region "
            "failover. I care about systems that compound, mentorship that "
            "scales people, and metrics that matter. Open to staff-level "
            "engineering roles where craft and autonomy are the norm."
        ),
        experience=[
            ExperienceItem(
                title="Senior Software Engineer",
                company="Acme",
                duration="2021 - present",
                description=(
                    "Led platform redesign that reduced p99 latency by 30%. "
                    "Shipped distributed scheduler. Mentored 3 engineers. "
                    "Drove 25% growth in API adoption."
                ),
            ),
        ],
        skills=["python", "distributed systems", "go", "kafka", "kubernetes",
                "postgres", "redis", "design"],
    )


# ─── intent ─────────────────────────────────────────────────────────

def test_intent_positive():
    assert detect_linkedin_intent("Optimize my LinkedIn profile please") is not None
    assert detect_linkedin_intent("Can you rewrite my linkedin?") is not None


def test_intent_negative():
    assert detect_linkedin_intent("hello world") is None
    assert detect_linkedin_intent("") is None


# ─── ATS scorer ─────────────────────────────────────────────────────

def test_score_section_headline_short_low():
    score, fb = score_section("headline", "SWE", "Software Engineer")
    assert score < 0.6
    assert fb


def test_score_section_headline_well_formed_high():
    text = "Senior Software Engineer | Distributed systems leader scaling platforms to 10M users daily"
    score, _ = score_section("headline", text, "Software Engineer")
    assert score >= 0.6


def test_score_section_unsupported_raises():
    with pytest.raises(ValueError):
        score_section("foo", "bar", "baz")


def test_score_profile_weak_vs_strong_orders_correctly():
    weak = score_profile(_weak_profile(), "Software Engineer")
    strong = score_profile(_strong_profile(), "Software Engineer")
    assert strong.overall > weak.overall
    assert strong.about > weak.about
    assert strong.experience > weak.experience
    assert strong.quantified_achievements >= 2


# ─── optimizer ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_optimize_with_llm_payload_improves_score():
    payload = {
        "headline": ("Senior Software Engineer | Distributed systems leader "
                     "who scaled platforms to 10M users daily"),
        "about": (
            "Senior software engineer with 8 years building distributed "
            "systems. Led platform redesign that reduced p99 latency by "
            "30%. Scaled analytics pipeline to 10M events per minute. "
            "Mentored 5 engineers into senior roles. I care about clear "
            "writing, fast iteration, and outcomes that compound. Recent "
            "wins include reducing on-call pages by 40%, growing API "
            "adoption by 25%, and launching multi-region failover. Open "
            "to staff-level roles where craft and autonomy are the norm."
        ),
        "rationale_headline": "Tightened to 110 chars with role + outcome.",
        "rationale_about": "Expanded with quantified outcomes.",
    }
    optimizer = LinkedInOptimizer(ai_client=_StubClient(payload))
    report = await optimizer.optimize(_weak_profile(), "Software Engineer")
    assert report.score_after.overall > report.score_before.overall
    assert len(report.results) == 2
    assert report.results[0].score_after >= report.results[0].score_before
    assert report.headline_variants  # AB defaults to True


@pytest.mark.asyncio
async def test_optimize_falls_back_when_llm_raises():
    optimizer = LinkedInOptimizer(ai_client=_RaisingClient())
    report = await optimizer.optimize(_weak_profile(), "Software Engineer",
                                       include_headline_ab=False)
    assert report.score_after.overall >= report.score_before.overall
    assert report.results[0].optimized  # deterministic rewrite present
    assert report.results[1].optimized
    assert report.headline_variants == []


@pytest.mark.asyncio
async def test_headline_ab_uses_llm_payload():
    payload = {"variants": [
        {"text": "Senior SWE | Shipped 30% latency reduction across the platform stack",
         "hook_type": "results"},
        {"text": "Senior SWE | Translating ambiguous strategy into shipped distributed systems",
         "hook_type": "value-prop"},
    ]}
    optimizer = LinkedInOptimizer(ai_client=_StubClient(payload))
    variants = await optimizer.headline_ab(_strong_profile(), "Software Engineer", n=2)
    assert len(variants) == 2
    assert all(v.text for v in variants)
    assert variants[0].hook_type == "results"


@pytest.mark.asyncio
async def test_headline_ab_falls_back_without_llm():
    optimizer = LinkedInOptimizer(ai_client=_RaisingClient())
    variants = await optimizer.headline_ab(_weak_profile(), "Software Engineer", n=3)
    assert len(variants) == 3
    assert all(len(v.text) <= 120 for v in variants)


@pytest.mark.asyncio
async def test_optimize_blank_role_raises():
    optimizer = LinkedInOptimizer(ai_client=_RaisingClient())
    with pytest.raises(ValueError):
        await optimizer.optimize(_weak_profile(), "   ")


# ─── tool registry ─────────────────────────────────────────────────

def test_build_linkedin_tools_registers_both():
    reg = build_linkedin_tools()
    assert reg.get("optimize_linkedin_profile") is not None
    assert reg.get("generate_linkedin_headline_ab") is not None
