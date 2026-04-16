"""
Evidence Graph — user-scoped canonical evidence with contradiction detection.

Promotes job-scoped EvidenceLedger items into user-level canonical evidence
nodes, detects contradictions across jobs, and provides the evidence strength
scoring the adaptive planner needs.

Architecture:
  EvidenceLedger (job-scoped, in-memory)
    → EvidenceGraphBuilder.canonicalize()
    → user_evidence_nodes (cross-job, DB-persisted)
    → EvidenceGraphBuilder.detect_contradictions()
    → evidence_contradictions (DB-persisted)
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

from ai_engine.agents.evidence import EvidenceItem, EvidenceLedger, EvidenceTier

logger = structlog.get_logger("hirestack.evidence_graph")


# ═══════════════════════════════════════════════════════════════════════
#  Contradiction types
# ═══════════════════════════════════════════════════════════════════════

class ContradictionType(str, Enum):
    COMPANY_NAME = "company_name"           # Same company, different names
    TITLE_CONFLICT = "title_conflict"       # Conflicting seniority/role
    DATE_OVERLAP = "date_overlap"           # Overlapping employment periods
    CERTIFICATION_CONFLICT = "certification_conflict"  # Different institutions for same cert
    METRIC_CONFLICT = "metric_conflict"     # Conflicting impact numbers


@dataclass
class CanonicalNode:
    """A canonical evidence node that spans all of a user's jobs."""
    id: str
    canonical_text: str
    tier: str
    source: str
    source_field: str
    confidence: float
    first_seen_job_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)


@dataclass
class Contradiction:
    """A detected contradiction between two canonical nodes."""
    node_a: CanonicalNode
    node_b: CanonicalNode
    contradiction_type: ContradictionType
    severity: str  # low, medium, high, critical
    description: str


@dataclass
class EvidenceGraphStats:
    """Summary stats for evidence graph scoring."""
    total_nodes: int = 0
    verbatim_count: int = 0
    derived_count: int = 0
    inferred_count: int = 0
    user_stated_count: int = 0
    avg_confidence: float = 0.0
    contradiction_count: int = 0
    unresolved_contradictions: int = 0


# ═══════════════════════════════════════════════════════════════════════
#  Graph builder
# ═══════════════════════════════════════════════════════════════════════

class EvidenceGraphBuilder:
    """Promotes job evidence into canonical user-level nodes and detects conflicts."""

    SIMILARITY_THRESHOLD = 0.85  # Text similarity for alias detection

    def __init__(self, db: Any = None, user_id: str = "") -> None:
        self._db = db
        self._user_id = user_id
        self._in_memory_nodes: List[CanonicalNode] = []  # local cache across calls

    # ── Canonicalization ──────────────────────────────────────────────

    def canonicalize(
        self,
        ledger: EvidenceLedger,
        job_id: Optional[str] = None,
    ) -> List[CanonicalNode]:
        """Promote job-scoped evidence into canonical nodes.

        For each evidence item:
        1. Check if a similar canonical node already exists (fuzzy match).
        2. If yes, record it as an alias and boost confidence.
        3. If no, create a new canonical node.

        Returns the list of new or updated canonical nodes.
        """
        existing_nodes = self._load_existing_nodes()
        # Merge in-memory cache (for no-DB usage across multiple canonicalize calls)
        if not self._db:
            existing_nodes = list(self._in_memory_nodes)
        new_nodes: List[CanonicalNode] = []
        updated_nodes: List[CanonicalNode] = []

        for item in ledger.items:
            match = self._find_matching_node(item, existing_nodes + new_nodes)

            if match:
                # Record as alias and boost
                if item.text not in match.aliases:
                    match.aliases.append(item.text)
                match.confidence = min(1.0, match.confidence + 0.05)
                updated_nodes.append(match)
            else:
                # Create new canonical node
                # Use fresh_confidence (age-decayed) so stale inferred/user_stated
                # evidence enters the graph with appropriately low confidence.
                node = CanonicalNode(
                    id=self._canonical_id(item),
                    canonical_text=item.text,
                    tier=item.tier.value if isinstance(item.tier, EvidenceTier) else item.tier,
                    source=item.source.value if hasattr(item.source, "value") else str(item.source),
                    source_field=item.source_field,
                    confidence=item.fresh_confidence,
                    first_seen_job_id=job_id,
                    metadata=item.metadata.copy(),
                )
                new_nodes.append(node)
                existing_nodes.append(node)

        if self._db and self._user_id:
            self._persist_nodes(new_nodes, updated_nodes)

        # Update in-memory cache for subsequent calls without DB
        if not self._db:
            for node in new_nodes:
                self._in_memory_nodes.append(node)

        logger.info(
            "evidence_graph.canonicalize",
            user_id=self._user_id,
            new_nodes=len(new_nodes),
            updated_nodes=len(updated_nodes),
            total=len(existing_nodes),
        )

        return new_nodes + updated_nodes

    def _find_matching_node(
        self,
        item: EvidenceItem,
        existing: List[CanonicalNode],
    ) -> Optional[CanonicalNode]:
        """Find an existing canonical node that matches this evidence item."""
        item_text = self._normalize_text(item.text)

        for node in existing:
            node_text = self._normalize_text(node.canonical_text)
            similarity = SequenceMatcher(None, item_text, node_text).ratio()
            if similarity >= self.SIMILARITY_THRESHOLD:
                return node

            # Also check aliases
            for alias in node.aliases:
                alias_text = self._normalize_text(alias)
                sim = SequenceMatcher(None, item_text, alias_text).ratio()
                if sim >= self.SIMILARITY_THRESHOLD:
                    return node

        return None

    # ── Contradiction detection ───────────────────────────────────────

    def detect_contradictions(
        self,
        nodes: Optional[List[CanonicalNode]] = None,
    ) -> List[Contradiction]:
        """Scan canonical nodes for contradictions.

        Contradiction types:
        1. Company name conflicts — same company, different textual names
        2. Title conflicts — conflicting seniority for same role/period
        3. Date overlaps — overlapping employment periods
        4. Certification conflicts — different details for same cert
        5. Metric conflicts — contradictory impact numbers
        """
        if nodes is None:
            nodes = self._load_existing_nodes()

        contradictions: List[Contradiction] = []

        # Group nodes by source category for efficient comparison
        profile_nodes = [n for n in nodes if n.source == "profile"]

        # 1. Company name conflicts
        contradictions.extend(self._detect_company_conflicts(profile_nodes))

        # 2. Title conflicts
        contradictions.extend(self._detect_title_conflicts(profile_nodes))

        # 3. Date overlaps
        contradictions.extend(self._detect_date_overlaps(profile_nodes))

        # 4. Certification conflicts
        contradictions.extend(self._detect_certification_conflicts(profile_nodes))

        # 5. Metric conflicts
        contradictions.extend(self._detect_metric_conflicts(profile_nodes))

        if self._db and self._user_id:
            self._persist_contradictions(contradictions)

        logger.info(
            "evidence_graph.contradictions",
            user_id=self._user_id,
            total=len(contradictions),
            by_type={ct.value: sum(1 for c in contradictions if c.contradiction_type == ct)
                     for ct in ContradictionType},
        )

        return contradictions

    def _detect_company_conflicts(self, nodes: List[CanonicalNode]) -> List[Contradiction]:
        """Detect references to the same company with different names."""
        contradictions = []
        company_nodes = [n for n in nodes if "company" in n.source_field.lower() or "employer" in n.source_field.lower()]

        for i, a in enumerate(company_nodes):
            for b in company_nodes[i + 1:]:
                similarity = SequenceMatcher(
                    None,
                    self._normalize_text(a.canonical_text),
                    self._normalize_text(b.canonical_text),
                ).ratio()
                # Similar but not the same — possible alias confusion
                if 0.5 < similarity < 0.85:
                    contradictions.append(Contradiction(
                        node_a=a, node_b=b,
                        contradiction_type=ContradictionType.COMPANY_NAME,
                        severity="low",
                        description=f"Company names are similar but not identical: "
                                    f"'{a.canonical_text}' vs '{b.canonical_text}'",
                    ))
        return contradictions

    def _detect_title_conflicts(self, nodes: List[CanonicalNode]) -> List[Contradiction]:
        """Detect conflicting job titles (e.g., junior vs senior for overlapping periods)."""
        contradictions = []
        title_nodes = [n for n in nodes if "title" in n.source_field.lower() or "role" in n.source_field.lower()]

        seniority_levels = {
            "intern": 0, "junior": 1, "associate": 1, "mid": 2,
            "senior": 3, "lead": 4, "staff": 4, "principal": 5,
            "director": 6, "vp": 7, "head": 7, "chief": 8, "c-level": 8,
        }

        for i, a in enumerate(title_nodes):
            a_seniority = self._extract_seniority(a.canonical_text, seniority_levels)
            for b in title_nodes[i + 1:]:
                b_seniority = self._extract_seniority(b.canonical_text, seniority_levels)
                # Different seniority for same company/role
                if a_seniority is not None and b_seniority is not None:
                    if abs(a_seniority - b_seniority) >= 2:
                        contradictions.append(Contradiction(
                            node_a=a, node_b=b,
                            contradiction_type=ContradictionType.TITLE_CONFLICT,
                            severity="medium",
                            description=f"Large seniority gap: "
                                        f"'{a.canonical_text}' vs '{b.canonical_text}'",
                        ))
        return contradictions

    def _detect_date_overlaps(self, nodes: List[CanonicalNode]) -> List[Contradiction]:
        """Detect overlapping employment date ranges."""
        contradictions = []
        date_nodes = [n for n in nodes if "date" in n.source_field.lower() or "period" in n.source_field.lower()]

        date_ranges = []
        for node in date_nodes:
            parsed = self._parse_date_range(node.canonical_text)
            if parsed:
                date_ranges.append((node, parsed[0], parsed[1]))

        for i, (node_a, start_a, end_a) in enumerate(date_ranges):
            for node_b, start_b, end_b in date_ranges[i + 1:]:
                if start_a < end_b and start_b < end_a:  # overlap check
                    contradictions.append(Contradiction(
                        node_a=node_a, node_b=node_b,
                        contradiction_type=ContradictionType.DATE_OVERLAP,
                        severity="high",
                        description=f"Overlapping date ranges: "
                                    f"'{node_a.canonical_text}' vs '{node_b.canonical_text}'",
                    ))
        return contradictions

    def _detect_certification_conflicts(self, nodes: List[CanonicalNode]) -> List[Contradiction]:
        """Detect conflicting certification details."""
        contradictions = []
        cert_nodes = [n for n in nodes if "cert" in n.source_field.lower() or "education" in n.source_field.lower()]

        for i, a in enumerate(cert_nodes):
            for b in cert_nodes[i + 1:]:
                # Same cert name but different issuing body
                a_name = self._extract_cert_name(a.canonical_text)
                b_name = self._extract_cert_name(b.canonical_text)
                if a_name and b_name and a_name == b_name:
                    if a.canonical_text != b.canonical_text:
                        contradictions.append(Contradiction(
                            node_a=a, node_b=b,
                            contradiction_type=ContradictionType.CERTIFICATION_CONFLICT,
                            severity="medium",
                            description=f"Same certification with different details: "
                                        f"'{a.canonical_text}' vs '{b.canonical_text}'",
                        ))
        return contradictions

    def _detect_metric_conflicts(self, nodes: List[CanonicalNode]) -> List[Contradiction]:
        """Detect contradictory impact metrics (e.g., different percentages for same achievement)."""
        contradictions = []
        metric_nodes = [
            n for n in nodes
            if any(c in n.canonical_text for c in ("%", "$", "revenue", "users", "reduced", "increased"))
        ]

        for i, a in enumerate(metric_nodes):
            for b in metric_nodes[i + 1:]:
                # Same context but different numbers
                a_nums = re.findall(r"[\d,]+(?:\.\d+)?", a.canonical_text)
                b_nums = re.findall(r"[\d,]+(?:\.\d+)?", b.canonical_text)
                if not a_nums or not b_nums:
                    continue

                # Check if the non-numeric text is similar (same achievement, different numbers)
                a_text = re.sub(r"[\d,]+(?:\.\d+)?", "X", a.canonical_text)
                b_text = re.sub(r"[\d,]+(?:\.\d+)?", "X", b.canonical_text)
                similarity = SequenceMatcher(None, a_text.lower(), b_text.lower()).ratio()

                if similarity > 0.8 and a_nums != b_nums:
                    contradictions.append(Contradiction(
                        node_a=a, node_b=b,
                        contradiction_type=ContradictionType.METRIC_CONFLICT,
                        severity="high",
                        description=f"Same achievement with different metrics: "
                                    f"'{a.canonical_text}' vs '{b.canonical_text}'",
                    ))
        return contradictions

    # ── Scoring ───────────────────────────────────────────────────────

    def compute_evidence_strength(self) -> EvidenceGraphStats:
        """Compute evidence strength statistics for the adaptive planner."""
        nodes = self._load_existing_nodes()
        contradictions = self._load_existing_contradictions()

        stats = EvidenceGraphStats(
            total_nodes=len(nodes),
            verbatim_count=sum(1 for n in nodes if n.tier == "verbatim"),
            derived_count=sum(1 for n in nodes if n.tier == "derived"),
            inferred_count=sum(1 for n in nodes if n.tier == "inferred"),
            user_stated_count=sum(1 for n in nodes if n.tier == "user_stated"),
            avg_confidence=sum(n.confidence for n in nodes) / max(len(nodes), 1),
            contradiction_count=len(contradictions),
            unresolved_contradictions=sum(1 for c in contradictions if c.severity != "resolved"),
        )
        return stats

    def compute_evidence_strength_score(self) -> int:
        """Return a 0-100 score for evidence strength.

        Used by the adaptive planner for risk_mode decisions.
        """
        stats = self.compute_evidence_strength()

        if stats.total_nodes == 0:
            return 0

        # Base score from volume and tier quality
        tier_weights = {
            "verbatim": 1.0,
            "derived": 0.75,
            "inferred": 0.5,
            "user_stated": 0.3,
        }
        weighted_sum = (
            stats.verbatim_count * tier_weights["verbatim"]
            + stats.derived_count * tier_weights["derived"]
            + stats.inferred_count * tier_weights["inferred"]
            + stats.user_stated_count * tier_weights["user_stated"]
        )
        # Normalize: 50 weighted items = 100 base points
        base = min(100, int(weighted_sum * 2))

        # Confidence bonus
        conf_bonus = int(stats.avg_confidence * 20)

        # Contradiction penalty
        penalty = stats.unresolved_contradictions * 10

        return max(0, min(100, base + conf_bonus - penalty))

    # ── Persistence helpers ───────────────────────────────────────────

    def _load_existing_nodes(self) -> List[CanonicalNode]:
        """Load canonical nodes from DB for this user."""
        if not self._db or not self._user_id:
            return []
        try:
            resp = self._db.table("user_evidence_nodes") \
                .select("*") \
                .eq("user_id", self._user_id) \
                .execute()
            nodes = []
            for row in (resp.data or []):
                nodes.append(CanonicalNode(
                    id=row["id"],
                    canonical_text=row["canonical_text"],
                    tier=row["tier"],
                    source=row["source"],
                    source_field=row.get("source_field", ""),
                    confidence=row.get("confidence", 0.5),
                    first_seen_job_id=row.get("first_seen_job_id"),
                    metadata=row.get("metadata", {}),
                ))
            return nodes
        except Exception as e:
            logger.warning("evidence_graph.load_nodes_failed", error=str(e)[:200])
            return []

    def _load_existing_contradictions(self) -> List[Contradiction]:
        """Load contradictions from DB for this user."""
        if not self._db or not self._user_id:
            return []
        try:
            resp = self._db.table("evidence_contradictions") \
                .select("*") \
                .eq("user_id", self._user_id) \
                .is_("resolved_at", "null") \
                .execute()
            # Return minimal stubs for counting purposes
            contradictions = []
            for row in (resp.data or []):
                contradictions.append(Contradiction(
                    node_a=CanonicalNode(id=row["node_a_id"], canonical_text="", tier="", source="", source_field="", confidence=0),
                    node_b=CanonicalNode(id=row["node_b_id"], canonical_text="", tier="", source="", source_field="", confidence=0),
                    contradiction_type=ContradictionType(row["contradiction_type"]),
                    severity=row.get("severity", "medium"),
                    description=row.get("description", ""),
                ))
            return contradictions
        except Exception as e:
            logger.warning("evidence_graph.load_contradictions_failed", error=str(e)[:200])
            return []

    def _persist_nodes(self, new_nodes: List[CanonicalNode], updated_nodes: List[CanonicalNode]) -> None:
        """Persist new canonical nodes and update existing ones."""
        if not self._db or not self._user_id:
            return
        try:
            for node in new_nodes:
                self._db.table("user_evidence_nodes").insert({
                    "id": node.id,
                    "user_id": self._user_id,
                    "canonical_text": node.canonical_text,
                    "tier": node.tier,
                    "source": node.source,
                    "source_field": node.source_field,
                    "confidence": node.confidence,
                    "first_seen_job_id": node.first_seen_job_id,
                    "metadata": node.metadata,
                }).execute()

            for node in updated_nodes:
                self._db.table("user_evidence_nodes").update({
                    "confidence": node.confidence,
                }).eq("id", node.id).execute()

            # Persist aliases
            for node in new_nodes + updated_nodes:
                for alias in node.aliases:
                    self._db.table("user_evidence_aliases").insert({
                        "user_id": self._user_id,
                        "canonical_node_id": node.id,
                        "alias_text": alias,
                        "similarity_score": self.SIMILARITY_THRESHOLD,
                        "source_job_id": node.first_seen_job_id,
                    }).execute()
        except Exception as e:
            logger.warning("evidence_graph.persist_nodes_failed", error=str(e)[:200])

    def _persist_contradictions(self, contradictions: List[Contradiction]) -> None:
        """Persist detected contradictions to DB."""
        if not self._db or not self._user_id:
            return
        try:
            for c in contradictions:
                self._db.table("evidence_contradictions").insert({
                    "user_id": self._user_id,
                    "node_a_id": c.node_a.id,
                    "node_b_id": c.node_b.id,
                    "contradiction_type": c.contradiction_type.value,
                    "severity": c.severity,
                    "description": c.description,
                }).execute()
        except Exception as e:
            logger.warning("evidence_graph.persist_contradictions_failed", error=str(e)[:200])

    # ── Outcome feedback loop ───────────────────────────────────────

    # Outcome → confidence delta mapping
    _OUTCOME_DELTAS = {
        "offer": 0.10,      # Strong positive signal
        "callback": 0.05,   # Moderate positive signal
        "rejected": -0.03,  # Mild negative signal (evidence may still be valid)
        "ghosted": -0.01,   # Weak negative signal
    }

    def apply_outcome_feedback(
        self,
        outcome: str,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adjust canonical node confidence based on application outcome.

        When a user reports an outcome (offer, callback, rejected, ghosted),
        boost or lower the confidence of evidence nodes that were in scope
        for that application.

        Args:
            outcome: One of 'offer', 'callback', 'rejected', 'ghosted'.
            job_id: Optional job_id to limit which nodes are affected.
                    If None, adjusts all user nodes.

        Returns:
            Summary dict with adjusted_count and delta applied.
        """
        delta = self._OUTCOME_DELTAS.get(outcome, 0.0)
        if delta == 0.0:
            return {"adjusted_count": 0, "delta": 0.0, "outcome": outcome}

        nodes = self._load_existing_nodes()
        if job_id:
            nodes = [n for n in nodes if n.first_seen_job_id == job_id]

        adjusted = 0
        for node in nodes:
            new_confidence = max(0.0, min(1.0, node.confidence + delta))
            if new_confidence != node.confidence:
                node.confidence = new_confidence
                adjusted += 1

        if self._db and self._user_id and adjusted:
            try:
                for node in nodes:
                    self._db.table("user_evidence_nodes").update({
                        "confidence": node.confidence,
                    }).eq("id", node.id).execute()
            except Exception as e:
                logger.warning(
                    "evidence_graph.outcome_feedback_persist_failed",
                    error=str(e)[:200],
                )

        logger.info(
            "evidence_graph.outcome_feedback",
            user_id=self._user_id,
            outcome=outcome,
            delta=delta,
            adjusted_count=adjusted,
            total_nodes=len(nodes),
        )

        return {
            "adjusted_count": adjusted,
            "delta": delta,
            "outcome": outcome,
        }

    # ── Text processing helpers ───────────────────────────────────────

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        return re.sub(r"\s+", " ", text.strip().lower())

    @staticmethod
    def _canonical_id(item: EvidenceItem) -> str:
        """Generate a canonical node ID from an evidence item."""
        source = item.source.value if hasattr(item.source, "value") else str(item.source)
        content = f"canonical:{source}:{item.source_field}:{item.text[:200]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    def _extract_seniority(title: str, levels: Dict[str, int]) -> Optional[int]:
        """Extract seniority level from a job title."""
        title_lower = title.lower()
        for keyword, level in sorted(levels.items(), key=lambda x: -x[1]):
            if keyword in title_lower:
                return level
        return None

    @staticmethod
    def _parse_date_range(text: str) -> Optional[Tuple[int, int]]:
        """Parse a date range into (start_year_month, end_year_month).

        Handles formats like "Jan 2020 - Mar 2023", "2020-2023", "2020 - present".
        """
        # Try "YYYY - YYYY" or "YYYY - present"
        m = re.search(r"(\d{4})\s*[-–]\s*(?:(\d{4})|present|current)", text, re.IGNORECASE)
        if m:
            start = int(m.group(1)) * 12
            end = int(m.group(2)) * 12 + 12 if m.group(2) else 2026 * 12 + 4
            return (start, end)

        # Try "Mon YYYY - Mon YYYY"
        months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                  "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        pattern = r"([a-z]{3})\w*\s+(\d{4})\s*[-–]\s*([a-z]{3})\w*\s+(\d{4})"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            start = int(m.group(2)) * 12 + months.get(m.group(1).lower()[:3], 1)
            end = int(m.group(4)) * 12 + months.get(m.group(3).lower()[:3], 1)
            return (start, end)

        return None

    @staticmethod
    def _extract_cert_name(text: str) -> Optional[str]:
        """Extract certification name (e.g., 'AWS Solutions Architect', 'PMP')."""
        patterns = [
            r"(AWS\s+[\w\s]+?(?:Associate|Professional|Architect|Developer|Administrator|Practitioner))",
            r"\b(PMP|CISSP|CPA|CFA|CCNA|CCNP|CISA|CISM|CEH|CompTIA\s+\w+)\b",
            r"(\w+\s+Certified\s+[\w\s]+?(?:Associate|Professional|Expert))",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1).strip().lower()
        return None
