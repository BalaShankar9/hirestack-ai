"""ATLAS multi-source candidate fusion.

Merges signals from multiple zero-config providers into a single
``CandidateProfile`` artifact. Inputs (all optional except resume
skills):

* ``resume_skills`` — raw skill strings already parsed by the upstream
  ``RoleProfilerChain`` (or any caller-supplied list).
* ``github`` — the ``raw`` payload from
  :class:`ai_engine.agents.sub_agents.atlas.sources.github_user.GitHubUserProvider`.
* ``linkedin`` — the ``raw`` payload from
  :class:`ai_engine.agents.sub_agents.atlas.sources.linkedin_public.LinkedInPublicProvider`.
* ``impact_signals`` — output of
  :class:`ai_engine.agents.sub_agents.atlas.impact_extractor.ImpactExtractor`.

Per-skill rules:

* Provenance accumulates one record per source that mentioned the skill.
* ``proficiency`` = ``max(confidence)`` across providers.
* ``verified`` flips to ``True`` when ≥ 2 distinct sources back the
  claim.
* Skill decay — if the most recent ``last_used_at`` parses to a date
  older than 36 months, multiply proficiency by 0.7.

Pure synchronous; no I/O. Safe to import unconditionally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from ai_engine.agents.artifact_contracts import (
    CandidateProfile,
    CandidateSkill,
    ImpactSignal,
    SkillProvenance,
)

logger = logging.getLogger(__name__)


_MAX_SKILLS = 20                  # Cap on the fused candidate skill list.
_DECAY_MONTHS = 36
_DECAY_FACTOR = 0.7

# Per-source confidence weighting when no per-record confidence available.
_CONF_RESUME = 0.6
_CONF_LINKEDIN = 0.5
_CONF_GH_TOP = 0.9                # confidence for the #1 GitHub language
_CONF_GH_STEP = 0.15              # decrement per rank


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    return (name or "").strip().lower()


def _parse_iso_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Last-ditch fromisoformat (handles +00:00).
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _months_since(dt: datetime, *, now: Optional[datetime] = None) -> float:
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return delta.days / 30.4375


# ---------------------------------------------------------------------------
# Internal accumulator
# ---------------------------------------------------------------------------

@dataclass
class _SkillBucket:
    name: str                         # original-cased label (first writer wins)
    provenance: List[SkillProvenance] = field(default_factory=list)

    def add(self, prov: SkillProvenance) -> None:
        self.provenance.append(prov)

    @property
    def max_confidence(self) -> float:
        return max((p.confidence for p in self.provenance), default=0.0)

    @property
    def latest_use(self) -> Optional[datetime]:
        dates = []
        for p in self.provenance:
            d = _parse_iso_date(p.last_used_at)
            if d is not None:
                dates.append(d)
        return max(dates) if dates else None

    @property
    def source_set(self) -> set:
        return {p.source for p in self.provenance}


# ---------------------------------------------------------------------------
# Source ingesters
# ---------------------------------------------------------------------------

def _ingest_resume(
    buckets: Dict[str, _SkillBucket],
    resume_skills: Iterable[str],
    evidence_map: Dict[str, str],
) -> None:
    for raw in resume_skills or []:
        if not raw:
            continue
        name = str(raw).strip()
        if not name:
            continue
        key = _normalize(name)
        bucket = buckets.setdefault(key, _SkillBucket(name=name))
        bucket.add(
            SkillProvenance(
                source="resume",
                confidence=_CONF_RESUME,
                evidence=(evidence_map.get(key, "") or "")[:280],
            )
        )


def _ingest_github(
    buckets: Dict[str, _SkillBucket],
    github: Optional[Dict[str, Any]],
) -> None:
    if not github or not isinstance(github, dict):
        return
    langs = github.get("top_languages") or []
    if not isinstance(langs, list):
        return
    most_recent = github.get("most_recent_push")
    last_used_at = most_recent if isinstance(most_recent, str) else None

    for rank, lang in enumerate(langs):
        if not lang:
            continue
        name = str(lang).strip()
        if not name:
            continue
        key = _normalize(name)
        confidence = max(0.3, _CONF_GH_TOP - rank * _CONF_GH_STEP)
        bucket = buckets.setdefault(key, _SkillBucket(name=name))
        bucket.add(
            SkillProvenance(
                source="github_user",
                confidence=confidence,
                evidence=f"top language rank {rank + 1}",
                last_used_at=last_used_at,
            )
        )


def _ingest_linkedin(
    buckets: Dict[str, _SkillBucket],
    linkedin: Optional[Dict[str, Any]],
) -> None:
    """Cross-reference the LinkedIn headline against existing buckets.

    LinkedIn public scraping yields no structured skill list — only a
    headline + description. We avoid hallucinating new skills; instead
    we boost any existing bucket whose normalized name appears as a
    whole-word substring in the headline or description.
    """
    if not linkedin or not isinstance(linkedin, dict):
        return
    haystack = " ".join(
        str(linkedin.get(k) or "").lower()
        for k in ("headline", "description", "raw_title")
    )
    if not haystack.strip():
        return
    for key, bucket in buckets.items():
        # Whole-word check via padded boundaries to avoid "go" matching
        # "ago" / "google".
        padded = f" {haystack} "
        if f" {key} " in padded:
            bucket.add(
                SkillProvenance(
                    source="linkedin_public",
                    confidence=_CONF_LINKEDIN,
                    evidence=f"mentioned in LinkedIn headline/summary",
                )
            )


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

def _bucket_to_skill(bucket: _SkillBucket) -> CandidateSkill:
    proficiency = bucket.max_confidence
    last_use = bucket.latest_use
    if last_use is not None and _months_since(last_use) > _DECAY_MONTHS:
        proficiency *= _DECAY_FACTOR
    proficiency = max(0.0, min(1.0, proficiency))

    if proficiency >= 0.85:
        level = "expert"
    elif proficiency >= 0.65:
        level = "advanced"
    elif proficiency >= 0.4:
        level = "intermediate"
    else:
        level = "beginner"

    verified = len(bucket.source_set) >= 2

    return CandidateSkill(
        name=bucket.name,
        level=level,
        years=0.0,
        proficiency=round(proficiency, 3),
        provenance=list(bucket.provenance),
        verified=verified,
    )


class CandidateFusion:
    """Merges multi-source signals into a :class:`CandidateProfile`."""

    def fuse(
        self,
        *,
        candidate_name: str = "",
        headline: str = "",
        summary: str = "",
        years_experience: float = 0.0,
        resume_skills: Optional[Iterable[str]] = None,
        resume_evidence: Optional[Dict[str, str]] = None,
        github: Optional[Dict[str, Any]] = None,
        linkedin: Optional[Dict[str, Any]] = None,
        impact_signals: Optional[List[ImpactSignal]] = None,
        experience: Optional[List[Dict[str, Any]]] = None,
        education: Optional[List[Dict[str, Any]]] = None,
    ) -> CandidateProfile:
        """Fuse all available signals; produce a CandidateProfile.

        Never raises; missing inputs default to empty.
        """
        buckets: Dict[str, _SkillBucket] = {}
        evidence_map = {
            _normalize(k): v
            for k, v in (resume_evidence or {}).items()
        }

        try:
            _ingest_resume(buckets, resume_skills or [], evidence_map)
        except Exception as exc:  # defensive
            logger.warning("CandidateFusion resume ingest failed: %s", exc)

        try:
            _ingest_github(buckets, github)
        except Exception as exc:
            logger.warning("CandidateFusion github ingest failed: %s", exc)

        try:
            # LinkedIn must run after the others — it boosts existing
            # buckets only.
            _ingest_linkedin(buckets, linkedin)
        except Exception as exc:
            logger.warning("CandidateFusion linkedin ingest failed: %s", exc)

        # Sort by max_confidence desc, then verified desc, name asc.
        sorted_buckets = sorted(
            buckets.values(),
            key=lambda b: (-b.max_confidence, -len(b.source_set), b.name.lower()),
        )[:_MAX_SKILLS]

        skills = [_bucket_to_skill(b) for b in sorted_buckets]

        # Use a stable known list to compute sources_used.
        sources_used: List[str] = ["resume"] if resume_skills else []
        if github and isinstance(github, dict) and (github.get("top_languages") or []):
            sources_used.append("github_user")
        if linkedin and isinstance(linkedin, dict) and any(
            linkedin.get(k) for k in ("headline", "description", "raw_title")
        ):
            sources_used.append("linkedin_public")

        # Pull headline/name from LinkedIn if not provided directly.
        if not candidate_name and isinstance(linkedin, dict):
            candidate_name = str(linkedin.get("name") or "").strip()
        if not headline and isinstance(linkedin, dict):
            headline = str(linkedin.get("headline") or "").strip()
        if not summary and isinstance(linkedin, dict):
            summary = str(linkedin.get("description") or "").strip()[:500]

        return CandidateProfile(
            candidate_name=candidate_name,
            headline=headline,
            summary=summary,
            years_experience=float(years_experience or 0.0),
            skills=skills,
            experience=list(experience or []),
            education=list(education or []),
            impact_signals=list(impact_signals or []),
            sources_used=sources_used,
        )
