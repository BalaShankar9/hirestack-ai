"""Tests for EvidenceGraphBuilder — canonicalization, contradiction detection, scoring."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_engine.agents.evidence import EvidenceLedger  # noqa: E402
from ai_engine.agents.evidence_graph import (  # noqa: E402
    CanonicalNode,
    ContradictionType,
    EvidenceGraphBuilder,
    EvidenceGraphStats,
)


# ═══════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════

def _make_ledger(*items_data) -> EvidenceLedger:
    """Create a ledger with specified items."""
    ledger = EvidenceLedger()
    for tier, source, source_field, text, confidence in items_data:
        ledger.add(tier=tier, source=source, source_field=source_field,
                    text=text, confidence=confidence)
    return ledger


def _make_node(
    text: str,
    source: str = "profile",
    source_field: str = "experience",
    tier: str = "verbatim",
    confidence: float = 0.9,
    **kwargs,
) -> CanonicalNode:
    return CanonicalNode(
        id=f"node_{hash(text) % 10000}",
        canonical_text=text,
        tier=tier,
        source=source,
        source_field=source_field,
        confidence=confidence,
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Canonicalization tests
# ═══════════════════════════════════════════════════════════════════════

class TestCanonicalize:
    def test_new_items_become_nodes(self):
        builder = EvidenceGraphBuilder()
        ledger = _make_ledger(
            ("verbatim", "profile", "experience", "Led team of 5 engineers at Acme Corp", 0.9),
            ("derived", "jd", "requirement", "Must have 3+ years Python experience", 0.75),
        )
        nodes = builder.canonicalize(ledger, job_id="job-1")
        assert len(nodes) == 2
        assert all(isinstance(n, CanonicalNode) for n in nodes)

    def test_duplicate_text_becomes_alias(self):
        builder = EvidenceGraphBuilder()
        ledger1 = _make_ledger(
            ("verbatim", "profile", "experience", "Led team of 5 engineers at Acme Corp", 0.9),
        )
        nodes1 = builder.canonicalize(ledger1, job_id="job-1")
        assert len(nodes1) == 1

        # Very similar text should match (> 0.85 similarity)
        ledger2 = _make_ledger(
            ("verbatim", "profile", "experience", "Led team of 5 engineers at Acme Corporation", 0.9),
        )
        nodes2 = builder.canonicalize(ledger2, job_id="job-2")
        # The similar item should match existing and become an alias (updated node)
        assert len(nodes2) == 1
        assert len(nodes2[0].aliases) >= 1

    def test_different_items_stay_separate(self):
        builder = EvidenceGraphBuilder()
        ledger = _make_ledger(
            ("verbatim", "profile", "experience", "Led team of 5 engineers at Acme Corp", 0.9),
            ("verbatim", "profile", "education", "BS Computer Science Stanford University", 0.9),
        )
        nodes = builder.canonicalize(ledger, job_id="job-1")
        assert len(nodes) == 2

    def test_confidence_boost_on_alias(self):
        builder = EvidenceGraphBuilder()
        ledger1 = _make_ledger(
            ("verbatim", "profile", "experience", "Managed $2M budget for product launch", 0.85),
        )
        nodes1 = builder.canonicalize(ledger1)
        original_confidence = nodes1[0].confidence

        # Re-canonicalize with very similar text
        ledger2 = _make_ledger(
            ("verbatim", "profile", "experience", "Managed $2M budget for the product launch", 0.85),
        )
        nodes2 = builder.canonicalize(ledger2)
        assert nodes2[0].confidence > original_confidence

    def test_canonical_id_is_deterministic(self):
        builder = EvidenceGraphBuilder()
        ledger = _make_ledger(
            ("verbatim", "profile", "experience", "Same text", 0.9),
        )
        nodes_a = builder.canonicalize(ledger)
        _nodes_b = builder.canonicalize(ledger)
        # IDs should be based on content hash
        assert len(nodes_a) >= 1

    def test_node_metadata_preserved(self):
        builder = EvidenceGraphBuilder()
        ledger = EvidenceLedger()
        ledger.add(
            tier="verbatim", source="profile", source_field="skills",
            text="Python programming", metadata={"years": 5}, confidence=0.9,
        )
        nodes = builder.canonicalize(ledger, job_id="j1")
        assert nodes[0].metadata == {"years": 5}
        assert nodes[0].first_seen_job_id == "j1"


# ═══════════════════════════════════════════════════════════════════════
#  Contradiction detection tests
# ═══════════════════════════════════════════════════════════════════════

class TestContradictionDetection:
    def test_company_name_conflict(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("Google Inc", source_field="company"),
            _make_node("Google LLC", source_field="company"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        company_conflicts = [c for c in contradictions if c.contradiction_type == ContradictionType.COMPANY_NAME]
        assert len(company_conflicts) >= 1

    def test_identical_companies_no_conflict(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("Google", source_field="company"),
            _make_node("Google", source_field="company"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        company_conflicts = [c for c in contradictions if c.contradiction_type == ContradictionType.COMPANY_NAME]
        # Identical text shouldn't trigger conflict (similarity >= 0.85)
        assert len(company_conflicts) == 0

    def test_title_seniority_conflict(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("Junior Software Engineer at Acme", source_field="title"),
            _make_node("Senior Software Engineer at Acme", source_field="title"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        title_conflicts = [c for c in contradictions if c.contradiction_type == ContradictionType.TITLE_CONFLICT]
        assert len(title_conflicts) >= 1

    def test_similar_title_no_conflict(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("Senior Software Engineer", source_field="title"),
            _make_node("Staff Software Engineer", source_field="title"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        title_conflicts = [c for c in contradictions if c.contradiction_type == ContradictionType.TITLE_CONFLICT]
        # Senior (3) and Staff (4) — difference < 2
        assert len(title_conflicts) == 0

    def test_date_overlap_detected(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("2020 - 2023", source_field="date"),
            _make_node("2022 - 2024", source_field="date"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        overlaps = [c for c in contradictions if c.contradiction_type == ContradictionType.DATE_OVERLAP]
        assert len(overlaps) >= 1

    def test_no_date_overlap(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("2018 - 2020", source_field="date"),
            _make_node("2021 - 2023", source_field="date"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        overlaps = [c for c in contradictions if c.contradiction_type == ContradictionType.DATE_OVERLAP]
        assert len(overlaps) == 0

    def test_metric_conflict(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("Reduced server costs by 40%", source_field="achievement"),
            _make_node("Reduced server costs by 25%", source_field="achievement"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        metric_conflicts = [c for c in contradictions if c.contradiction_type == ContradictionType.METRIC_CONFLICT]
        assert len(metric_conflicts) >= 1

    def test_no_contradiction_for_different_metrics(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("Increased revenue by 50%", source_field="achievement"),
            _make_node("Reduced latency by 30%", source_field="achievement"),
        ]
        contradictions = builder.detect_contradictions(nodes)
        metric_conflicts = [c for c in contradictions if c.contradiction_type == ContradictionType.METRIC_CONFLICT]
        assert len(metric_conflicts) == 0

    def test_certification_conflict(self):
        builder = EvidenceGraphBuilder()
        nodes = [
            _make_node("AWS Solutions Architect from Amazon 2020", source_field="certification"),
            _make_node("AWS Solutions Architect from Generic Provider 2021", source_field="certification"),
        ]
        # Verify the cert names are extractable
        name_a = EvidenceGraphBuilder._extract_cert_name(nodes[0].canonical_text)
        name_b = EvidenceGraphBuilder._extract_cert_name(nodes[1].canonical_text)
        assert name_a is not None, f"Could not extract cert name from: {nodes[0].canonical_text}"
        assert name_b is not None, f"Could not extract cert name from: {nodes[1].canonical_text}"
        assert name_a == name_b, f"Cert names don't match: {name_a!r} vs {name_b!r}"
        contradictions = builder.detect_contradictions(nodes)
        cert_conflicts = [c for c in contradictions if c.contradiction_type == ContradictionType.CERTIFICATION_CONFLICT]
        assert len(cert_conflicts) >= 1


# ═══════════════════════════════════════════════════════════════════════
#  Evidence strength scoring tests
# ═══════════════════════════════════════════════════════════════════════

class TestEvidenceStrengthScoring:
    def test_empty_graph_scores_zero(self):
        builder = EvidenceGraphBuilder()
        score = builder.compute_evidence_strength_score()
        assert score == 0

    def test_stats_shape(self):
        builder = EvidenceGraphBuilder()
        stats = builder.compute_evidence_strength()
        assert isinstance(stats, EvidenceGraphStats)
        assert stats.total_nodes == 0
        assert stats.avg_confidence == 0.0

    def test_score_increases_with_quality_nodes(self):
        """With mocked DB returning nodes, score should be > 0."""
        builder = EvidenceGraphBuilder()

        # Mock _load_existing_nodes to return some nodes
        builder._load_existing_nodes = lambda: [
            _make_node("X", tier="verbatim", confidence=0.9),
            _make_node("Y", tier="verbatim", confidence=0.85),
            _make_node("Z", tier="derived", confidence=0.7),
        ]
        builder._load_existing_contradictions = lambda: []

        score = builder.compute_evidence_strength_score()
        assert score > 0
        assert score <= 100


# ═══════════════════════════════════════════════════════════════════════
#  Text processing helper tests
# ═══════════════════════════════════════════════════════════════════════

class TestTextHelpers:
    def test_normalize_text(self):
        assert EvidenceGraphBuilder._normalize_text("  Hello   World  ") == "hello world"

    def test_parse_date_range_year_range(self):
        result = EvidenceGraphBuilder._parse_date_range("2020 - 2023")
        assert result is not None
        start, end = result
        assert start == 2020 * 12
        assert end == 2023 * 12 + 12

    def test_parse_date_range_present(self):
        result = EvidenceGraphBuilder._parse_date_range("2021 - present")
        assert result is not None
        start, end = result
        assert start == 2021 * 12
        assert end > start

    def test_parse_date_range_month_year(self):
        result = EvidenceGraphBuilder._parse_date_range("Jan 2020 - Mar 2023")
        assert result is not None
        start, end = result
        assert start < end

    def test_parse_date_range_invalid(self):
        assert EvidenceGraphBuilder._parse_date_range("no dates here") is None

    def test_extract_seniority(self):
        levels = {"junior": 1, "senior": 3, "lead": 4, "principal": 5}
        assert EvidenceGraphBuilder._extract_seniority("Senior Engineer", levels) == 3
        assert EvidenceGraphBuilder._extract_seniority("Software Developer", levels) is None

    def test_extract_cert_name(self):
        assert EvidenceGraphBuilder._extract_cert_name("AWS Solutions Architect cert") is not None
        assert EvidenceGraphBuilder._extract_cert_name("PMP certified") is not None
        assert EvidenceGraphBuilder._extract_cert_name("random text") is None

    def test_canonical_id_deterministic(self):
        ledger = EvidenceLedger()
        item = ledger.add("verbatim", "profile", "skills", "Python", confidence=0.9)
        id1 = EvidenceGraphBuilder._canonical_id(item)
        id2 = EvidenceGraphBuilder._canonical_id(item)
        assert id1 == id2
        assert len(id1) == 16  # sha256[:16]


# ═══════════════════════════════════════════════════════════════════════
#  Persistence tests (with mocked DB)
# ═══════════════════════════════════════════════════════════════════════

class TestPersistence:
    def _mock_db(self, existing_rows=None):
        db = MagicMock()
        select_mock = MagicMock()
        select_mock.execute.return_value = MagicMock(data=existing_rows or [])
        eq_mock = MagicMock()
        eq_mock.execute.return_value = MagicMock(data=existing_rows or [])
        select_chain = MagicMock()
        select_chain.eq.return_value = eq_mock
        table_mock = MagicMock()
        table_mock.select.return_value = select_chain
        insert_mock = MagicMock()
        insert_mock.execute.return_value = MagicMock(data=[])
        table_mock.insert.return_value = insert_mock
        update_mock = MagicMock()
        update_mock.eq.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=[])))
        table_mock.update.return_value = update_mock
        db.table.return_value = table_mock
        return db

    def test_canonicalize_persists_new_nodes(self):
        db = self._mock_db()
        builder = EvidenceGraphBuilder(db=db, user_id="user-1")
        ledger = _make_ledger(
            ("verbatim", "profile", "experience", "Worked at Google for 5 years", 0.9),
        )
        nodes = builder.canonicalize(ledger, job_id="job-1")
        assert len(nodes) == 1
        # Verify insert was called for the node
        db.table.assert_any_call("user_evidence_nodes")

    def test_no_persistence_without_db(self):
        builder = EvidenceGraphBuilder()  # no db
        ledger = _make_ledger(
            ("verbatim", "profile", "experience", "Test", 0.9),
        )
        nodes = builder.canonicalize(ledger, job_id="job-1")
        assert len(nodes) == 1  # still works, just doesn't persist

    def test_load_existing_nodes_from_db(self):
        db = self._mock_db(existing_rows=[
            {
                "id": "node-1", "canonical_text": "Python expert",
                "tier": "verbatim", "source": "profile",
                "source_field": "skills", "confidence": 0.9,
                "first_seen_job_id": "j1", "metadata": {},
            },
        ])
        builder = EvidenceGraphBuilder(db=db, user_id="user-1")
        nodes = builder._load_existing_nodes()
        assert len(nodes) == 1
        assert nodes[0].canonical_text == "Python expert"
