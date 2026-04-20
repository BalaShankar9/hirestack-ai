"""
ValidationCritic — schema + content gate for typed agent artifacts.

The Critic runs at stage boundaries in the v4 pipeline. Its job is to
prevent the runtime from advancing the application/module state machine
on the basis of bad output. Concretely, no module may transition to
COMPLETED without a passing ValidationReport — failures transition the
module to FAILED with a reason.

Distinct from the legacy `CriticAgent` in ai_engine/agents/critic.py
(which is the LLM judge inside the gap_analysis pipeline). This Critic
operates over typed artifacts at runtime stage boundaries.
"""
from __future__ import annotations

from typing import Any, List, Optional

import structlog

from ai_engine.agents.artifact_contracts import (
    ArtifactBase,
    BenchmarkProfile,
    BuildPlan,
    EvidenceTier,
    FinalApplicationPack,
    SkillGapMap,
    TailoredDocumentBundle,
    ValidationFinding,
    ValidationReport,
)

logger = structlog.get_logger(__name__)


_MIN_CONFIDENCE = 0.4
_MIN_TIER = EvidenceTier.INFERRED


class ValidationCritic:
    """Runs validation gates over typed artifacts."""

    def __init__(self, *, agent_name: str = "validation_critic") -> None:
        self._agent_name = agent_name

    # ── public surface ────────────────────────────────────────────────

    def review_benchmark(self, artifact: Optional[BenchmarkProfile]) -> ValidationReport:
        report = self._new_report(artifact)
        if artifact is None:
            self._fail(report, rule="benchmark.missing",
                       message="No BenchmarkProfile artifact produced.")
            return self._finalize(report)

        if not (artifact.summary or "").strip():
            self._warn(report, rule="benchmark.summary_empty",
                       message="Benchmark profile has no summary.")
        if not artifact.skills:
            self._warn(report, rule="benchmark.skills_empty",
                       message="Benchmark profile has no skills extracted.")
        if not artifact.experience:
            self._warn(report, rule="benchmark.experience_empty",
                       message="Benchmark profile has no experience entries.")
        self._gate_meta(report, artifact)
        return self._finalize(report)

    def review_gap_map(self, artifact: Optional[SkillGapMap]) -> ValidationReport:
        report = self._new_report(artifact)
        if artifact is None:
            self._fail(report, rule="gap_map.missing",
                       message="No SkillGapMap artifact produced.")
            return self._finalize(report)

        total = (
            len(artifact.gaps)
            + len(artifact.strengths)
            + len(artifact.transferable_skills)
        )
        if total == 0:
            self._warn(report, rule="gap_map.empty",
                       message="Gap map has no gaps/strengths/transferable_skills.")
        if (artifact.overall_alignment or 0.0) <= 0.0:
            self._warn(report, rule="gap_map.no_alignment_score",
                       message="Gap map overall_alignment is zero — likely not computed.")
        self._gate_meta(report, artifact)
        return self._finalize(report)

    def review_documents(
        self,
        artifact: Optional[TailoredDocumentBundle],
        *,
        required_modules: Optional[List[str]] = None,
    ) -> ValidationReport:
        report = self._new_report(artifact)
        if artifact is None:
            self._fail(report, rule="documents.missing",
                       message="No TailoredDocumentBundle artifact produced.")
            return self._finalize(report)

        produced = artifact.documents or {}
        if not produced:
            self._fail(report, rule="documents.no_outputs",
                       message="Document bundle is empty.")
        else:
            for mod, rec in produced.items():
                has_content = bool((getattr(rec, "html_content", "") or "").strip())
                if has_content:
                    report.docs_passed.append(mod)
                else:
                    report.docs_failed.append(mod)
                    self._warn(report, rule=f"documents.{mod}.empty",
                               target_doc=mod,
                               message=f"Module '{mod}' has no html content.")

        if required_modules:
            for mod in required_modules:
                key = self._normalize_mod(mod)
                if key and key not in produced:
                    report.docs_failed.append(key)
                    self._fail(report, rule=f"documents.{key}.missing",
                               target_doc=key,
                               message=f"Required module '{key}' is missing from bundle.")
        self._gate_meta(report, artifact)
        return self._finalize(report)

    def review_final_pack(self, artifact: Optional[FinalApplicationPack]) -> ValidationReport:
        report = self._new_report(artifact)
        if artifact is None:
            self._fail(report, rule="final_pack.missing",
                       message="No FinalApplicationPack artifact produced.")
            return self._finalize(report)

        if artifact.tailored_docs is None and artifact.benchmark_docs is None:
            self._fail(report, rule="final_pack.no_docs",
                       message="FinalApplicationPack contains no document bundles.")

        if artifact.failed_modules:
            for fm in artifact.failed_modules:
                mod = str((fm or {}).get("module", "unknown"))
                err = str((fm or {}).get("error", ""))[:200]
                self._warn(report, rule=f"final_pack.{mod}.failed",
                           target_doc=mod,
                           message=f"Module '{mod}' failed: {err}")
        self._gate_meta(report, artifact)
        return self._finalize(report)

    def review_plan(self, artifact: Optional[BuildPlan]) -> ValidationReport:
        report = self._new_report(artifact)
        if artifact is None:
            self._fail(report, rule="plan.missing",
                       message="No BuildPlan artifact provided.")
            return self._finalize(report)
        if not artifact.stages:
            self._fail(report, rule="plan.empty",
                       message="BuildPlan has no stages.")
        ids = {s.stage_id for s in artifact.stages}
        for s in artifact.stages:
            for dep in s.depends_on:
                if dep not in ids:
                    self._fail(report, rule="plan.bad_dependency",
                               message=f"Stage '{s.stage_id}' depends on missing '{dep}'.")
        return self._finalize(report)

    # ── internals ─────────────────────────────────────────────────────

    def _new_report(self, source: Optional[ArtifactBase]) -> ValidationReport:
        return ValidationReport(
            application_id=getattr(source, "application_id", None) if source else None,
            created_by_agent=self._agent_name,
            confidence=1.0,
            evidence_tier=EvidenceTier.DERIVED,
            findings=[],
            docs_passed=[],
            docs_failed=[],
            overall_score=100.0,
        )

    @staticmethod
    def _fail(report: ValidationReport, *, rule: str, message: str,
              target_doc: str = "") -> None:
        report.findings.append(ValidationFinding(
            severity="error", rule=rule, message=message,
            target_doc_type=target_doc,
        ))

    @staticmethod
    def _warn(report: ValidationReport, *, rule: str, message: str,
              target_doc: str = "") -> None:
        report.findings.append(ValidationFinding(
            severity="warning", rule=rule, message=message,
            target_doc_type=target_doc,
        ))

    def _gate_meta(self, report: ValidationReport, artifact: ArtifactBase) -> None:
        if (artifact.confidence or 0.0) < _MIN_CONFIDENCE:
            self._warn(report, rule="meta.low_confidence",
                       message=f"Artifact confidence {artifact.confidence:.2f} below {_MIN_CONFIDENCE}.")
        if not self._tier_meets(artifact.evidence_tier, _MIN_TIER):
            tier_str = (
                artifact.evidence_tier.value
                if isinstance(artifact.evidence_tier, EvidenceTier)
                else str(artifact.evidence_tier)
            )
            self._warn(report, rule="meta.weak_evidence",
                       message=f"Artifact evidence tier '{tier_str}' below '{_MIN_TIER.value}'.")

    @staticmethod
    def _tier_meets(actual: Any, minimum: EvidenceTier) -> bool:
        order = [
            EvidenceTier.UNKNOWN,
            EvidenceTier.USER_STATED,
            EvidenceTier.INFERRED,
            EvidenceTier.DERIVED,
            EvidenceTier.VERBATIM,
        ]
        try:
            actual_v = actual if isinstance(actual, EvidenceTier) else EvidenceTier(str(actual))
        except Exception:
            return False
        try:
            return order.index(actual_v) >= order.index(minimum)
        except ValueError:
            return False

    @staticmethod
    def _finalize(report: ValidationReport) -> ValidationReport:
        errors = sum(1 for f in report.findings if f.severity == "error")
        warns = sum(1 for f in report.findings if f.severity == "warning")
        report.overall_score = max(0.0, 100.0 - 25.0 * errors - 5.0 * warns)
        return report

    @staticmethod
    def _normalize_mod(mod: str) -> str:
        return (mod or "").strip().lower()


def report_passed(report: Optional[ValidationReport]) -> bool:
    """A report passes if it has zero error-severity findings."""
    if report is None:
        return False
    return not any(f.severity == "error" for f in report.findings)
