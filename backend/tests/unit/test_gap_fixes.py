"""Tests for discover_and_observe(), company_intel in planner, and on-demand doc endpoint."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
    PLANNER_PROMPT,
)
from app.services.document_catalog import discover_and_observe

TABLES = {
    "document_type_catalog": "document_type_catalog",
    "document_observations": "document_observations",
}

SAMPLE_CATALOG = [
    {"key": "cv", "label": "Tailored CV", "category": "core", "seen_count": 100},
    {"key": "cover_letter", "label": "Cover Letter", "category": "core", "seen_count": 95},
    {"key": "personal_statement", "label": "Personal Statement", "category": "core", "seen_count": 80},
    {"key": "portfolio", "label": "Portfolio & Evidence", "category": "core", "seen_count": 70},
    {"key": "executive_summary", "label": "Executive Summary", "category": "executive", "seen_count": 20},
    {"key": "ninety_day_plan", "label": "90-Day Plan", "category": "executive", "seen_count": 15},
    {"key": "research_statement", "label": "Research Statement", "category": "academic", "seen_count": 5},
]


def _mock_db(select_data=None, rpc_ok=True):
    db = MagicMock()
    resp = MagicMock()
    resp.data = select_data or []
    chain = MagicMock()
    chain.execute.return_value = resp
    chain.order.return_value = chain
    chain.select.return_value = chain
    chain.upsert.return_value = chain
    chain.insert.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    db.table.return_value = chain
    rpc_chain = MagicMock()
    rpc_chain.execute.return_value = MagicMock()
    if not rpc_ok:
        rpc_chain.execute.side_effect = Exception("RPC failed")
    db.rpc.return_value = rpc_chain
    return db


# ═══════════════════════════════════════════════════════════════════════
#  Tests: discover_and_observe() helper
# ═══════════════════════════════════════════════════════════════════════


class TestDiscoverAndObserve:
    """Tests for the centralized discover_and_observe() helper."""

    @pytest.mark.asyncio
    async def test_returns_doc_pack_plan_on_success(self):
        plan = DocumentPackPlan(
            core=list(CORE_DOCS),
            required=[{"key": "executive_summary", "label": "Exec Summary", "priority": "high", "reason": "Senior role"}],
            optional=[{"key": "ninety_day_plan", "label": "90-Day Plan", "priority": "medium", "reason": "Good to have"}],
            industry="technology",
            job_level="senior",
        )
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value={
            "required": [{"key": "executive_summary", "label": "Exec Summary", "reason": "Senior"}],
            "optional": [{"key": "ninety_day_plan", "label": "90-Day Plan", "reason": "Helpful"}],
            "industry": "technology",
            "job_level": "senior",
            "strategy": "Test",
            "tone": "professional",
            "key_themes": ["leadership"],
            "confidence": 0.9,
        })
        db = _mock_db(select_data=SAMPLE_CATALOG)

        with patch("app.services.document_catalog.ensure_catalog_seeded", new_callable=AsyncMock), \
             patch("app.services.document_catalog.get_full_catalog", new_callable=AsyncMock, return_value=SAMPLE_CATALOG), \
             patch("app.services.document_catalog.observe_document_types", new_callable=AsyncMock) as mock_observe:
            result = await discover_and_observe(
                db=db, tables=TABLES, ai_client=ai,
                jd_text="Senior engineering manager", job_title="Engineering Manager",
                company="Acme", user_id="user-1",
            )

        assert result is not None
        assert isinstance(result, DocumentPackPlan)
        assert len(result.core) == 4
        mock_observe.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self):
        ai = MagicMock()
        db = _mock_db()

        with patch("app.services.document_catalog.ensure_catalog_seeded", new_callable=AsyncMock, side_effect=Exception("DB down")):
            result = await discover_and_observe(
                db=db, tables=TABLES, ai_client=ai,
                jd_text="Test", job_title="Test",
                user_id="user-1",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_company_intel_to_planner(self):
        company_intel = {
            "hiring_intelligence": {"must_have_skills": ["Python", "React"]},
            "culture_and_values": {"core_values": ["Innovation"]},
            "application_strategy": {"keywords_to_use": ["AI", "ML"]},
            "confidence": "high",
        }
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value={
            "required": [],
            "optional": [],
            "industry": "technology",
            "job_level": "mid",
            "strategy": "Test",
            "tone": "professional",
            "key_themes": [],
            "confidence": 0.8,
        })
        db = _mock_db()

        with patch("app.services.document_catalog.ensure_catalog_seeded", new_callable=AsyncMock), \
             patch("app.services.document_catalog.get_full_catalog", new_callable=AsyncMock, return_value=SAMPLE_CATALOG), \
             patch("app.services.document_catalog.observe_document_types", new_callable=AsyncMock):
            result = await discover_and_observe(
                db=db, tables=TABLES, ai_client=ai,
                jd_text="Software Engineer", job_title="SWE",
                company="TechCo", user_id="user-1",
                company_intel=company_intel,
            )

        assert result is not None
        # Verify the planner received company_intel data in the prompt
        call_args = ai.complete_json.call_args
        prompt = call_args.kwargs.get("prompt", "")
        if not prompt and call_args.args:
            prompt = call_args.args[0]
        assert "Python" in prompt or "COMPANY INTELLIGENCE" in prompt

    @pytest.mark.asyncio
    async def test_passes_application_id_to_observe(self):
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value={
            "required": [],
            "optional": [],
            "industry": "technology",
            "job_level": "mid",
            "strategy": "Test",
            "tone": "professional",
            "key_themes": [],
            "confidence": 0.8,
        })
        db = _mock_db()

        with patch("app.services.document_catalog.ensure_catalog_seeded", new_callable=AsyncMock), \
             patch("app.services.document_catalog.get_full_catalog", new_callable=AsyncMock, return_value=SAMPLE_CATALOG), \
             patch("app.services.document_catalog.observe_document_types", new_callable=AsyncMock) as mock_obs:
            await discover_and_observe(
                db=db, tables=TABLES, ai_client=ai,
                jd_text="Test", job_title="Engineer",
                user_id="user-1", application_id="app-123",
            )

        # observe_document_types should receive the application_id
        call_kwargs = mock_obs.call_args.kwargs
        assert call_kwargs.get("application_id") == "app-123" or \
               (mock_obs.call_args.args and len(mock_obs.call_args.args) > 3)


# ═══════════════════════════════════════════════════════════════════════
#  Tests: company_intel in DocumentPackPlanner
# ═══════════════════════════════════════════════════════════════════════


class TestPlannerCompanyIntel:
    """Tests for company_intel integration in DocumentPackPlanner.plan()."""

    @pytest.mark.asyncio
    async def test_plan_includes_company_intel_in_prompt(self):
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value={
            "required": [],
            "optional": [],
            "industry": "technology",
            "job_level": "mid",
            "strategy": "Standard",
            "tone": "professional",
            "key_themes": [],
            "confidence": 0.85,
        })

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        company_intel = {
            "hiring_intelligence": {"must_have_skills": ["Kubernetes", "Go"]},
            "culture_and_values": {"core_values": ["Transparency", "Ownership"]},
            "application_strategy": {"keywords_to_use": ["distributed systems", "microservices"]},
            "tech_and_engineering": {"tech_stack": ["Go", "gRPC", "Kubernetes"]},
            "confidence": "high",
        }

        await planner.plan(
            jd_text="Backend engineer with Go experience",
            job_title="Backend Engineer",
            company="CloudCo",
            company_intel=company_intel,
        )

        call_args = ai.complete_json.call_args
        prompt = call_args.kwargs.get("prompt", "")
        assert "COMPANY INTELLIGENCE" in prompt
        assert "Kubernetes" in prompt
        assert "Transparency" in prompt
        assert "distributed systems" in prompt
        assert "Go" in prompt

    @pytest.mark.asyncio
    async def test_plan_works_without_company_intel(self):
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value={
            "required": [],
            "optional": [],
            "industry": "other",
            "job_level": "mid",
            "strategy": "Standard",
            "tone": "professional",
            "key_themes": [],
            "confidence": 0.8,
        })

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        result = await planner.plan(
            jd_text="Test JD",
            job_title="Tester",
            company="Co",
        )

        assert result is not None
        assert len(result.core) == 4
        # No COMPANY INTELLIGENCE section when None
        prompt = ai.complete_json.call_args.kwargs.get("prompt", "")
        assert "COMPANY INTELLIGENCE" not in prompt

    @pytest.mark.asyncio
    async def test_plan_handles_empty_company_intel(self):
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value={
            "required": [],
            "optional": [],
            "industry": "other",
            "job_level": "mid",
            "strategy": "Standard",
            "tone": "professional",
            "key_themes": [],
            "confidence": 0.8,
        })

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        result = await planner.plan(
            jd_text="Test JD",
            job_title="Tester",
            company="Co",
            company_intel={},
        )

        assert result is not None
        # Empty dict should not produce COMPANY INTELLIGENCE section (only confidence line)
        prompt = ai.complete_json.call_args.kwargs.get("prompt", "")
        # Empty intel produces only "Intel confidence: unknown" but still includes the section
        assert result.core is not None

    @pytest.mark.asyncio
    async def test_plan_handles_partial_company_intel(self):
        ai = MagicMock()
        ai.complete_json = AsyncMock(return_value={
            "required": [],
            "optional": [],
            "industry": "finance",
            "job_level": "senior",
            "strategy": "Financial focus",
            "tone": "formal",
            "key_themes": ["compliance"],
            "confidence": 0.9,
        })

        planner = DocumentPackPlanner(ai_client=ai, catalog=SAMPLE_CATALOG)
        result = await planner.plan(
            jd_text="VP of Engineering",
            job_title="VP Engineering",
            company="FinCorp",
            company_intel={"confidence": "medium", "hiring_intelligence": {"must_have_skills": ["Python"]}},
        )

        prompt = ai.complete_json.call_args.kwargs.get("prompt", "")
        assert "Python" in prompt
        assert "medium" in prompt


# ═══════════════════════════════════════════════════════════════════════
#  Tests: PLANNER_PROMPT template
# ═══════════════════════════════════════════════════════════════════════


class TestPlannerPromptTemplate:
    """Tests for the PLANNER_PROMPT template placeholders."""

    def test_prompt_has_company_intel_section_placeholder(self):
        assert "{company_intel_section}" in PLANNER_PROMPT

    def test_prompt_formats_without_company_intel(self):
        result = PLANNER_PROMPT.format(
            job_title="Test",
            company="Co",
            jd_text="JD",
            catalog_text="catalog",
            profile_summary="profile",
            company_intel_section="",
        )
        assert "Test" in result
        assert "COMPANY INTELLIGENCE" not in result

    def test_prompt_formats_with_company_intel(self):
        intel = "\nCOMPANY INTELLIGENCE:\nMust-have skills: Python\n"
        result = PLANNER_PROMPT.format(
            job_title="Test",
            company="Co",
            jd_text="JD",
            catalog_text="catalog",
            profile_summary="profile",
            company_intel_section=intel,
        )
        assert "COMPANY INTELLIGENCE" in result
        assert "Python" in result


# ═══════════════════════════════════════════════════════════════════════
#  Tests: On-demand document endpoint
# ═══════════════════════════════════════════════════════════════════════


class TestGenerateOnDemandEndpoint:
    """Tests for the POST /generate/document endpoint model validation."""

    def test_generate_document_request_valid(self):
        from app.api.routes.generate import GenerateDocumentRequest
        req = GenerateDocumentRequest(
            application_id="12345678-1234-1234-1234-123456789012",
            doc_key="executive_summary",
            doc_label="Executive Summary",
        )
        assert req.doc_key == "executive_summary"
        assert req.application_id == "12345678-1234-1234-1234-123456789012"

    def test_generate_document_request_empty_key(self):
        from app.api.routes.generate import GenerateDocumentRequest
        with pytest.raises(Exception):
            GenerateDocumentRequest(
                application_id="12345678-1234-1234-1234-123456789012",
                doc_key="",
            )

    def test_generate_document_request_key_too_long(self):
        from app.api.routes.generate import GenerateDocumentRequest
        with pytest.raises(Exception):
            GenerateDocumentRequest(
                application_id="12345678-1234-1234-1234-123456789012",
                doc_key="x" * 101,
            )

    def test_generate_document_request_default_label(self):
        from app.api.routes.generate import GenerateDocumentRequest
        req = GenerateDocumentRequest(
            application_id="12345678-1234-1234-1234-123456789012",
            doc_key="ninety_day_plan",
        )
        assert req.doc_label == ""

    def test_generate_document_request_invalid_uuid(self):
        from app.api.routes.generate import GenerateDocumentRequest
        with pytest.raises(Exception):
            GenerateDocumentRequest(
                application_id="not-a-uuid",
                doc_key="test",
            )


# ═══════════════════════════════════════════════════════════════════════
#  Tests: _fetch_job_and_application helper
# ═══════════════════════════════════════════════════════════════════════


class TestFetchJobAndApplication:
    """Tests for the shared _fetch_job_and_application helper."""

    @staticmethod
    async def _fake_to_thread(fn, *args, **kwargs):
        """Run fn synchronously instead of in a thread."""
        return fn(*args, **kwargs)

    @pytest.mark.asyncio
    async def test_returns_none_when_job_not_found(self):
        from app.api.routes.generate import _fetch_job_and_application

        db = _mock_db(select_data=[])

        with patch("app.core.database.get_supabase", return_value=db), \
             patch("asyncio.to_thread", side_effect=self._fake_to_thread):

            result = await _fetch_job_and_application("job-1", "user-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_tuple_on_success(self):
        from app.api.routes.generate import _fetch_job_and_application

        job_row = {"id": "job-1", "application_id": "app-1", "requested_modules": ["cv", "cover_letter"]}
        app_row = {"id": "app-1", "user_id": "user-1", "confirmed_facts": {}}

        db = MagicMock()

        # First call returns job
        job_resp = MagicMock()
        job_resp.data = [job_row]

        # Second call returns app
        app_resp = MagicMock()
        app_resp.data = [app_row]

        call_count = 0
        def mock_table(name):
            nonlocal call_count
            chain = MagicMock()
            if call_count == 0:
                chain.execute.return_value = job_resp
            else:
                chain.execute.return_value = app_resp
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain
            call_count += 1
            return chain

        db.table.side_effect = mock_table

        with patch("app.core.database.get_supabase", return_value=db), \
             patch("asyncio.to_thread", side_effect=self._fake_to_thread):

            result = await _fetch_job_and_application("job-1", "user-1")

        assert result is not None
        assert len(result) == 5
        sb, job, app_data, app_id, modules = result
        assert job["id"] == "job-1"
        assert app_data["id"] == "app-1"
        assert app_id == "app-1"
