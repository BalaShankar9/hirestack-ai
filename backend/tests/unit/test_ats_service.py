"""S7-F4: pin app/services/ats.py contracts.

Behavioural lock for ATSService — column membership, fallback path
when extended columns missing, and the contract that DB failures
NEVER swallow the AI scan result.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import ats as ats_module
from app.services.ats import (
    _BASE_COLUMNS,
    _EXTENDED_COLUMNS,
    ATSService,
)


# ── Column constants ──────────────────────────────────────────────


class TestColumnSets:
    def test_base_columns_pinned(self):
        assert _BASE_COLUMNS == {
            "user_id",
            "document_content",
            "status",
            "created_at",
            "updated_at",
        }

    def test_extended_columns_pinned(self):
        # Exact set membership is API contract — adding a new field
        # without a migration would cause silent data loss in the
        # fallback path. This test forces a deliberate update.
        assert _EXTENDED_COLUMNS == {
            "application_id",
            "document_id",
            "job_description_id",
            "ats_score",
            "keyword_match_rate",
            "readability_score",
            "format_score",
            "section_scores",
            "matched_keywords",
            "missing_keywords",
            "formatting_issues",
            "recommendations",
            "pass_prediction",
            "recruiter_view_html",
        }

    def test_base_and_extended_disjoint(self):
        assert _BASE_COLUMNS.isdisjoint(_EXTENDED_COLUMNS)


# ── Helpers ───────────────────────────────────────────────────────


def _make_scan_result() -> dict[str, Any]:
    """A canonical successful AIClient/ATSScannerChain output."""
    return {
        "ats_score": 87,
        "keyword_match_rate": 0.66,
        "score_breakdown": {"structure_score": 80, "strategy_score": 75},
        "structure": {"parsing_issues": ["bad_table"]},
        "keywords": {"present": ["python"], "missing": ["rust"]},
        "strategy": {"rewrite_suggestions": ["use bullets"]},
        "pass_probability": "high",
    }


@pytest.fixture(autouse=True)
def _reset_extended_cache():
    """Reset the module-level cache between tests."""
    ats_module._extended_available = None
    yield
    ats_module._extended_available = None


@pytest.fixture
def service():
    db = MagicMock()
    db.create = AsyncMock(return_value="row-id-42")
    db.client = MagicMock()
    svc = ATSService(db=db)
    # Patch the AI client at the chain layer so no LLM calls happen.
    return svc


# ── _has_extended_columns caching ─────────────────────────────────


class TestHasExtendedColumns:
    @pytest.mark.asyncio
    async def test_returns_true_when_select_succeeds(self, service):
        # Default db.client.table().select().limit().execute() chain
        # returns a MagicMock (does not raise) → True.
        out = await service._has_extended_columns()
        assert out is True

    @pytest.mark.asyncio
    async def test_returns_false_when_select_raises(self, service):
        service.db.client.table.side_effect = RuntimeError("missing column")
        out = await service._has_extended_columns()
        assert out is False

    @pytest.mark.asyncio
    async def test_result_is_cached_module_wide(self, service):
        # First call probes the table; subsequent calls reuse cache.
        await service._has_extended_columns()
        assert ats_module._extended_available is True

        # Even if we make the next probe raise, the cached value
        # must be returned without a second probe.
        service.db.client.table.side_effect = RuntimeError("would raise")
        out = await service._has_extended_columns()
        assert out is True

    @pytest.mark.asyncio
    async def test_cache_shared_across_instances(self, service):
        await service._has_extended_columns()
        # New instance, new MagicMock — but cached True must persist.
        new_svc = ATSService(db=MagicMock())
        out = await new_svc._has_extended_columns()
        assert out is True


# ── scan_document: extended-column happy path ─────────────────────


class TestScanDocumentExtended:
    @pytest.mark.asyncio
    async def test_extended_record_includes_all_keys(self, service):
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=_make_scan_result()),
        ):
            await service.scan_document(
                user_id="u1",
                document_content="resume body",
                jd_text="job desc",
                document_id="doc-9",
                job_id="job-3",
            )

        # First create call gets the FULL extended record.
        record = service.db.create.await_args.args[1]
        assert record["user_id"] == "u1"
        assert record["status"] == "completed"
        assert record["ats_score"] == 87
        assert record["keyword_match_rate"] == pytest.approx(0.66)
        # readability_score MUST come from structure_score (NOT a
        # separate field — pinned mapping).
        assert record["readability_score"] == 80
        # format_score MUST come from strategy_score.
        assert record["format_score"] == 75
        assert record["matched_keywords"] == ["python"]
        assert record["missing_keywords"] == ["rust"]
        assert record["formatting_issues"] == ["bad_table"]
        assert record["recommendations"] == ["use bullets"]
        assert record["pass_prediction"] == "high"
        assert record["document_id"] == "doc-9"
        assert record["job_description_id"] == "job-3"

    @pytest.mark.asyncio
    async def test_document_content_truncated_to_2000_chars(self, service):
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=_make_scan_result()),
        ):
            await service.scan_document(
                user_id="u1",
                document_content="x" * 5000,
                jd_text="jd",
            )
        record = service.db.create.await_args.args[1]
        assert len(record["document_content"]) == 2000

    @pytest.mark.asyncio
    async def test_optional_ids_omitted_when_none(self, service):
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=_make_scan_result()),
        ):
            await service.scan_document(
                user_id="u1",
                document_content="r",
                jd_text="j",
            )
        record = service.db.create.await_args.args[1]
        assert "document_id" not in record
        assert "job_description_id" not in record

    @pytest.mark.asyncio
    async def test_int_and_float_coercion(self, service):
        # Even if AI returns strings or floats, the record must
        # coerce to int/float as pinned.
        result = _make_scan_result()
        result["ats_score"] = 87.9      # float → int
        result["keyword_match_rate"] = 1  # int → float
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=result),
        ):
            await service.scan_document("u", "r", "j")
        record = service.db.create.await_args.args[1]
        assert isinstance(record["ats_score"], int)
        assert record["ats_score"] == 87
        assert isinstance(record["keyword_match_rate"], float)


# ── scan_document: missing-keys defaults ──────────────────────────


class TestScanDocumentDefaults:
    @pytest.mark.asyncio
    async def test_empty_scan_result_uses_zero_defaults(self, service):
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value={}),
        ):
            await service.scan_document("u", "r", "j")
        record = service.db.create.await_args.args[1]
        assert record["ats_score"] == 0
        assert record["keyword_match_rate"] == 0.0
        assert record["readability_score"] == 0
        assert record["format_score"] == 0
        assert record["matched_keywords"] == []
        assert record["missing_keywords"] == []
        assert record["formatting_issues"] == []
        assert record["recommendations"] == []
        assert record["pass_prediction"] == "unknown"


# ── scan_document: extended-columns NOT available ─────────────────


class TestScanDocumentBaseOnly:
    @pytest.mark.asyncio
    async def test_extended_keys_omitted_when_no_extended_cols(self, service):
        # Force the cache to False before scan.
        service.db.client.table.side_effect = RuntimeError("schema missing")
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=_make_scan_result()),
        ):
            await service.scan_document("u", "r", "j", document_id="d", job_id="j")
        record = service.db.create.await_args.args[1]
        # Only base keys present.
        for k in (
            "ats_score",
            "keyword_match_rate",
            "readability_score",
            "format_score",
            "document_id",
            "job_description_id",
        ):
            assert k not in record
        assert set(record.keys()) <= {"user_id", "document_content", "status"}


# ── scan_document: fallback when extended insert raises ───────────


class TestScanDocumentFallback:
    @pytest.mark.asyncio
    async def test_first_create_raises_then_base_only_retry(self, service):
        # Two-call pattern: first create raises, second succeeds.
        service.db.create = AsyncMock(
            side_effect=[RuntimeError("unknown column ats_score"), "row-base-1"]
        )
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=_make_scan_result()),
        ):
            out = await service.scan_document("u1", "r", "j")

        # Two create calls.
        assert service.db.create.await_count == 2
        # Second call's record only contains _BASE_COLUMNS keys.
        second_record = service.db.create.await_args_list[1].args[1]
        assert set(second_record.keys()) <= _BASE_COLUMNS
        # Returned id comes from the successful retry.
        assert out["id"] == "row-base-1"
        # Status still completed; AI scan result still present.
        assert out["status"] == "completed"
        assert out["ats_score"] == 87

    @pytest.mark.asyncio
    async def test_both_creates_fail_returns_id_none_with_scan(self, service):
        service.db.create = AsyncMock(
            side_effect=[RuntimeError("first"), RuntimeError("second")]
        )
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=_make_scan_result()),
        ):
            out = await service.scan_document("u", "r", "j")

        # CRITICAL contract: id is None but result is preserved.
        assert out["id"] is None
        assert out["status"] == "completed"
        assert out["ats_score"] == 87
        assert out["keyword_match_rate"] == pytest.approx(0.66)


# ── Return shape ──────────────────────────────────────────────────


class TestReturnShape:
    @pytest.mark.asyncio
    async def test_return_includes_id_status_and_scan_result(self, service):
        with patch(
            "app.services.ats.ATSScannerChain.scan_document",
            new=AsyncMock(return_value=_make_scan_result()),
        ):
            out = await service.scan_document("u", "r", "j")
        assert out["id"] == "row-id-42"
        assert out["status"] == "completed"
        # scan_result fields are spread into the return dict.
        assert out["ats_score"] == 87
        assert out["pass_probability"] == "high"
        assert out["score_breakdown"] == {"structure_score": 80, "strategy_score": 75}
