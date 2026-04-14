from unittest.mock import MagicMock

from ai_engine.agents.pipelines import benchmark_pipeline, resume_parse_pipeline
from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain
from ai_engine.chains.role_profiler import RoleProfilerChain


def test_resume_parse_pipeline_disables_researcher_fanout():
    pipeline = resume_parse_pipeline(ai_client=MagicMock())
    assert pipeline.researcher is None


def test_benchmark_pipeline_uses_atlas_specific_sub_agents():
    pipeline = benchmark_pipeline(ai_client=MagicMock())
    assert pipeline.researcher is not None
    names = [sa.name for sa in pipeline.researcher._sub_agents]
    assert names == ["jd_analyst", "profile_match"]


def test_role_profiler_adds_parse_confidence_and_warnings():
    chain = RoleProfilerChain(ai_client=MagicMock())
    parsed = chain._validate_result({
        "name": "",
        "contact_info": {},
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
        "languages": [],
        "achievements": [],
    })

    assert "parse_confidence" in parsed
    assert isinstance(parsed["parse_confidence"], float)
    assert 0.0 <= parsed["parse_confidence"] <= 1.0
    assert "parse_warnings" in parsed
    assert isinstance(parsed["parse_warnings"], list)
    assert parsed["parse_warnings"]


def test_benchmark_builder_validates_and_caps_profile_payload():
    chain = BenchmarkBuilderChain(ai_client=MagicMock())
    raw = {
        "ideal_profile": {},
        "ideal_skills": [{"name": str(i)} for i in range(25)],
        "ideal_experience": [{"company": str(i)} for i in range(10)],
        "ideal_education": [{"institution": str(i)} for i in range(5)],
        "ideal_certifications": [{"name": str(i)} for i in range(8)],
        "soft_skills": [{"skill": str(i)} for i in range(9)],
        "industry_knowledge": [{"area": str(i)} for i in range(7)],
        "scoring_weights": {"a": 0.5, "b": 0.2},
    }

    validated = chain._validate_ideal_profile(raw)

    assert len(validated["ideal_skills"]) == 10
    assert len(validated["ideal_experience"]) == 3
    assert len(validated["ideal_education"]) == 2
    assert len(validated["ideal_certifications"]) == 5
    assert len(validated["soft_skills"]) == 6
    assert len(validated["industry_knowledge"]) == 4

    assert "benchmark_quality_flags" in validated
    assert "benchmark_quality_score" in validated
    assert 0.0 <= validated["benchmark_quality_score"] <= 1.0


def test_format_response_includes_atlas_diagnostics():
    from app.api.routes.generate.helpers import _format_response, _build_atlas_diagnostics

    user_profile = {
        "parse_confidence": 0.42,
        "parse_warnings": ["Low skill extraction density"],
    }
    benchmark_data = {
        "benchmark_quality_score": 0.65,
        "benchmark_quality_flags": ["weight_sum_not_1"],
    }

    resp = _format_response(
        benchmark_data=benchmark_data,
        gap_analysis={},
        roadmap={},
        cv_html="",
        cl_html="",
        ps_html="",
        portfolio_html="",
        validation={},
        keywords=[],
        job_title="Engineer",
        atlas_diagnostics=_build_atlas_diagnostics(user_profile, benchmark_data),
    )

    assert "atlas" in resp
    assert resp["atlas"]["parseConfidence"] == 0.42
    assert resp["atlas"]["safeMode"] is True
