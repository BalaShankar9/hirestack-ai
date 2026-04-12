"""Tests for DocumentPackPlanner — catalog-driven AI document selection."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ai_engine.chains.document_pack_planner import (
    CORE_DOCS,
    DocumentPackPlan,
    DocumentPackPlanner,
)


# ── Fixtures ──────────────────────────────────────────────────────────

SAMPLE_CATALOG = [
    {"key": "cv", "label": "Tailored CV", "category": "core", "seen_count": 100},
    {"key": "cover_letter", "label": "Cover Letter", "category": "core", "seen_count": 95},
    {"key": "personal_statement", "label": "Personal Statement", "category": "core", "seen_count": 80},
    {"key": "portfolio", "label": "Portfolio & Evidence", "category": "core", "seen_count": 70},
    {"key": "executive_summary", "label": "Executive Summary", "category": "executive", "seen_count": 20},
    {"key": "ninety_day_plan", "label": "90-Day Plan", "category": "executive", "seen_count": 15},
    {"key": "selection_criteria", "label": "Selection Criteria Response", "category": "compliance", "seen_count": 8},
    {"key": "research_statement", "label": "Research Statement", "category": "academic", "seen_count": 5},
    {"key": "teaching_philosophy", "label": "Teaching Philosophy", "category": "academic", "seen_count": 4},
    {"key": "diversity_statement", "label": "Diversity Statement", "category": "compliance", "seen_count": 3},
    {"key": "code_samples", "label": "Code Samples", "category": "technical", "seen_count": 12},
]


def _make_ai_response(
    required=None, optional=None, new_candidates=None,
    industry="technology", job_level="senior", confidence=0.85,
):
    """Build a simulated AI response dict."""
    return {
        "required": required or [],
        "optional": optional or [],
        "new_candidates": new_candidates or [],
        "industry": industry,
        "job_level": job_level,
        "strategy": "Test strategy for the role",
        "tone": "professional",
        "key_themes": ["leadership", "scalability"],
        "confidence": confidence,
    }


# ═══════════════════════════════════════════════════════════════════════
#  DocumentPackPlan dataclass tests
# ═══════════════════════════════════════════════════════════════════════

class TestDocumentPackPlan:
    def test_default_empty(self):
        plan = DocumentPackPlan()
        assert plan.core == []
        assert plan.required == []
        assert plan.optional == []
        assert plan.confidence == 0.8

    def test_all_required_keys(self):
        plan = DocumentPackPlan(
            core=[{"key": "cv"}, {"key": "cover_letter"}],
            required=[{"key": "executive_summary"}, {"key": "ninety_day_plan"}],
        )
        keys = plan.all_required_keys()
        assert keys == ["cv", "cover_letter", "executive_summary", "ninety_day_plan"]

    def test_all_optional_keys(self):
        plan = DocumentPackPlan(
            optional=[{"key": "code_samples"}, {"key": "diversity_statement"}],
        )
        assert plan.all_optional_keys() == ["code_samples", "diversity_statement"]

    def test_to_dict_has_expected_keys(self):
        plan = DocumentPackPlan(
            core=list(CORE_DOCS),
            required=[{"key": "executive_summary"}],
            strategy="Test strategy",
            industry="technology",
            confidence=0.9,
        )
        d = plan.to_dict()
        assert d["core"] == list(CORE_DOCS)
        assert d["strategy"] == "Test strategy"
        assert d["industry"] == "technology"
        assert d["confidence"] == 0.9
        assert "deferred_count" in d
        assert "reasons" in d

    def test_to_dict_deferred_count(self):
        plan = DocumentPackPlan(
            deferred=[{"key": "a"}, {"key": "b"}, {"key": "c"}],
        )
        assert plan.to_dict()["deferred_count"] == 3


# ═══════════════════════════════════════════════════════════════════════
#  DocumentPackPlanner tests
# ═══════════════════════════════════════════════════════════════════════

class TestDocumentPackPlanner:
    @pytest.mark.asyncio
    async def test_plan_core_always_included(self):
        """Core docs appear in the plan even if AI doesn't mention them."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response())

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Senior Python Developer", job_title="SWE")

        core_keys = {d["key"] for d in plan.core}
        assert core_keys == {"cv", "cover_letter", "personal_statement", "portfolio"}

    @pytest.mark.asyncio
    async def test_plan_required_from_catalog(self):
        """Required docs come from the catalog, not invented."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            required=[
                {"key": "executive_summary", "label": "Executive Summary", "reason": "Senior role"},
                {"key": "ninety_day_plan", "label": "90-Day Plan", "reason": "Exec requirement"},
            ],
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="VP Engineering", job_title="VP Eng")

        req_keys = {d["key"] for d in plan.required}
        assert "executive_summary" in req_keys
        assert "ninety_day_plan" in req_keys

    @pytest.mark.asyncio
    async def test_plan_rejects_core_in_required(self):
        """AI might redundantly put core docs in required — planner should filter them out."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            required=[
                {"key": "cv", "label": "CV again", "reason": "always"},
                {"key": "code_samples", "label": "Code Samples", "reason": "Tech role"},
            ],
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Dev role", job_title="Dev")

        req_keys = [d["key"] for d in plan.required]
        assert "cv" not in req_keys
        assert "code_samples" in req_keys

    @pytest.mark.asyncio
    async def test_plan_rejects_unknown_in_required(self):
        """Required docs not in catalog are silently skipped."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            required=[
                {"key": "nonexistent_doc", "label": "Made Up", "reason": "test"},
            ],
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Test", job_title="Test")

        assert len(plan.required) == 0

    @pytest.mark.asyncio
    async def test_plan_optional_excludes_required(self):
        """Optional should not duplicate required docs."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            required=[{"key": "code_samples", "label": "Code Samples", "reason": "Tech"}],
            optional=[{"key": "code_samples", "label": "Code Samples", "reason": "Also nice"}],
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Dev", job_title="Dev")

        opt_keys = [d["key"] for d in plan.optional]
        assert "code_samples" not in opt_keys  # already in required

    @pytest.mark.asyncio
    async def test_plan_new_candidates_unknown_keys(self):
        """New candidates are doc types NOT in the catalog."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            new_candidates=[
                {"key": "security_clearance_form", "label": "Security Clearance", "reason": "Gov role"},
            ],
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Gov contractor", job_title="Analyst")

        assert len(plan.new_candidates) == 1
        assert plan.new_candidates[0]["key"] == "security_clearance_form"

    @pytest.mark.asyncio
    async def test_plan_new_candidates_rejects_catalog_keys(self):
        """New candidates that ARE in catalog should be ignored."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            new_candidates=[
                {"key": "code_samples", "label": "Code Samples", "reason": "Already in catalog"},
            ],
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Dev", job_title="Dev")

        assert len(plan.new_candidates) == 0

    @pytest.mark.asyncio
    async def test_plan_deferred_populated(self):
        """Deferred contains catalog entries not selected by the AI."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response())

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Simple role", job_title="Tester")

        deferred_keys = {d["key"] for d in plan.deferred}
        # Everything non-core should be deferred if no required/optional
        assert "executive_summary" in deferred_keys
        assert "selection_criteria" in deferred_keys

    @pytest.mark.asyncio
    async def test_plan_reasons_populated(self):
        """Plan reasons dict should contain entries for core + required + optional."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            required=[{"key": "code_samples", "label": "Code Samples", "reason": "Tech assessment needed"}],
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Dev", job_title="Dev")

        assert "cv" in plan.reasons  # core
        assert "code_samples" in plan.reasons  # required

    @pytest.mark.asyncio
    async def test_plan_confidence_clamped(self):
        """Confidence is clamped to [0.0, 1.0]."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(confidence=1.5))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="X", job_title="X")

        assert plan.confidence == 1.0

    @pytest.mark.asyncio
    async def test_plan_confidence_clamped_negative(self):
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(confidence=-0.5))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="X", job_title="X")

        assert plan.confidence == 0.0

    @pytest.mark.asyncio
    async def test_plan_graceful_fallback_on_ai_error(self):
        """On AI failure, planner returns core-only plan with low confidence."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(side_effect=Exception("API key invalid"))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="Test", job_title="Test")

        core_keys = {d["key"] for d in plan.core}
        assert core_keys == {"cv", "cover_letter", "personal_statement", "portfolio"}
        assert plan.confidence == 0.3
        assert len(plan.required) == 0
        assert "Fallback" in plan.strategy

    @pytest.mark.asyncio
    async def test_plan_metadata_propagated(self):
        """Industry, job_level, tone, key_themes propagate from AI response."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            industry="finance", job_level="executive",
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(jd_text="CFO", job_title="CFO")

        assert plan.industry == "finance"
        assert plan.job_level == "executive"
        assert plan.tone == "professional"
        assert plan.key_themes == ["leadership", "scalability"]

    @pytest.mark.asyncio
    async def test_plan_government_jd_selects_selection_criteria(self):
        """Integration-style: government JD should prompt AI to select selection_criteria."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response(
            required=[
                {"key": "selection_criteria", "label": "Selection Criteria", "reason": "Government"},
                {"key": "diversity_statement", "label": "Diversity Statement", "reason": "APS requirement"},
            ],
            industry="government",
            job_level="mid",
        ))

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        plan = await planner.plan(
            jd_text="APS Level 6 Policy Officer, Department of Home Affairs",
            job_title="Policy Officer",
        )

        req_keys = {d["key"] for d in plan.required}
        assert "selection_criteria" in req_keys
        assert plan.industry == "government"

    @pytest.mark.asyncio
    async def test_plan_profile_summary_in_prompt(self):
        """User profile data is included in the AI prompt."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response())

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        await planner.plan(
            jd_text="Dev role",
            job_title="SWE",
            user_profile={
                "name": "Jane Doe",
                "experience_years": 10,
                "skills": ["Python", "AWS", "Terraform"],
            },
        )

        # Verify the prompt contains profile info
        call_args = ai.complete_json.call_args
        prompt = call_args.kwargs.get("prompt", call_args[0][0] if call_args[0] else "")
        assert "Jane Doe" in prompt
        assert "10 years" in prompt

    @pytest.mark.asyncio
    async def test_plan_empty_catalog(self):
        """Planner works with an empty catalog (only core docs)."""
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value=_make_ai_response())

        planner = DocumentPackPlanner(ai_client=ai, catalog=[])
        plan = await planner.plan(jd_text="Test", job_title="Test")

        assert len(plan.core) == 4
        assert len(plan.deferred) == 0
