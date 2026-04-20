"""Phase-C anchor tests: typed intermediate artifacts + per-stage critic gates.

These tests pin the dedicated Phase C hardening slice:
1) PipelineRuntime builds typed artifacts at intermediate boundaries.
2) Agent pipeline calls the critic at stage boundaries (atlas/cipher/quill/forge/sentinel/nova).
3) Sentinel critic summary is the canonical validation block stamped into response.

We intentionally combine behavior tests (helpers returning typed artifacts) and
source anchors (call-site presence) so regressions fail loudly even if a future
refactor bypasses runtime integration tests.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

# Ensure project roots are importable
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ai_engine.agents.artifact_contracts import (  # noqa: E402
    BenchmarkProfile,
    FinalApplicationPack,
    SkillGapMap,
    TailoredDocumentBundle,
)
from app.services.pipeline_runtime import PipelineRuntime  # noqa: E402


def test_build_benchmark_profile_artifact_returns_typed_model():
    artifact = PipelineRuntime._build_benchmark_profile_artifact(
        job_title="Senior Backend Engineer",
        company="HireStack",
        benchmark_data={
            "ideal_profile": {"summary": "Strong distributed systems background", "years_experience": 6},
            "ideal_skills": [
                {"name": "Python", "level": "expert", "importance": "critical", "years": 5},
                {"name": "FastAPI", "level": "advanced", "importance": "important"},
            ],
            "scoring_weights": {"skills": 0.5, "experience": 0.5},
        },
    )
    assert isinstance(artifact, BenchmarkProfile)
    assert artifact.job_title == "Senior Backend Engineer"
    assert artifact.company == "HireStack"
    assert len(artifact.skills) == 2


def test_build_skill_gap_map_artifact_returns_typed_model():
    artifact = PipelineRuntime._build_skill_gap_map_artifact(
        gap_analysis={
            "compatibility_score": 78,
            "skill_gaps": [
                {
                    "skill": "Kubernetes",
                    "current_level": "beginner",
                    "required_level": "advanced",
                    "gap_severity": "high",
                    "recommendation": "Build and operate a production cluster",
                }
            ],
            "strengths": [{"area": "Python", "description": "Deep async experience"}],
            "transferable_skills": ["Distributed systems"],
            "risk_areas": ["Infrastructure operations"],
        }
    )
    assert isinstance(artifact, SkillGapMap)
    assert artifact.overall_alignment == 0.78
    assert len(artifact.gaps) == 1
    assert artifact.gaps[0].skill == "Kubernetes"


def test_build_tailored_bundle_artifact_returns_typed_model():
    artifact = PipelineRuntime._build_tailored_bundle_artifact(
        cv_html="<p>cv</p>",
        cl_html="<p>cover letter</p>",
        ps_html="",
        portfolio_html="<p>portfolio</p>",
        resume_html="<p>resume</p>",
        application_id="app-123",
        created_by_agent="forge",
    )
    assert isinstance(artifact, TailoredDocumentBundle)
    assert artifact.application_id == "app-123"
    assert set(artifact.documents.keys()) == {"cv", "cover_letter", "portfolio", "resume"}


def test_build_final_pack_artifact_returns_typed_model():
    artifact = PipelineRuntime._build_final_pack_artifact(
        benchmark_data={
            "job_title": "Engineer",
            "company": "HireStack",
            "ideal_profile": {"summary": "Strong fit"},
            "ideal_skills": [{"name": "Python", "level": "expert", "importance": "critical"}],
        },
        gap_analysis={"compatibility_score": 85, "skill_gaps": [], "strengths": []},
        company="HireStack",
        company_intel={"summary": "AI hiring platform"},
        cv_html="<p>cv</p>",
        cl_html="<p>cl</p>",
        ps_html="<p>ps</p>",
        portfolio_html="<p>pf</p>",
        resume_html="<p>resume</p>",
        sentinel_validation={
            "passed": True,
            "overall_score": 91,
            "docs_passed": ["cv"],
            "docs_failed": [],
            "error_count": 0,
            "warning_count": 1,
            "finding_count": 1,
            "findings_summary": [
                {"code": "doc.warn", "severity": "warning", "message": "Minor issue", "doc_type": "cv"}
            ],
        },
        elapsed_seconds=12.4,
    )
    assert isinstance(artifact, FinalApplicationPack)
    assert artifact.benchmark is not None
    assert artifact.gap_map is not None
    assert artifact.tailored_docs is not None


def test_agent_pipeline_contains_all_phase_critic_gate_calls():
    src = inspect.getsource(PipelineRuntime._run_agent_pipeline)
    for phase in ("atlas", "cipher", "quill", "forge", "sentinel", "nova"):
        assert f'phase="{phase}"' in src, f"Missing phase critic gate wiring for {phase}."

    helper_calls = src.count("_run_critic_gate(")
    assert helper_calls >= 6, (
        "Expected per-stage critic calls for atlas/cipher/quill/forge/sentinel/nova; "
        f"only found {helper_calls}."
    )


def test_sentinel_gate_controls_response_validation_block():
    src = inspect.getsource(PipelineRuntime._run_agent_pipeline)
    assert "sentinel_validation = await self._run_critic_gate(" in src
    assert 'response["validation"] = sentinel_validation' in src


def test_critic_gate_helper_exists_and_emits_pass_fail_events():
    src = inspect.getsource(PipelineRuntime._run_critic_gate)
    assert 'event_type="validation_passed" if passed else "validation_failed"' in src
    assert "review_benchmark" in src
    assert "review_gap_map" in src
    assert "review_documents" in src
    assert "review_final_pack" in src
