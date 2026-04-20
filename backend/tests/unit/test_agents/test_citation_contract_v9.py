"""Deterministic citation contract tests (v9).

The fact-checker emits source markers like ``"skill:python"``.  Profile
items added via populate_from_profile are tagged with matching pool
metadata.  Citation rebuilding must resolve markers to evidence_ids
deterministically (exact pool+value match) instead of fuzzy text search.

These tests pin that contract so a future refactor can't silently
regress to text-only matching.
"""
from __future__ import annotations

from ai_engine.agents.evidence import (
    EvidenceLedger,
    EvidenceSource,
    EvidenceTier,
    populate_from_profile,
)


class TestPoolIndex:
    def test_skill_lookup_resolves_via_pool_metadata(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {"skills": ["Python", "Rust"]})
        hits = ledger.find_by_pool_value("skill", "python")
        assert len(hits) == 1
        assert hits[0].text == "Python"
        assert hits[0].metadata["pool"] == "skill"
        assert hits[0].metadata["value"] == "python"

    def test_company_lookup(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {
            "experience": [{"title": "SWE", "company": "Acme Corp"}],
        })
        hits = ledger.find_by_pool_value("company", "acme corp")
        assert len(hits) == 1
        assert hits[0].text == "Acme Corp"

    def test_title_lookup(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {
            "experience": [{"title": "Staff Engineer", "company": "X"}],
        })
        hits = ledger.find_by_pool_value("title", "staff engineer")
        assert len(hits) == 1

    def test_cert_lookup(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {"certifications": ["AWS SAA"]})
        hits = ledger.find_by_pool_value("cert", "aws saa")
        assert len(hits) == 1

    def test_education_lookup(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {
            "education": [{"degree": "BSc", "institution": "MIT", "field": "CS"}],
        })
        # Each education field is its own evidence item
        assert len(ledger.find_by_pool_value("education", "bsc")) == 1
        assert len(ledger.find_by_pool_value("education", "mit")) == 1
        assert len(ledger.find_by_pool_value("education", "cs")) == 1

    def test_pool_lookup_is_case_insensitive(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {"skills": ["TypeScript"]})
        # Caller passes mixed case; lookup normalizes
        assert len(ledger.find_by_pool_value("SKILL", "TypeScript")) == 1
        assert len(ledger.find_by_pool_value("skill", "typescript")) == 1
        assert len(ledger.find_by_pool_value("skill", "  typescript  ")) == 1

    def test_returns_empty_on_unknown_pool(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {"skills": ["Python"]})
        assert ledger.find_by_pool_value("nonsense", "python") == []
        assert ledger.find_by_pool_value("skill", "rust") == []

    def test_empty_args_return_empty(self):
        ledger = EvidenceLedger()
        populate_from_profile(ledger, {"skills": ["Python"]})
        assert ledger.find_by_pool_value("", "python") == []
        assert ledger.find_by_pool_value("skill", "") == []

    def test_externally_added_items_without_pool_metadata_excluded(self):
        # Items added without pool tagging should NOT appear in pool lookup
        ledger = EvidenceLedger()
        ledger.add(
            tier=EvidenceTier.VERBATIM,
            source=EvidenceSource.TOOL,
            source_field="test",
            text="some text mentioning python",
        )
        # find_by_text would match; find_by_pool_value must not
        assert len(ledger.find_by_text("python")) == 1
        assert ledger.find_by_pool_value("skill", "python") == []
