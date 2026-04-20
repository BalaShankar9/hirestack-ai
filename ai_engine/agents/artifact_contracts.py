"""
Typed artifact contracts for the v4 agent orchestrator.

Every agent in the rebuild produces ARTIFACTS — versioned, lineage-tagged,
schema-validated data objects. Artifacts are the unit of communication
between agents (no more passing dicts around). They are also the unit of
persistence in the `agent_artifacts` table, which lets us:

  - Resume a pipeline from any artifact boundary
  - Build a full provenance graph (which agent created what, from what input)
  - Replay or A/B-test individual agents on identical input
  - Cache expensive artifacts across runs
  - Drive the future Mission Control UI from a single source of truth

Each artifact carries:

  - `version`              — the artifact-schema version (NOT the agent version)
  - `created_by_agent`     — the agent that produced this artifact
  - `parent_artifact_ids`  — ancestor artifact ids (for lineage / replay)
  - `created_at`           — ISO-8601 UTC timestamp
  - `application_id`       — the application this artifact belongs to
  - `confidence`           — agent's self-reported confidence (0–1)
  - `evidence_tier`        — strongest evidence tier underpinning this artifact

These are deliberately Pydantic v2 models so we get:
  - Field-level validation
  - JSON (de)serialisation for the `agent_artifacts.content` jsonb column
  - IDE/refactor support through types
  - Automatic schema export for tools and the future Critic agent

Foundation only — no orchestration logic in this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────
#  Evidence tiers (mirrors the v3 evidence ledger)
# ─────────────────────────────────────────────────────────────────────────


class EvidenceTier(str, Enum):
    """Strongest available evidence supporting a claim or artifact."""
    VERBATIM = "verbatim"          # literal quote from a source document
    DERIVED = "derived"            # logically derived from one verbatim claim
    INFERRED = "inferred"          # multi-hop inference / generalisation
    USER_STATED = "user_stated"    # asserted by the user; no external source
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────────────────────────────────
#  Artifact base
# ─────────────────────────────────────────────────────────────────────────


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactBase(BaseModel):
    """Base for every typed artifact passed between agents."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Schema version for this artifact TYPE (bump when fields change shape).
    version: str = "1.0.0"

    # Agent that produced this artifact.
    created_by_agent: str = ""

    # Lineage: artifact ids this one was derived from (in order).
    parent_artifact_ids: List[str] = Field(default_factory=list)

    # Wall-clock creation time (UTC, ISO-8601).
    created_at: str = Field(default_factory=_utcnow)

    # Application this artifact belongs to (None = global / cross-application).
    application_id: Optional[str] = None

    # Agent's self-reported confidence in this artifact, 0..1.
    confidence: float = 1.0

    # Strongest evidence tier underpinning the artifact's claims.
    evidence_tier: EvidenceTier = EvidenceTier.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────
#  Atlas: BenchmarkProfile
# ─────────────────────────────────────────────────────────────────────────


class BenchmarkSkill(BaseModel):
    name: str
    level: Literal["expert", "advanced", "intermediate", "beginner"] = "intermediate"
    years: int = 0
    category: Literal["technical", "soft", "domain"] = "technical"
    importance: Literal["critical", "important", "preferred"] = "important"


class BenchmarkProfile(ArtifactBase):
    """Atlas output — the ideal-candidate profile for a specific job."""

    job_title: str
    company: str
    summary: str = ""
    years_experience: int = 0
    skills: List[BenchmarkSkill] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    education: List[Dict[str, Any]] = Field(default_factory=list)
    experience: List[Dict[str, Any]] = Field(default_factory=list)
    scoring_weights: Dict[str, float] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
#  Recon: CompanyIntelReport
# ─────────────────────────────────────────────────────────────────────────


class CompanyIntelSource(BaseModel):
    name: str
    url: Optional[str] = None
    status: Literal["completed", "warning", "failed", "skipped"] = "completed"


class CompanyIntelReport(ArtifactBase):
    """Recon output — everything we know about the company before generation."""

    company: str
    summary: str = ""
    industry: str = ""
    sources: List[CompanyIntelSource] = Field(default_factory=list)
    culture_signals: List[str] = Field(default_factory=list)
    recent_news: List[Dict[str, Any]] = Field(default_factory=list)
    leadership: List[Dict[str, Any]] = Field(default_factory=list)
    funding_status: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
#  Cipher: SkillGapMap
# ─────────────────────────────────────────────────────────────────────────


class SkillGap(BaseModel):
    skill: str
    user_level: Literal["expert", "advanced", "intermediate", "beginner", "none"] = "none"
    target_level: Literal["expert", "advanced", "intermediate", "beginner"] = "intermediate"
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    closeable_in_weeks: Optional[int] = None
    closing_strategy: Optional[str] = None


class SkillStrength(BaseModel):
    area: str
    evidence: str = ""


class SkillGapMap(ArtifactBase):
    """Cipher output — gap and strength inventory for the candidate vs. benchmark."""

    overall_alignment: float = 0.0  # 0..1
    gaps: List[SkillGap] = Field(default_factory=list)
    strengths: List[SkillStrength] = Field(default_factory=list)
    transferable_skills: List[str] = Field(default_factory=list)
    risk_areas: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
#  Cipher / Quill: LearningRecommendationSet
# ─────────────────────────────────────────────────────────────────────────


class LearningResource(BaseModel):
    title: str
    provider: str = ""
    url: Optional[str] = None
    cost: Optional[str] = None
    duration_hours: Optional[int] = None
    addresses_skill: Optional[str] = None


class LearningRecommendationSet(ArtifactBase):
    """Cipher/Quill output — the actionable upskilling plan."""

    focus: str = ""
    horizon_weeks: int = 12
    resources: List[LearningResource] = Field(default_factory=list)
    weekly_plan: List[Dict[str, Any]] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
#  Quill / Forge / Cipher: document bundles
# ─────────────────────────────────────────────────────────────────────────


class DocumentRecord(BaseModel):
    """A single generated document."""

    doc_type: str
    label: str
    html_content: str = ""
    word_count: int = 0
    quality_score: float = 0.0
    issues: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class BenchmarkDocumentBundle(ArtifactBase):
    """Cipher/Atlas output — the canonical benchmark document set.

    Canonical 6-doc benchmark base set: cv, resume, cover_letter,
    personal_statement, portfolio, learning_plan.
    """

    documents: Dict[str, DocumentRecord] = Field(default_factory=dict)


class TailoredDocumentBundle(ArtifactBase):
    """Quill/Forge output — the tailored, JD-personalised document set."""

    documents: Dict[str, DocumentRecord] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
#  Sentinel: ValidationReport
# ─────────────────────────────────────────────────────────────────────────


class ValidationFinding(BaseModel):
    severity: Literal["error", "warning", "info"] = "warning"
    target_doc_type: str = ""
    rule: str
    message: str
    suggestion: Optional[str] = None


class ValidationReport(ArtifactBase):
    """Sentinel output — quality + factuality + brand-consistency findings."""

    overall_score: float = 0.0  # 0..100
    findings: List[ValidationFinding] = Field(default_factory=list)
    docs_passed: List[str] = Field(default_factory=list)
    docs_failed: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
#  Nova: FinalApplicationPack
# ─────────────────────────────────────────────────────────────────────────


class FinalApplicationPack(ArtifactBase):
    """Nova output — the assembled, validated, ready-to-send application."""

    benchmark: Optional[BenchmarkProfile] = None
    company_intel: Optional[CompanyIntelReport] = None
    gap_map: Optional[SkillGapMap] = None
    learning_plan: Optional[LearningRecommendationSet] = None
    benchmark_docs: Optional[BenchmarkDocumentBundle] = None
    tailored_docs: Optional[TailoredDocumentBundle] = None
    validation: Optional[ValidationReport] = None
    failed_modules: List[Dict[str, Any]] = Field(default_factory=list)
    elapsed_seconds: float = 0.0


# ─────────────────────────────────────────────────────────────────────────
#  Planner: BuildPlan + StagePlan
# ─────────────────────────────────────────────────────────────────────────


class StagePlan(BaseModel):
    """One node in the BuildPlan DAG."""

    model_config = ConfigDict(extra="forbid")

    stage_id: str                                     # e.g. "atlas.benchmark"
    agent_name: str                                   # e.g. "atlas"
    description: str = ""
    depends_on: List[str] = Field(default_factory=list)  # other stage_ids
    expected_artifact_type: Optional[str] = None      # name in ARTIFACT_TYPES
    optional: bool = False                            # if true, failure → skip
    weight: float = 1.0                               # for progress calculation
    timeout_s: float = 300.0


class BuildPlan(ArtifactBase):
    """Planner output — the full execution DAG for a single application build.

    The Executor consults this plan to:
      - Schedule stages respecting dependencies
      - Compute truthful progress weighted by stage.weight
      - Decide which stage failures kill the build vs. degrade gracefully
    """

    job_title: str = ""
    company: str = ""
    requested_modules: List[str] = Field(default_factory=list)
    stages: List[StagePlan] = Field(default_factory=list)
    rationale: str = ""

    def total_weight(self) -> float:
        return sum(s.weight for s in self.stages) or 1.0

    def stage(self, stage_id: str) -> Optional[StagePlan]:
        return next((s for s in self.stages if s.stage_id == stage_id), None)


# ─────────────────────────────────────────────────────────────────────────
#  Helpers — used by the future orchestrator's persistence layer
# ─────────────────────────────────────────────────────────────────────────


ARTIFACT_TYPES: Dict[str, type[ArtifactBase]] = {
    "BenchmarkProfile": BenchmarkProfile,
    "CompanyIntelReport": CompanyIntelReport,
    "SkillGapMap": SkillGapMap,
    "LearningRecommendationSet": LearningRecommendationSet,
    "BenchmarkDocumentBundle": BenchmarkDocumentBundle,
    "TailoredDocumentBundle": TailoredDocumentBundle,
    "ValidationReport": ValidationReport,
    "FinalApplicationPack": FinalApplicationPack,
    "BuildPlan": BuildPlan,
}


def artifact_for_type(name: str) -> Optional[type[ArtifactBase]]:
    """Look up an artifact class by its type name."""
    return ARTIFACT_TYPES.get(name)
