"""
P2-11: Verify all generated content is saved to Supabase correctly.

Tests that _persist_generation_result_to_application writes the correct
columns for every module type and that module state transitions are correct.
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from app.api.routes.generate.jobs import (
    _persist_generation_result_to_application,
    _merge_module_states,
)


# ── Fake Supabase builder ──────────────────────────────────────────────

class _FakeSB:
    """Minimal supabase-py facade that records .update() calls."""

    def __init__(self):
        self.updates: List[Dict[str, Any]] = []
        self._pending: Dict[str, Any] = {}

    def table(self, _name: str) -> "_FakeSB":
        return self

    def update(self, patch: Dict[str, Any]) -> "_FakeSB":
        self._pending = dict(patch)
        return self

    def select(self, *_a, **_kw) -> "_FakeSB":
        return self

    def eq(self, *_a) -> "_FakeSB":
        return self

    def limit(self, *_a) -> "_FakeSB":
        return self

    def execute(self) -> Any:
        self.updates.append(dict(self._pending))
        self._pending = {}
        return MagicMock(data=[{"id": "app-1"}])

    def insert(self, row: Dict[str, Any]) -> "_FakeSB":
        return self


TABLES = {
    "applications": "applications",
    "generation_jobs": "generation_jobs",
    "generation_job_events": "generation_job_events",
    "tasks": "tasks",
    "document_library": "document_library",
}

_BASE_APP_ROW: Dict[str, Any] = {
    "id": "app-1",
    "user_id": "user-1",
    "modules": {},
}

_FULL_RESULT: Dict[str, Any] = {
    "benchmark": {"ideal_skills": [{"name": "Python", "importance": "critical"}], "min_years": 5},
    "gaps": {"compatibility_score": 72, "skill_gaps": [], "missingKeywords": ["Kubernetes"]},
    "learningPlan": {"focus": "Cloud skills", "plan": [{"week": 1, "theme": "AWS", "tasks": ["Complete AWS cert"]}]},
    "cvHtml": "<div><h1>Jane Doe</h1></div>",
    "cvVariants": [{"id": "v1", "html": "<div>v1</div>", "locked": True}],
    "coverLetterHtml": "<p>Dear Hiring Manager,</p>",
    "personalStatementHtml": "<p>I am passionate about...</p>",
    "personalStatementVariants": [{"id": "ps1", "html": "<p>PS v1</p>", "locked": True}],
    "portfolioHtml": "<div>Portfolio</div>",
    "resumeHtml": "<div>Resume</div>",
    "scorecard": {"overall": 85, "categories": {}},
    "scores": {"relevance": 90},
    "validation": {"passed": True, "checks": []},
    "companyIntel": {"name": "Acme", "size": "large"},
}


def _get_patch_from_sb(sb: _FakeSB) -> Dict[str, Any]:
    """Merge all update calls into a single flat patch dict."""
    merged: Dict[str, Any] = {}
    for update in sb.updates:
        merged.update(update)
    return merged


# ═══════════════════════════════════════════════════════════════════════
#  Column persistence tests (P2-11)
# ═══════════════════════════════════════════════════════════════════════

class TestPersistAllModuleColumns:
    """Verify every generated field reaches the correct DB column."""

    @pytest.mark.asyncio
    async def test_persists_benchmark_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["benchmark"],
                        result={"benchmark": _FULL_RESULT["benchmark"]},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "benchmark" in patch_data
        assert patch_data["benchmark"]["ideal_skills"][0]["name"] == "Python"
        assert "createdAt" in patch_data["benchmark"]

    @pytest.mark.asyncio
    async def test_persists_gap_analysis_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["gaps"],
                        result={"gaps": _FULL_RESULT["gaps"]},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "gaps" in patch_data
        assert patch_data["gaps"]["compatibility_score"] == 72

    @pytest.mark.asyncio
    async def test_persists_learning_plan_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["learningPlan"],
                        result={"learningPlan": _FULL_RESULT["learningPlan"]},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "learning_plan" in patch_data
        assert patch_data["learning_plan"]["focus"] == "Cloud skills"

    @pytest.mark.asyncio
    async def test_persists_cv_html_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["cv"],
                        result={"cvHtml": _FULL_RESULT["cvHtml"]},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "cv_html" in patch_data
        assert "<h1>Jane Doe</h1>" in patch_data["cv_html"]

    @pytest.mark.asyncio
    async def test_persists_cv_variants_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["cv"],
                        result={
                            "cvHtml": _FULL_RESULT["cvHtml"],
                            "cvVariants": _FULL_RESULT["cvVariants"],
                        },
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "cv_variants" in patch_data
        assert patch_data["cv_variants"][0]["locked"] is True

    @pytest.mark.asyncio
    async def test_persists_cover_letter_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["coverLetter"],
                        result={"coverLetterHtml": _FULL_RESULT["coverLetterHtml"]},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "cover_letter_html" in patch_data
        assert "Dear Hiring Manager" in patch_data["cover_letter_html"]

    @pytest.mark.asyncio
    async def test_persists_personal_statement_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["personalStatement"],
                        result={"personalStatementHtml": _FULL_RESULT["personalStatementHtml"]},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "personal_statement_html" in patch_data

    @pytest.mark.asyncio
    async def test_persists_ps_variants_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["personalStatement"],
                        result={
                            "personalStatementHtml": _FULL_RESULT["personalStatementHtml"],
                            "personalStatementVariants": _FULL_RESULT["personalStatementVariants"],
                        },
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "ps_variants" in patch_data
        assert patch_data["ps_variants"][0]["locked"] is True

    @pytest.mark.asyncio
    async def test_persists_portfolio_column(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["portfolio"],
                        result={"portfolioHtml": _FULL_RESULT["portfolioHtml"]},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "portfolio_html" in patch_data

    @pytest.mark.asyncio
    async def test_persists_scorecard_columns(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["scorecard"],
                        result={
                            "scorecard": _FULL_RESULT["scorecard"],
                            "scores": _FULL_RESULT["scores"],
                            "validation": _FULL_RESULT["validation"],
                        },
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "scorecard" in patch_data
        assert patch_data["scorecard"]["overall"] == 85
        assert "scores" in patch_data
        assert "validation" in patch_data
        assert "updatedAt" in patch_data["scorecard"]

    @pytest.mark.asyncio
    async def test_persists_company_intel(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["benchmark"],
                        result={
                            "benchmark": _FULL_RESULT["benchmark"],
                            "companyIntel": _FULL_RESULT["companyIntel"],
                        },
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "company_intel" in patch_data
        assert patch_data["company_intel"]["name"] == "Acme"

    @pytest.mark.asyncio
    async def test_all_modules_full_pipeline(self):
        """Verify a full pipeline result persists every expected column."""
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["benchmark", "gaps", "learningPlan", "cv", "coverLetter",
                                           "personalStatement", "portfolio", "scorecard"],
                        result=_FULL_RESULT,
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        expected_columns = [
            "benchmark", "gaps", "learning_plan",
            "cv_html", "cv_variants",
            "cover_letter_html",
            "personal_statement_html", "ps_variants",
            "portfolio_html",
            "scorecard", "scores", "validation",
            "modules",
        ]
        for col in expected_columns:
            assert col in patch_data, f"Column '{col}' was not persisted"


# ═══════════════════════════════════════════════════════════════════════
#  Module state transition tests
# ═══════════════════════════════════════════════════════════════════════

class TestModuleStateTransitions:
    """Verify modules are marked ready/error based on whether content exists."""

    @pytest.mark.asyncio
    async def test_module_marked_ready_when_content_exists(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["cv"],
                        result={"cvHtml": "<div>CV content</div>"},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        modules = patch_data.get("modules", {})
        assert modules.get("cv", {}).get("state") == "ready"

    @pytest.mark.asyncio
    async def test_module_marked_error_when_content_missing(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["cv"],
                        result={"cvHtml": ""},  # empty HTML
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        modules = patch_data.get("modules", {})
        assert modules.get("cv", {}).get("state") == "error"

    @pytest.mark.asyncio
    async def test_module_error_message_contains_module_name(self):
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["coverLetter"],
                        result={"coverLetterHtml": ""},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        modules = patch_data.get("modules", {})
        error_msg = modules.get("coverLetter", {}).get("error", "")
        assert "coverLetter" in error_msg

    @pytest.mark.asyncio
    async def test_only_requested_modules_have_state_updated(self):
        """Modules NOT in requested_modules should not have state changed."""
        existing_modules = {
            "portfolio": {"state": "ready", "updatedAt": 1_000_000},
        }
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row={**_BASE_APP_ROW, "modules": existing_modules},
                        requested_modules=["cv"],
                        result={"cvHtml": "<div>CV</div>"},
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        modules = patch_data.get("modules", {})
        # Portfolio was not requested — its state should be preserved
        assert modules.get("portfolio", {}).get("state") == "ready"
        # CV was requested and has content — should be ready
        assert modules.get("cv", {}).get("state") == "ready"

    @pytest.mark.asyncio
    async def test_resume_html_persisted_without_being_requested(self):
        """resume_html is always persisted if present, even if not in requested_modules."""
        sb = _FakeSB()
        with patch("app.api.routes.generate.jobs._sync_generation_tasks", new=AsyncMock()):
            with patch("app.api.routes.generate.jobs._sync_document_library", new=AsyncMock()):
                with patch("app.api.routes.generate.jobs._run_post_generation_hooks", new=AsyncMock()):
                    await _persist_generation_result_to_application(
                        sb, TABLES,
                        application_row=dict(_BASE_APP_ROW),
                        requested_modules=["cv"],  # resume not requested explicitly
                        result={
                            "cvHtml": "<div>CV</div>",
                            "resumeHtml": "<div>Resume</div>",
                        },
                        user_id="user-1",
                    )
        patch_data = _get_patch_from_sb(sb)
        assert "resume_html" in patch_data
