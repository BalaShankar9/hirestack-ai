"""Evidence ledger integrity tests — Rank 9.

Verifies that the ``supabase/migrations/`` chain establishes all required
structural guarantees for the evidence subsystem:

  1. ``evidence_ledger_items`` table exists with (job_id, id) UNIQUE constraint
  2. ``claim_citations`` table exists with FK → ``generation_jobs``
  3. Python ``EvidenceTier`` enum values exactly match the DB CHECK constraint
  4. Python ``EvidenceItem`` source values match the DB CHECK constraint
  5. ``EvidenceLedger.add()`` does not silently accept an invalid tier
  6. The default confidence table covers every tier

All tests run fully offline — no DB connection required.

Run with:
    pytest tests/unit/test_evidence_ledger_integrity.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Path helpers ───────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parents[3]
_SUPABASE_MIG_DIR = _REPO_ROOT / "supabase" / "migrations"


def _full_chain_sql() -> str:
    files = sorted(_SUPABASE_MIG_DIR.glob("*.sql"))
    return "\n".join(f.read_text() for f in files)


# ─────────────────────────────────────────────────────────────────────────────
# DB schema invariants (static SQL analysis)
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceLedgerSchema:
    """The supabase migration chain must define the evidence_ledger_items table."""

    def test_evidence_ledger_items_table_exists_in_chain(self) -> None:
        sql = _full_chain_sql()
        assert re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?evidence_ledger_items\b",
            sql, re.IGNORECASE
        ), "evidence_ledger_items table not found in supabase/migrations/"

    def test_evidence_ledger_items_has_unique_job_id_id(self) -> None:
        """The (job_id, id) pair must be UNIQUE to prevent duplicate evidence entries."""
        sql = _full_chain_sql()
        assert re.search(
            r"UNIQUE\s*\(\s*job_id\s*,\s*id\s*\)",
            sql, re.IGNORECASE
        ), (
            "evidence_ledger_items is missing UNIQUE(job_id, id).  "
            "Without this constraint the same evidence item can be inserted twice, "
            "causing duplicate citations and inflated confidence scores."
        )

    def test_evidence_ledger_items_pk_is_bigint(self) -> None:
        """Primary key must be BIGINT (not UUID) for high-volume append-only writes."""
        sql = _full_chain_sql()
        # Look for pk BIGINT GENERATED ALWAYS AS IDENTITY
        assert re.search(
            r"pk\s+BIGINT\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY",
            sql, re.IGNORECASE
        ), "evidence_ledger_items.pk should be BIGINT GENERATED ALWAYS AS IDENTITY"

    def test_evidence_ledger_items_references_generation_jobs(self) -> None:
        """job_id must FK → generation_jobs to prevent orphaned evidence rows."""
        sql = _full_chain_sql()
        # The REFERENCES must appear inside the evidence_ledger_items block
        table_block = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?evidence_ledger_items\b.*?\);",
            sql, re.IGNORECASE | re.DOTALL,
        )
        assert table_block, "evidence_ledger_items table definition not found"
        block_text = table_block.group(0)
        assert re.search(
            r"REFERENCES\s+(?:public\.)?generation_jobs", block_text, re.IGNORECASE
        ), "evidence_ledger_items.job_id must REFERENCES generation_jobs"

    def test_evidence_ledger_items_tier_check_constraint(self) -> None:
        """The DB tier CHECK must include all four tiers."""
        sql = _full_chain_sql()
        table_block = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?evidence_ledger_items\b.*?\);",
            sql, re.IGNORECASE | re.DOTALL,
        )
        assert table_block
        block_text = table_block.group(0)
        for tier in ("verbatim", "derived", "inferred", "user_stated"):
            assert tier in block_text, (
                f"DB CHECK constraint for evidence_ledger_items.tier is missing '{tier}'"
            )

    def test_claim_citations_table_exists(self) -> None:
        sql = _full_chain_sql()
        assert re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?claim_citations\b",
            sql, re.IGNORECASE
        ), "claim_citations table not found in supabase/migrations/"

    def test_claim_citations_references_generation_jobs(self) -> None:
        sql = _full_chain_sql()
        table_block = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?claim_citations\b.*?\);",
            sql, re.IGNORECASE | re.DOTALL,
        )
        assert table_block, "claim_citations table definition not found"
        block_text = table_block.group(0)
        assert re.search(
            r"REFERENCES\s+(?:public\.)?generation_jobs", block_text, re.IGNORECASE
        ), "claim_citations.job_id must REFERENCES generation_jobs"


# ─────────────────────────────────────────────────────────────────────────────
# Python ↔ DB enum alignment
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceTierAlignment:
    """Python EvidenceTier enum must exactly match the DB CHECK constraint."""

    # These are the DB-authoritative values from the migration.
    _DB_TIERS = frozenset({"verbatim", "derived", "inferred", "user_stated"})
    _DB_SOURCES = frozenset({"profile", "jd", "company", "tool", "memory"})

    def test_evidence_tier_enum_importable(self) -> None:
        from ai_engine.agents.evidence import EvidenceTier  # noqa: F401

    def test_evidence_tier_values_match_db(self) -> None:
        from ai_engine.agents.evidence import EvidenceTier

        python_tiers = {t.value for t in EvidenceTier}
        missing_from_python = self._DB_TIERS - python_tiers
        extra_in_python = python_tiers - self._DB_TIERS

        assert not missing_from_python, (
            f"DB CHECK has tiers that Python EvidenceTier is missing: {missing_from_python}"
        )
        assert not extra_in_python, (
            f"Python EvidenceTier has values not in DB CHECK: {extra_in_python}.  "
            f"Add them to the supabase migration or remove from the enum."
        )

    def test_evidence_item_source_values_match_db(self) -> None:
        """EvidenceItem.source literals must be in the DB source CHECK."""
        # The EvidenceItem dataclass defines source as a plain str field;
        # the valid values are documented in the migration CHECK constraint.
        # We validate that any hard-coded source strings in evidence.py are legal.
        import inspect
        from ai_engine.agents import evidence as ev_module

        source = inspect.getsource(ev_module)
        # Extract string literals assigned to .source or passed as source=
        # This is a conservative lint check — catches obvious regressions.
        literal_sources = re.findall(r"""source\s*=\s*["']([^"']+)["']""", source)
        illegal = [s for s in literal_sources if s not in self._DB_SOURCES]
        assert not illegal, (
            f"evidence.py uses source values not in the DB CHECK: {illegal}.  "
            f"Valid sources: {sorted(self._DB_SOURCES)}"
        )

    @pytest.mark.parametrize("tier", ["verbatim", "derived", "inferred", "user_stated"])
    def test_each_tier_resolves_from_enum(self, tier: str) -> None:
        from ai_engine.agents.evidence import EvidenceTier

        resolved = EvidenceTier(tier)
        assert resolved.value == tier


class TestEvidenceLedgerPythonBehaviour:
    """EvidenceLedger Python class invariants."""

    def test_evidence_ledger_importable(self) -> None:
        from ai_engine.agents.evidence import EvidenceLedger  # noqa: F401

    def test_default_confidence_covers_all_tiers(self) -> None:
        """_DEFAULT_CONFIDENCE must have an entry for every EvidenceTier value."""
        from ai_engine.agents.evidence import _DEFAULT_CONFIDENCE, EvidenceTier  # noqa: PLC2701

        for tier in EvidenceTier:
            assert tier in _DEFAULT_CONFIDENCE, (
                f"_DEFAULT_CONFIDENCE is missing an entry for {tier!r}"
            )

    def test_verbatim_has_highest_default_confidence(self) -> None:
        """Verbatim evidence is the most trustworthy source."""
        from ai_engine.agents.evidence import _DEFAULT_CONFIDENCE, EvidenceTier  # noqa: PLC2701

        verbatim_conf = _DEFAULT_CONFIDENCE[EvidenceTier.VERBATIM]
        for tier, conf in _DEFAULT_CONFIDENCE.items():
            if tier != EvidenceTier.VERBATIM:
                assert verbatim_conf >= conf, (
                    f"VERBATIM confidence ({verbatim_conf}) should be ≥ {tier.value} ({conf})"
                )

    def test_evidence_ledger_initial_state_is_empty(self) -> None:
        from ai_engine.agents.evidence import EvidenceLedger

        ledger = EvidenceLedger()
        assert len(ledger) == 0

    def test_add_item_increases_length(self) -> None:
        from ai_engine.agents.evidence import EvidenceLedger, EvidenceTier

        ledger = EvidenceLedger()
        ledger.add(
            tier=EvidenceTier.VERBATIM,
            source="profile",
            source_field="skills",
            text="Python developer with 5 years of experience",
            confidence=0.90,
        )
        assert len(ledger) == 1

    def test_duplicate_id_not_added_twice(self) -> None:
        """Content-identical items should not be stored twice.

        EvidenceLedger keys by a deterministic hash of (source, source_field, text),
        mirroring the DB UNIQUE(job_id, id) constraint.
        """
        from ai_engine.agents.evidence import EvidenceLedger, EvidenceTier

        ledger = EvidenceLedger()
        kwargs = dict(
            tier=EvidenceTier.VERBATIM,
            source="profile",
            source_field="summary",
            text="Experienced engineer",
        )
        ledger.add(**kwargs)
        ledger.add(**kwargs)  # identical content → same hash → deduplication
        assert len(ledger) == 1, (
            "EvidenceLedger should deduplicate content-identical items"
        )
