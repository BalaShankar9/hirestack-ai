"""
Evidence Ledger — structured, addressable evidence objects.

Every material claim in a generated document must trace back to an
EvidenceItem in the ledger.  The ledger is populated by the researcher
and tools, consumed by the drafter as insertion constraints, and
enforced by the fact-checker and validator.

Evidence lifecycle:
  1. Researcher/tools create EvidenceItems with source provenance
  2. Drafter receives the ledger and must cite evidence IDs
  3. Fact-checker verifies each claim maps to a ledger entry
  4. Validator rejects documents with unsupported material claims

Evidence tiers (ordered by strength):
  - VERBATIM:   Exact text from source (profile, JD, company page)
  - DERIVED:    Computed from source data (keyword overlap, gap score)
  - INFERRED:   Reasonable extrapolation needing justification
  - USER_STATED: User provided but unverified (self-reported skills)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class EvidenceTier(str, Enum):
    """Strength of evidence, from strongest to weakest."""
    VERBATIM = "verbatim"       # Exact source text
    DERIVED = "derived"         # Computed from source data
    INFERRED = "inferred"       # Reasonable extrapolation
    USER_STATED = "user_stated" # Self-reported, unverified


class EvidenceSource(str, Enum):
    """Where the evidence came from."""
    PROFILE = "profile"
    JD = "jd"
    COMPANY = "company"
    TOOL = "tool"
    MEMORY = "memory"


def _coerce_evidence_tier(tier: EvidenceTier | str) -> EvidenceTier:
    """Accept either enum instances or raw values for resilience at call sites."""
    if isinstance(tier, EvidenceTier):
        return tier
    return EvidenceTier(str(tier))


def _coerce_evidence_source(source: EvidenceSource | str) -> EvidenceSource:
    """Accept either enum instances or raw values for resilience at call sites."""
    if isinstance(source, EvidenceSource):
        return source
    return EvidenceSource(str(source))


@dataclass
class EvidenceItem:
    """A single piece of addressable evidence.

    Attributes:
        id: Unique stable identifier (content-hash based for dedup).
        tier: Strength tier (verbatim > derived > inferred > user_stated).
        source: Where this evidence originated.
        source_field: Specific field path (e.g., "experience[0].description").
        text: The evidence text or value.
        metadata: Additional context (e.g., tool name, confidence score).
        confidence: How confident we are in this evidence (0.0-1.0).
                    Cross-referenced evidence (confirmed by 2+ sources) gets
                    higher confidence.  Defaults based on tier.
        confirmed_by: List of sub-agent names that independently confirmed
                      this evidence item.  Used for cross-source boosting.
        created_at: ISO-8601 timestamp when this evidence was first captured.
                    Used for freshness scoring — older inferred/user_stated
                    evidence decays in confidence.
    """
    id: str
    tier: EvidenceTier
    source: EvidenceSource
    source_field: str
    text: str
    metadata: dict = field(default_factory=dict)
    confidence: float = 0.7
    confirmed_by: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _now_iso())

    @property
    def fresh_confidence(self) -> float:
        """Confidence adjusted for age — decays inferred/user_stated evidence.

        Verbatim and derived evidence don't decay (source text is stable).
        Inferred/user_stated evidence loses 0.01 confidence per day, floored
        at 0.10, because unverified claims go stale.
        """
        if self.tier in (EvidenceTier.VERBATIM, EvidenceTier.DERIVED):
            return self.confidence
        try:
            from datetime import datetime, timezone
            created = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
            decay = age_days * 0.01
            return max(0.10, round(self.confidence - decay, 3))
        except Exception:
            return self.confidence

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "source": self.source.value,
            "source_field": self.source_field,
            "text": self.text,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "fresh_confidence": self.fresh_confidence,
            "confirmed_by": self.confirmed_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EvidenceItem:
        return cls(
            id=d["id"],
            tier=EvidenceTier(d["tier"]),
            source=EvidenceSource(d["source"]),
            source_field=d.get("source_field", ""),
            text=d["text"],
            metadata=d.get("metadata", {}),
            confidence=d.get("confidence", 0.7),
            confirmed_by=d.get("confirmed_by", []),
            created_at=d.get("created_at", _now_iso()),
        )


def _evidence_id(source: str, source_field: str, text: str) -> str:
    """Generate a stable, content-based evidence ID for deduplication."""
    content = f"{source}:{source_field}:{text[:200]}"
    return "ev_" + hashlib.sha256(content.encode()).hexdigest()[:12]


# Default confidence by tier — verbatim is highest, user_stated lowest
_DEFAULT_CONFIDENCE: dict[EvidenceTier, float] = {
    EvidenceTier.VERBATIM: 0.90,
    EvidenceTier.DERIVED: 0.75,
    EvidenceTier.INFERRED: 0.55,
    EvidenceTier.USER_STATED: 0.50,
}


@dataclass
class Citation:
    """Links a claim in a generated document to its evidence."""
    claim_text: str
    evidence_ids: list[str]
    tier: str = ""              # Resolved tier (weakest evidence cited)
    confidence: float = 0.0     # Match confidence from deterministic tools
    classification: str = ""    # 4-tier fact-check result

    def to_dict(self) -> dict:
        return {
            "claim_text": self.claim_text,
            "evidence_ids": self.evidence_ids,
            "tier": self.tier,
            "confidence": self.confidence,
            "classification": self.classification,
        }


class EvidenceLedger:
    """Append-only collection of evidence items with lookup by ID, source, and tier."""

    def __init__(self) -> None:
        self._items: dict[str, EvidenceItem] = {}

    def add(
        self,
        tier: EvidenceTier | str,
        source: EvidenceSource | str,
        source_field: str,
        text: str,
        metadata: Optional[dict] = None,
        confidence: Optional[float] = None,
        sub_agent: Optional[str] = None,
    ) -> EvidenceItem:
        """Add an evidence item. Returns existing item if content-duplicate.

        If the item already exists and a new sub_agent confirms it, the
        confidence is boosted and the confirmer is recorded.
        """
        canonical_tier = _coerce_evidence_tier(tier)
        canonical_source = _coerce_evidence_source(source)
        eid = _evidence_id(canonical_source.value, source_field, text)

        if eid in self._items:
            existing = self._items[eid]
            # Cross-source confirmation: boost confidence
            if sub_agent and sub_agent not in existing.confirmed_by:
                existing.confirmed_by.append(sub_agent)
                existing.confidence = min(1.0, existing.confidence + 0.10)
            return existing

        default_conf = _DEFAULT_CONFIDENCE.get(canonical_tier, 0.7)
        confirmed = [sub_agent] if sub_agent else []
        meta = metadata or {}
        if sub_agent:
            meta["sub_agent"] = sub_agent

        item = EvidenceItem(
            id=eid,
            tier=canonical_tier,
            source=canonical_source,
            source_field=source_field,
            text=text,
            metadata=meta,
            confidence=confidence if confidence is not None else default_conf,
            confirmed_by=confirmed,
        )
        self._items[eid] = item
        return item

    def get(self, evidence_id: str) -> Optional[EvidenceItem]:
        return self._items.get(evidence_id)

    def find_by_source(self, source: EvidenceSource) -> list[EvidenceItem]:
        return [i for i in self._items.values() if i.source == source]

    def find_by_tier(self, tier: EvidenceTier) -> list[EvidenceItem]:
        return [i for i in self._items.values() if i.tier == tier]

    def find_by_text(self, text_fragment: str) -> list[EvidenceItem]:
        """Find evidence items containing the given text fragment."""
        fragment_lower = text_fragment.lower()
        return [
            i for i in self._items.values()
            if fragment_lower in i.text.lower()
        ]

    def find_by_pool_value(self, pool: str, value: str) -> list[EvidenceItem]:
        """Exact, deterministic lookup by (pool, value) metadata pair.

        Items added via populate_from_profile are tagged with
        ``metadata['pool']`` (skill | company | title | cert | education)
        and ``metadata['value']`` (the lower-cased canonical value).
        Fact-checker tools emit source markers in the same vocabulary
        (``"skill:python"``), so the orchestrator can resolve a marker
        to a stable evidence_id without text matching.

        This is the deterministic path used by
        ``_rebuild_citations_from_fact_check``; it falls back to
        :meth:`find_by_text` when an item wasn't pool-tagged (legacy
        profile shapes, externally-added evidence, etc.).
        """
        if not pool or not value:
            return []
        value_lower = value.strip().lower()
        pool_lower = pool.strip().lower()
        return [
            i for i in self._items.values()
            if i.metadata.get("pool") == pool_lower
            and i.metadata.get("value") == value_lower
        ]

    def confirm(self, evidence_id: str, sub_agent: str) -> None:
        """Record that *sub_agent* independently confirmed this evidence.

        Boosts confidence by +0.10 per unique confirmer (capped at 1.0).
        """
        item = self._items.get(evidence_id)
        if item and sub_agent not in item.confirmed_by:
            item.confirmed_by.append(sub_agent)
            item.confidence = min(1.0, item.confidence + 0.10)

    def boost_cross_referenced(self) -> int:
        """Boost confidence for items confirmed by 2+ sub-agents.

        Returns the number of items that received a boost.
        """
        boosted = 0
        for item in self._items.values():
            if len(item.confirmed_by) >= 2 and item.confidence < 0.95:
                item.confidence = min(1.0, item.confidence + 0.05 * (len(item.confirmed_by) - 1))
                boosted += 1
        return boosted

    def find_high_confidence(self, threshold: float = 0.80) -> list[EvidenceItem]:
        """Return items with confidence at or above the threshold."""
        return [i for i in self._items.values() if i.confidence >= threshold]

    @property
    def items(self) -> list[EvidenceItem]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, evidence_id: str) -> bool:
        return evidence_id in self._items

    def to_dict(self) -> dict:
        """Serialize for JSON transport between agents."""
        return {
            "items": [i.to_dict() for i in self._items.values()],
            "count": len(self._items),
            "tier_counts": {
                tier.value: len(self.find_by_tier(tier))
                for tier in EvidenceTier
            },
            "source_counts": {
                src.value: len(self.find_by_source(src))
                for src in EvidenceSource
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> EvidenceLedger:
        """Reconstruct from serialized form."""
        ledger = cls()
        for item_dict in d.get("items", []):
            item = EvidenceItem.from_dict(item_dict)
            ledger._items[item.id] = item
        return ledger

    def to_prompt_context(self, max_items: int = 50) -> str:
        """Format ledger for inclusion in LLM prompts.

        Prioritises verbatim > derived > inferred > user_stated,
        truncates to max_items to fit token budgets.
        """
        priority = {
            EvidenceTier.VERBATIM: 0,
            EvidenceTier.DERIVED: 1,
            EvidenceTier.INFERRED: 2,
            EvidenceTier.USER_STATED: 3,
        }
        sorted_items = sorted(self._items.values(), key=lambda i: priority.get(i.tier, 9))
        lines = [f"## Evidence Ledger ({len(self._items)} items)\n"]
        for item in sorted_items[:max_items]:
            lines.append(
                f"- [{item.id}] ({item.tier.value}, {item.source.value}) "
                f"{item.source_field}: {item.text[:150]}"
            )
        if len(self._items) > max_items:
            lines.append(f"\n... and {len(self._items) - max_items} more items")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
#  Ledger population helpers — called by researcher and tools
# ═══════════════════════════════════════════════════════════════════════

def populate_from_profile(ledger: EvidenceLedger, user_profile: dict) -> None:
    """Extract evidence items from a user profile dict."""
    # Skills
    for i, skill in enumerate(user_profile.get("skills") or []):
        if isinstance(skill, dict):
            name = skill.get("name", "")
        else:
            name = str(skill)
        if name:
            ledger.add(
                tier=EvidenceTier.USER_STATED,
                source=EvidenceSource.PROFILE,
                source_field=f"skills[{i}]",
                text=name,
                metadata={
                    "endorsements": skill.get("endorsements", 0) if isinstance(skill, dict) else 0,
                    "pool": "skill",
                    "value": name.strip().lower(),
                },
            )

    # Experience
    for i, exp in enumerate(user_profile.get("experience") or []):
        if not isinstance(exp, dict):
            continue
        title = exp.get("title", "")
        company = exp.get("company", "")
        desc = exp.get("description", "")

        if title:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.PROFILE,
                source_field=f"experience[{i}].title",
                text=title,
                metadata={"pool": "title", "value": title.strip().lower()},
            )
        if company:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.PROFILE,
                source_field=f"experience[{i}].company",
                text=company,
                metadata={"pool": "company", "value": company.strip().lower()},
            )
        if desc:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.PROFILE,
                source_field=f"experience[{i}].description",
                text=desc[:500],
            )

        # Dates are verbatim
        start = exp.get("start_date") or exp.get("startDate")
        end = exp.get("end_date") or exp.get("endDate")
        if start:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.PROFILE,
                source_field=f"experience[{i}].start_date",
                text=str(start),
            )
        if end:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.PROFILE,
                source_field=f"experience[{i}].end_date",
                text=str(end),
            )

    # Education
    for i, edu in enumerate(user_profile.get("education") or []):
        if not isinstance(edu, dict):
            continue
        for k in ("degree", "institution", "field", "fieldOfStudy"):
            val = edu.get(k, "")
            if val:
                ledger.add(
                    tier=EvidenceTier.VERBATIM,
                    source=EvidenceSource.PROFILE,
                    source_field=f"education[{i}].{k}",
                    text=str(val),
                    metadata={"pool": "education", "value": str(val).strip().lower()},
                )

    # Certifications
    for i, cert in enumerate(user_profile.get("certifications") or []):
        if isinstance(cert, dict):
            name = cert.get("name", "")
        else:
            name = str(cert)
        if name:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.PROFILE,
                source_field=f"certifications[{i}]",
                text=name,
                metadata={"pool": "cert", "value": name.strip().lower()},
            )

    # Summary / headline
    for field_name in ("summary", "headline", "title"):
        val = user_profile.get(field_name, "")
        if val and isinstance(val, str):
            ledger.add(
                tier=EvidenceTier.USER_STATED,
                source=EvidenceSource.PROFILE,
                source_field=field_name,
                text=val[:500],
            )


def populate_from_jd(ledger: EvidenceLedger, jd_parsed: dict) -> None:
    """Extract evidence items from a parsed JD result.

    Handles both legacy and v2 parse_jd output formats:
      top_keywords, must_have_keywords, nice_to_have_keywords, requirements
    """
    for i, kw in enumerate(jd_parsed.get("top_keywords") or []):
        word = kw.get("word", kw) if isinstance(kw, dict) else str(kw)
        if word:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.JD,
                source_field=f"top_keywords[{i}]",
                text=word,
                metadata={"score": kw.get("score", 0) if isinstance(kw, dict) else 0},
            )

    # Must-have keywords from v2 JD parser (higher priority)
    for i, kw in enumerate(jd_parsed.get("must_have_keywords") or []):
        word = str(kw)
        if word:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.JD,
                source_field=f"must_have_keywords[{i}]",
                text=word,
                metadata={"priority": "must_have"},
            )

    # Nice-to-have keywords from v2 JD parser
    for i, kw in enumerate(jd_parsed.get("nice_to_have_keywords") or []):
        word = str(kw)
        if word:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.JD,
                source_field=f"nice_to_have_keywords[{i}]",
                text=word,
                metadata={"priority": "nice_to_have"},
            )

    for i, req in enumerate(jd_parsed.get("requirements") or []):
        text = req.get("text", req) if isinstance(req, dict) else str(req)
        if text:
            ledger.add(
                tier=EvidenceTier.VERBATIM,
                source=EvidenceSource.JD,
                source_field=f"requirements[{i}]",
                text=text,
                metadata={"category": req.get("category", "") if isinstance(req, dict) else ""},
            )


def populate_from_tool_result(
    ledger: EvidenceLedger,
    tool_name: str,
    result: dict,
) -> None:
    """Extract evidence items from a deterministic tool result.

    Key mapping (tools.py output → evidence ingestion):
      compute_keyword_overlap → matched_keywords, missing_from_document, fuzzy_matches
      extract_profile_evidence → skills, companies, titles, education, certifications
      compute_readability → flesch_reading_ease
      extract_claims → claims
    """
    if tool_name == "compute_keyword_overlap":
        # Exact keyword matches  (tools.py key: matched_keywords)
        for i, word in enumerate(result.get("matched_keywords") or result.get("matches") or []):
            kw = word.get("keyword", word) if isinstance(word, dict) else str(word)
            if kw:
                ledger.add(
                    tier=EvidenceTier.DERIVED,
                    source=EvidenceSource.TOOL,
                    source_field=f"keyword_overlap.matches[{i}]",
                    text=kw,
                    metadata={
                        "tool": tool_name,
                        "match_ratio": result.get("match_ratio", 0),
                    },
                )
        # Fuzzy keyword matches (tools.py key: fuzzy_matches)
        for i, fm in enumerate(result.get("fuzzy_matches") or []):
            if isinstance(fm, dict):
                jd_kw = fm.get("jd_keyword", "")
                doc_kw = fm.get("doc_keyword", "")
                sim = fm.get("similarity", 0)
                if jd_kw:
                    ledger.add(
                        tier=EvidenceTier.DERIVED,
                        source=EvidenceSource.TOOL,
                        source_field=f"keyword_overlap.fuzzy[{i}]",
                        text=jd_kw,
                        metadata={"tool": tool_name, "doc_variant": doc_kw, "similarity": sim},
                    )
        # Missing keywords / gaps  (tools.py key: missing_from_document)
        for i, word in enumerate(result.get("missing_from_document") or result.get("gaps") or []):
            kw = word.get("keyword", word) if isinstance(word, dict) else str(word)
            if kw:
                ledger.add(
                    tier=EvidenceTier.DERIVED,
                    source=EvidenceSource.TOOL,
                    source_field=f"keyword_overlap.gaps[{i}]",
                    text=f"MISSING: {kw}",
                    metadata={"tool": tool_name, "type": "gap"},
                )

    elif tool_name == "extract_profile_evidence":
        for field_name in ("skills", "companies", "titles", "education", "certifications"):
            for i, val in enumerate(result.get(field_name) or []):
                if val:
                    ledger.add(
                        tier=EvidenceTier.VERBATIM,
                        source=EvidenceSource.TOOL,
                        source_field=f"extracted.{field_name}[{i}]",
                        text=str(val),
                        metadata={"tool": tool_name},
                    )

    elif tool_name == "compute_readability":
        # tools.py key: flesch_reading_ease  (fallback: flesch_score, score)
        score = result.get("flesch_reading_ease", result.get("flesch_score", result.get("score")))
        if score is not None:
            ledger.add(
                tier=EvidenceTier.DERIVED,
                source=EvidenceSource.TOOL,
                source_field="readability.flesch_score",
                text=f"Flesch readability score: {score}",
                metadata={"tool": tool_name, "score": score},
            )

    elif tool_name == "extract_claims":
        for i, claim in enumerate(result.get("claims") or []):
            text = claim.get("text", claim) if isinstance(claim, dict) else str(claim)
            if text:
                ledger.add(
                    tier=EvidenceTier.DERIVED,
                    source=EvidenceSource.TOOL,
                    source_field=f"claims[{i}]",
                    text=text,
                    metadata={"tool": tool_name, "type": claim.get("type", "") if isinstance(claim, dict) else ""},
                )


def populate_from_company_intel(ledger: EvidenceLedger, intel: dict) -> None:
    """Extract evidence items from company intelligence results."""
    for field_name in ("name", "industry", "size", "culture"):
        val = intel.get(field_name)
        if val and isinstance(val, str):
            ledger.add(
                tier=EvidenceTier.INFERRED,
                source=EvidenceSource.COMPANY,
                source_field=f"company.{field_name}",
                text=val[:300],
            )
    for i, val in enumerate(intel.get("values") or []):
        if val:
            ledger.add(
                tier=EvidenceTier.INFERRED,
                source=EvidenceSource.COMPANY,
                source_field=f"company.values[{i}]",
                text=str(val)[:200],
            )
