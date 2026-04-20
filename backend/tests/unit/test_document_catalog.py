"""Tests for Document Catalog Service — CRUD, observations, seeding."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.document_catalog import (  # noqa: E402
    CORE_DOC_KEYS,
    SEED_BY_KEY,
    SEED_CATALOG,
    SEED_KEYS,
    _infer_category,
    get_catalog_id_map,
    get_catalog_keyset,
    get_full_catalog,
    observe_document_types,
)

# ── Helpers ────────────────────────────────────────────────────────────

TABLES = {
    "document_type_catalog": "document_type_catalog",
    "document_observations": "document_observations",
}


def _mock_db(select_data=None, rpc_ok=True):
    """Create a mock Supabase client."""
    db = MagicMock()

    # .table().select().order().execute() → resp.data
    resp = MagicMock()
    resp.data = select_data or []

    chain = MagicMock()
    chain.execute.return_value = resp
    chain.order.return_value = chain
    chain.select.return_value = chain
    chain.upsert.return_value = chain
    chain.insert.return_value = chain

    db.table.return_value = chain

    # .rpc().execute()
    rpc_chain = MagicMock()
    rpc_chain.execute.return_value = MagicMock()
    if not rpc_ok:
        rpc_chain.execute.side_effect = Exception("RPC failed")
    db.rpc.return_value = rpc_chain

    return db


# ═══════════════════════════════════════════════════════════════════════
#  Seed catalog integrity tests
# ═══════════════════════════════════════════════════════════════════════

class TestSeedCatalog:
    def test_seed_is_tuple(self):
        """SEED_CATALOG must be immutable."""
        assert isinstance(SEED_CATALOG, tuple)

    def test_seed_has_required_fields(self):
        for entry in SEED_CATALOG:
            assert "key" in entry
            assert "label" in entry
            assert "description" in entry
            assert "category" in entry
            assert "generatable" in entry

    def test_seed_keys_match_catalog(self):
        keys = {e["key"] for e in SEED_CATALOG}
        assert keys == SEED_KEYS

    def test_seed_by_key_lookup(self):
        assert SEED_BY_KEY["cv"]["label"] == "Tailored CV"
        assert SEED_BY_KEY["cover_letter"]["category"] == "core"

    def test_core_doc_keys(self):
        # Core docs are derived from SEED_CATALOG entries with category=="core".
        # This protects against silent drift: any change to SEED_CATALOG
        # categories must be reflected here, and we re-derive from the
        # catalog itself so the assertion is anchored to the source of truth.
        expected_core = {e["key"] for e in SEED_CATALOG if e["category"] == "core"}
        assert CORE_DOC_KEYS == expected_core
        # And the canonical core set as of this revision must include the
        # tailored four plus the resume variant. If a future change drops
        # one of these, this assertion forces an explicit decision.
        assert {"cv", "cover_letter", "personal_statement", "portfolio", "resume"} <= CORE_DOC_KEYS

    def test_no_duplicate_keys(self):
        keys = [e["key"] for e in SEED_CATALOG]
        assert len(keys) == len(set(keys)), "Duplicate keys in SEED_CATALOG"

    def test_all_entries_generatable(self):
        """All seed entries should be generatable (they come from DOCUMENT_TYPE_PROMPTS)."""
        for entry in SEED_CATALOG:
            assert entry["generatable"] is True, f"{entry['key']} should be generatable"


# ═══════════════════════════════════════════════════════════════════════
#  _infer_category tests
# ═══════════════════════════════════════════════════════════════════════

class TestInferCategory:
    def test_academic_keywords(self):
        assert _infer_category("research_methodology") == "academic"
        assert _infer_category("teaching_statement") == "academic"
        assert _infer_category("thesis_summary") == "academic"

    def test_compliance_keywords(self):
        assert _infer_category("selection_criteria_response") == "compliance"
        assert _infer_category("diversity_plan") == "compliance"
        assert _infer_category("safety_protocol") == "compliance"

    def test_technical_keywords(self):
        assert _infer_category("code_review") == "technical"
        assert _infer_category("technical_report") == "technical"

    def test_creative_keywords(self):
        assert _infer_category("design_brief") == "creative"
        assert _infer_category("media_release") == "creative"

    def test_executive_keywords(self):
        assert _infer_category("board_summary") == "executive"
        assert _infer_category("leadership_bio") == "executive"

    def test_default_professional(self):
        assert _infer_category("cover_note") == "professional"
        assert _infer_category("introduction") == "professional"


# ═══════════════════════════════════════════════════════════════════════
#  get_catalog_keyset tests
# ═══════════════════════════════════════════════════════════════════════

class TestGetCatalogKeyset:
    @pytest.mark.asyncio
    async def test_returns_keys_from_db(self):
        db = _mock_db(select_data=[{"key": "cv"}, {"key": "cover_letter"}, {"key": "custom_doc"}])
        result = await get_catalog_keyset(db, TABLES)
        assert result == {"cv", "cover_letter", "custom_doc"}

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self):
        db = MagicMock()
        db.table.side_effect = Exception("DB down")
        result = await get_catalog_keyset(db, TABLES)
        assert result == set(SEED_KEYS)

    @pytest.mark.asyncio
    async def test_filters_empty_keys(self):
        db = _mock_db(select_data=[{"key": "cv"}, {"key": ""}, {"key": None}])
        result = await get_catalog_keyset(db, TABLES)
        assert result == {"cv"}


# ═══════════════════════════════════════════════════════════════════════
#  get_catalog_id_map tests
# ═══════════════════════════════════════════════════════════════════════

class TestGetCatalogIdMap:
    @pytest.mark.asyncio
    async def test_returns_key_id_mapping(self):
        db = _mock_db(select_data=[
            {"id": "uuid-1", "key": "cv"},
            {"id": "uuid-2", "key": "cover_letter"},
        ])
        result = await get_catalog_id_map(db, TABLES)
        assert result == {"cv": "uuid-1", "cover_letter": "uuid-2"}

    @pytest.mark.asyncio
    async def test_empty_on_exception(self):
        db = MagicMock()
        db.table.side_effect = Exception("DB failure")
        result = await get_catalog_id_map(db, TABLES)
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════
#  get_full_catalog tests
# ═══════════════════════════════════════════════════════════════════════

class TestGetFullCatalog:
    @pytest.mark.asyncio
    async def test_returns_db_rows(self):
        rows = [
            {"key": "cv", "label": "CV", "seen_count": 100},
            {"key": "cover_letter", "label": "CL", "seen_count": 90},
        ]
        db = _mock_db(select_data=rows)
        result = await get_full_catalog(db, TABLES)
        assert result == rows

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self):
        db = MagicMock()
        db.table.side_effect = Exception("DB down")
        result = await get_full_catalog(db, TABLES)
        assert len(result) == len(SEED_CATALOG)
        assert all(r.get("seen_count") == 0 for r in result)


# ═══════════════════════════════════════════════════════════════════════
#  observe_document_types tests
# ═══════════════════════════════════════════════════════════════════════

class TestObserveDocumentTypes:
    @pytest.mark.asyncio
    async def test_empty_docs_noop(self):
        db = _mock_db()
        await observe_document_types(db, TABLES, [], user_id="u1")
        db.table.assert_not_called()
        db.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_known_key_increments_via_rpc(self):
        db = _mock_db(select_data=[
            {"id": "uuid-cv", "key": "cv"},
        ])
        docs = [{"key": "cv", "label": "CV", "reason": "always needed"}]
        await observe_document_types(db, TABLES, docs, user_id="u1", job_title="SWE")

        # Batch RPC called for known keys
        db.rpc.assert_called()
        rpc_args = db.rpc.call_args[0]
        assert rpc_args[0] == "increment_catalog_seen_count_batch"
        assert rpc_args[1] == {"p_keys": ["cv"]}

    @pytest.mark.asyncio
    async def test_unknown_key_inserts_new_entry(self):
        db = _mock_db(select_data=[
            {"id": "uuid-1", "key": "cv"},
        ])
        docs = [{"key": "blockchain_whitepaper", "label": "Blockchain Whitepaper", "reason": "Crypto role"}]
        await observe_document_types(
            db, TABLES, docs, user_id="u1",
            job_title="Blockchain Dev", industry="crypto",
        )

        # The upsert call should include the new entry
        upsert_calls = [
            c for c in db.table.return_value.upsert.call_args_list
        ]
        assert len(upsert_calls) > 0
        new_entry = upsert_calls[0][0][0][0]  # First positional arg → list → first item
        assert new_entry["key"] == "blockchain_whitepaper"
        assert new_entry["seen_count"] == 1
        assert new_entry["generatable"] is False  # Not in SEED_KEYS

    @pytest.mark.asyncio
    async def test_blank_key_skipped(self):
        db = _mock_db(select_data=[])
        docs = [{"key": "", "label": "Empty"}, {"key": "  ", "label": "Spaces"}]
        await observe_document_types(db, TABLES, docs, user_id="u1")
        # Should not crash, no RPC calls
        db.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_observations_batch_inserted(self):
        """Observation rows are inserted in a single batch."""
        db = _mock_db(select_data=[
            {"id": "uuid-cv", "key": "cv"},
            {"id": "uuid-cl", "key": "cover_letter"},
        ])
        docs = [
            {"key": "cv", "reason": "core"},
            {"key": "cover_letter", "reason": "core"},
        ]
        await observe_document_types(
            db, TABLES, docs, user_id="u1",
            job_title="SWE", industry="tech", job_level="senior",
        )

        # Check insert was called with batch of 2
        insert_calls = db.table.return_value.insert.call_args_list
        assert len(insert_calls) >= 1
        rows = insert_calls[-1][0][0]
        assert isinstance(rows, list)
        assert len(rows) == 2
        assert all(r.get("catalog_entry_id") for r in rows)

    @pytest.mark.asyncio
    async def test_source_context_includes_job_info(self):
        """New entries should have source_context with job title and level."""
        db = _mock_db(select_data=[])
        docs = [{"key": "new_doc_type", "label": "New Doc"}]
        await observe_document_types(
            db, TABLES, docs, user_id="u1",
            job_title="VP Engineering", industry="tech", job_level="executive",
        )

        upsert_calls = db.table.return_value.upsert.call_args_list
        if upsert_calls:
            entry = upsert_calls[0][0][0][0]
            assert "executive" in entry["source_context"]
            assert "VP Engineering" in entry["source_context"]
