"""S6-F2 — Pin ai_engine/agents/validation_critic.py contracts.

ValidationCritic is THE gate that decides if a module transitions to
COMPLETED or FAILED. A drift here either lets bad output pass
(regression visible to users) or fails healthy output (false-negative
rate). Per S6 charter: "Critic gates cover all 5 review modes" —
this test pins all 5 explicitly.

Pure logic, zero LLM calls — uses real artifact_contracts dataclasses.
"""
from __future__ import annotations

import pytest

from ai_engine.agents.artifact_contracts import (
    BenchmarkProfile,
    BenchmarkSkill,
    BuildPlan,
    DocumentRecord,
    EvidenceTier,
    FinalApplicationPack,
    SkillGap,
    SkillGapMap,
    SkillStrength,
    StagePlan,
    TailoredDocumentBundle,
    ValidationReport,
)
from ai_engine.agents.validation_critic import ValidationCritic, report_passed


@pytest.fixture
def critic():
    return ValidationCritic()


# ════════════════════════════════════════════════════════════════════
# review_benchmark — Stage 1 gate
# ════════════════════════════════════════════════════════════════════
class TestReviewBenchmark:
    def test_missing_artifact_fails_with_error(self, critic):
        report = critic.review_benchmark(None)
        assert any(f.severity == "error" and f.rule == "benchmark.missing"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_complete_artifact_passes(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme",
            summary="A solid summary line.",
            skills=[BenchmarkSkill(name="Python")],
            experience=[{"title": "Engineer"}],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_benchmark(bp)
        assert report_passed(report) is True
        # No error findings
        assert all(f.severity != "error" for f in report.findings)

    def test_empty_summary_warns(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme",
            summary="",  # empty
            skills=[BenchmarkSkill(name="Python")],
            experience=[{"x": 1}],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_benchmark(bp)
        assert any(f.rule == "benchmark.summary_empty" and f.severity == "warning"
                   for f in report.findings)
        # Warnings don't fail the gate
        assert report_passed(report) is True

    def test_empty_skills_warns(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme",
            summary="OK", skills=[], experience=[{"x": 1}],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_benchmark(bp)
        assert any(f.rule == "benchmark.skills_empty" for f in report.findings)

    def test_empty_experience_warns(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme",
            summary="OK", skills=[BenchmarkSkill(name="Py")], experience=[],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_benchmark(bp)
        assert any(f.rule == "benchmark.experience_empty" for f in report.findings)


# ════════════════════════════════════════════════════════════════════
# review_gap_map — Stage 2 gate
# ════════════════════════════════════════════════════════════════════
class TestReviewGapMap:
    def test_missing_artifact_fails(self, critic):
        report = critic.review_gap_map(None)
        assert any(f.rule == "gap_map.missing" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_complete_gap_map_passes(self, critic):
        gm = SkillGapMap(
            overall_alignment=0.75,
            gaps=[SkillGap(skill="K8s")],
            strengths=[SkillStrength(area="Python")],
            transferable_skills=["Linux"],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_gap_map(gm)
        assert report_passed(report) is True

    def test_completely_empty_gap_map_warns(self, critic):
        gm = SkillGapMap(
            overall_alignment=0.5,
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_gap_map(gm)
        assert any(f.rule == "gap_map.empty" for f in report.findings)
        # Empty is a warning, not an error
        assert report_passed(report) is True

    def test_zero_alignment_warns(self, critic):
        gm = SkillGapMap(
            overall_alignment=0.0,
            gaps=[SkillGap(skill="X")],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_gap_map(gm)
        assert any(f.rule == "gap_map.no_alignment_score" for f in report.findings)


# ════════════════════════════════════════════════════════════════════
# review_documents — document bundle gate
# ════════════════════════════════════════════════════════════════════
class TestReviewDocuments:
    def test_missing_bundle_fails(self, critic):
        report = critic.review_documents(None)
        assert any(f.rule == "documents.missing" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_empty_bundle_fails(self, critic):
        bundle = TailoredDocumentBundle(documents={}, evidence_tier=EvidenceTier.DERIVED)
        report = critic.review_documents(bundle)
        assert any(f.rule == "documents.no_outputs" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_documents_with_content_pass(self, critic):
        bundle = TailoredDocumentBundle(
            documents={
                "cv": DocumentRecord(doc_type="cv", label="CV", html_content="<p>hi</p>"),
                "cover_letter": DocumentRecord(
                    doc_type="cover_letter", label="CL", html_content="<p>dear</p>",
                ),
            },
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_documents(bundle)
        assert report_passed(report) is True
        assert "cv" in report.docs_passed
        assert "cover_letter" in report.docs_passed
        assert report.docs_failed == []

    def test_empty_html_content_fails_doc(self, critic):
        bundle = TailoredDocumentBundle(
            documents={
                "cv": DocumentRecord(doc_type="cv", label="CV", html_content=""),
            },
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_documents(bundle)
        assert "cv" in report.docs_failed
        assert any(f.rule == "documents.cv.empty" for f in report.findings)

    def test_whitespace_only_content_fails_doc(self, critic):
        bundle = TailoredDocumentBundle(
            documents={
                "cv": DocumentRecord(doc_type="cv", label="CV", html_content="   \n\t"),
            },
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_documents(bundle)
        assert "cv" in report.docs_failed

    def test_required_modules_missing_fails(self, critic):
        bundle = TailoredDocumentBundle(
            documents={
                "cv": DocumentRecord(doc_type="cv", label="CV", html_content="<p>hi</p>"),
            },
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_documents(bundle, required_modules=["cv", "cover_letter"])
        assert any(f.rule == "documents.cover_letter.missing" and f.severity == "error"
                   for f in report.findings)
        assert "cover_letter" in report.docs_failed
        assert report_passed(report) is False

    def test_required_modules_normalized_lowercase(self, critic):
        bundle = TailoredDocumentBundle(
            documents={
                "cv": DocumentRecord(doc_type="cv", label="CV", html_content="<p>hi</p>"),
            },
            evidence_tier=EvidenceTier.DERIVED,
        )
        # CV in upper-case should normalise to cv and be found
        report = critic.review_documents(bundle, required_modules=["CV"])
        assert report_passed(report) is True


# ════════════════════════════════════════════════════════════════════
# review_final_pack — pipeline completion gate
# ════════════════════════════════════════════════════════════════════
class TestReviewFinalPack:
    def test_missing_pack_fails(self, critic):
        report = critic.review_final_pack(None)
        assert any(f.rule == "final_pack.missing" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_pack_without_any_docs_fails(self, critic):
        pack = FinalApplicationPack(evidence_tier=EvidenceTier.DERIVED)
        report = critic.review_final_pack(pack)
        assert any(f.rule == "final_pack.no_docs" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_pack_with_tailored_docs_passes(self, critic):
        pack = FinalApplicationPack(
            tailored_docs=TailoredDocumentBundle(
                documents={"cv": DocumentRecord(doc_type="cv", label="CV", html_content="<p>x</p>")},
                evidence_tier=EvidenceTier.DERIVED,
            ),
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_final_pack(pack)
        assert report_passed(report) is True

    def test_failed_modules_emit_warnings(self, critic):
        pack = FinalApplicationPack(
            tailored_docs=TailoredDocumentBundle(
                documents={"cv": DocumentRecord(doc_type="cv", label="CV", html_content="<p>x</p>")},
                evidence_tier=EvidenceTier.DERIVED,
            ),
            failed_modules=[
                {"module": "cover_letter", "error": "LLM timeout"},
                {"module": "personal_statement", "error": "schema fail"},
            ],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_final_pack(pack)
        # Failures are warnings, not errors → still passes
        assert report_passed(report) is True
        warning_rules = [f.rule for f in report.findings if f.severity == "warning"]
        assert "final_pack.cover_letter.failed" in warning_rules
        assert "final_pack.personal_statement.failed" in warning_rules

    def test_failed_module_error_truncated_to_200(self, critic):
        long_err = "X" * 500
        pack = FinalApplicationPack(
            tailored_docs=TailoredDocumentBundle(
                documents={"cv": DocumentRecord(doc_type="cv", label="CV", html_content="<p>x</p>")},
                evidence_tier=EvidenceTier.DERIVED,
            ),
            failed_modules=[{"module": "cv", "error": long_err}],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_final_pack(pack)
        msg = next(f.message for f in report.findings if f.rule == "final_pack.cv.failed")
        # 200 X's max
        assert msg.count("X") <= 200


# ════════════════════════════════════════════════════════════════════
# review_plan — DAG dependency gate
# ════════════════════════════════════════════════════════════════════
class TestReviewPlan:
    def test_missing_plan_fails(self, critic):
        report = critic.review_plan(None)
        assert any(f.rule == "plan.missing" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_empty_stages_fails(self, critic):
        plan = BuildPlan(stages=[], evidence_tier=EvidenceTier.DERIVED)
        report = critic.review_plan(plan)
        assert any(f.rule == "plan.empty" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False

    def test_well_formed_plan_passes(self, critic):
        plan = BuildPlan(
            stages=[
                StagePlan(stage_id="a", agent_name="atlas"),
                StagePlan(stage_id="b", agent_name="cipher", depends_on=["a"]),
            ],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_plan(plan)
        assert report_passed(report) is True

    def test_bad_dependency_fails(self, critic):
        plan = BuildPlan(
            stages=[
                StagePlan(stage_id="a", agent_name="atlas",
                          depends_on=["nonexistent"]),
            ],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_plan(plan)
        assert any(f.rule == "plan.bad_dependency" and f.severity == "error"
                   for f in report.findings)
        assert report_passed(report) is False


# ════════════════════════════════════════════════════════════════════
# Internal scoring math — _finalize, _gate_meta, _tier_meets
# ════════════════════════════════════════════════════════════════════
class TestScoringMath:
    def test_perfect_report_scores_100(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme", summary="OK",
            skills=[BenchmarkSkill(name="Py")],
            experience=[{"x": 1}],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_benchmark(bp)
        assert report.overall_score == 100.0

    def test_one_error_subtracts_25(self, critic):
        # Missing artifact = 1 error finding only
        report = critic.review_benchmark(None)
        # Pure 1 error → 100 - 25 = 75
        assert report.overall_score == 75.0

    def test_one_warning_subtracts_5(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme", summary="",  # 1 warning
            skills=[BenchmarkSkill(name="Py")],
            experience=[{"x": 1}],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_benchmark(bp)
        assert report.overall_score == 95.0

    def test_score_floors_at_zero(self, critic):
        # Plan missing = 1 error (-25), no other findings. To hit zero we
        # need 4 errors. Stack via empty + bad-dependency on multi-stage plan.
        plan = BuildPlan(
            stages=[
                StagePlan(stage_id="a", agent_name="atlas",
                          depends_on=["x", "y", "z"]),  # 3 bad deps
            ],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report = critic.review_plan(plan)
        # 3 bad-deps × -25 = -75. Score = 25. Not yet zero — add another.
        plan2 = BuildPlan(
            stages=[
                StagePlan(stage_id="a", agent_name="atlas",
                          depends_on=["x", "y", "z", "w", "u"]),  # 5 bad deps
            ],
            evidence_tier=EvidenceTier.DERIVED,
        )
        report2 = critic.review_plan(plan2)
        assert report2.overall_score == 0.0  # max(0, 100 - 125)


class TestGateMeta:
    def test_low_confidence_warns(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme", summary="OK",
            skills=[BenchmarkSkill(name="Py")], experience=[{"x": 1}],
            evidence_tier=EvidenceTier.DERIVED,
            confidence=0.2,  # below 0.4
        )
        report = critic.review_benchmark(bp)
        assert any(f.rule == "meta.low_confidence" for f in report.findings)

    def test_high_confidence_no_warning(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme", summary="OK",
            skills=[BenchmarkSkill(name="Py")], experience=[{"x": 1}],
            evidence_tier=EvidenceTier.DERIVED,
            confidence=0.9,
        )
        report = critic.review_benchmark(bp)
        assert not any(f.rule == "meta.low_confidence" for f in report.findings)

    def test_weak_evidence_tier_warns(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme", summary="OK",
            skills=[BenchmarkSkill(name="Py")], experience=[{"x": 1}],
            evidence_tier=EvidenceTier.UNKNOWN,  # below INFERRED
        )
        report = critic.review_benchmark(bp)
        assert any(f.rule == "meta.weak_evidence" for f in report.findings)

    def test_user_stated_tier_warns(self, critic):
        # USER_STATED is below INFERRED
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme", summary="OK",
            skills=[BenchmarkSkill(name="Py")], experience=[{"x": 1}],
            evidence_tier=EvidenceTier.USER_STATED,
        )
        report = critic.review_benchmark(bp)
        assert any(f.rule == "meta.weak_evidence" for f in report.findings)

    def test_inferred_tier_passes_meta(self, critic):
        bp = BenchmarkProfile(
            job_title="SWE", company="Acme", summary="OK",
            skills=[BenchmarkSkill(name="Py")], experience=[{"x": 1}],
            evidence_tier=EvidenceTier.INFERRED,
        )
        report = critic.review_benchmark(bp)
        assert not any(f.rule == "meta.weak_evidence" for f in report.findings)


class TestTierMeets:
    def test_ordering(self):
        c = ValidationCritic
        # VERBATIM ≥ DERIVED ≥ INFERRED ≥ USER_STATED ≥ UNKNOWN
        assert c._tier_meets(EvidenceTier.VERBATIM, EvidenceTier.DERIVED) is True
        assert c._tier_meets(EvidenceTier.DERIVED, EvidenceTier.INFERRED) is True
        assert c._tier_meets(EvidenceTier.INFERRED, EvidenceTier.INFERRED) is True
        assert c._tier_meets(EvidenceTier.USER_STATED, EvidenceTier.INFERRED) is False
        assert c._tier_meets(EvidenceTier.UNKNOWN, EvidenceTier.INFERRED) is False

    def test_string_value_accepted(self):
        # The function accepts the enum's string value too
        assert ValidationCritic._tier_meets("derived", EvidenceTier.INFERRED) is True

    def test_garbage_value_returns_false(self):
        assert ValidationCritic._tier_meets("not-a-tier", EvidenceTier.INFERRED) is False


# ════════════════════════════════════════════════════════════════════
# report_passed helper
# ════════════════════════════════════════════════════════════════════
class TestReportPassed:
    def test_none_report_does_not_pass(self):
        assert report_passed(None) is False

    def test_empty_findings_passes(self):
        report = ValidationReport(created_by_agent="t")
        assert report_passed(report) is True

    def test_warnings_only_passes(self):
        from ai_engine.agents.artifact_contracts import ValidationFinding
        report = ValidationReport(
            created_by_agent="t",
            findings=[
                ValidationFinding(severity="warning", rule="r1", message="m"),
                ValidationFinding(severity="info", rule="r2", message="m"),
            ],
        )
        assert report_passed(report) is True

    def test_any_error_fails(self):
        from ai_engine.agents.artifact_contracts import ValidationFinding
        report = ValidationReport(
            created_by_agent="t",
            findings=[
                ValidationFinding(severity="warning", rule="r1", message="m"),
                ValidationFinding(severity="error", rule="r2", message="m"),
            ],
        )
        assert report_passed(report) is False
