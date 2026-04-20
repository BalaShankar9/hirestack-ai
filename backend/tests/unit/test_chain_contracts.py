"""Contract tests: pin auxiliary chain signatures so callers in the
service layer can't silently drift again. These tests inspect signatures
without invoking AI calls."""
from __future__ import annotations

import inspect

from ai_engine.chains.learning_challenge import LearningChallengeChain
from ai_engine.chains.salary_coach import SalaryCoachChain
from ai_engine.chains.interview_simulator import InterviewSimulatorChain
from ai_engine.chains.ats_scanner import ATSScannerChain


def _params(fn) -> dict[str, inspect.Parameter]:
    sig = inspect.signature(fn)
    return {name: p for name, p in sig.parameters.items() if name != "self"}


def test_learning_chain_exposes_generate_daily_set():
    """Service layer (LearningService) calls generate_daily_set; chain MUST
    expose it. Removing this method silently breaks the /learning route."""
    assert hasattr(LearningChallengeChain, "generate_daily_set"), (
        "LearningChallengeChain.generate_daily_set is required by "
        "backend/app/services/learning.py"
    )
    params = _params(LearningChallengeChain.generate_daily_set)
    for required in ("skills", "difficulty", "count", "job_context"):
        assert required in params, f"generate_daily_set missing param '{required}'"


def test_learning_generate_challenge_param_name():
    """Pin the canonical kwarg as `skill_name` (not `skill`)."""
    params = _params(LearningChallengeChain.generate_challenge)
    assert "skill_name" in params, "Renaming skill_name will break the chain prompt"


def test_salary_chain_uses_years_experience():
    """The chain expects `years_experience`. The service used to pass
    `experience_years` which was silently swallowed by **kwargs leaving
    the prompt with 0 years. This test guards that mistake."""
    params = _params(SalaryCoachChain.analyze_salary)
    assert "years_experience" in params, (
        "SalaryCoachChain.analyze_salary requires `years_experience`. "
        "Service callers must pass it under that exact name."
    )
    assert "experience_years" not in params, (
        "Two competing names is a footgun — keep only `years_experience`."
    )


def test_salary_service_passes_years_experience():
    """Lock the service caller to use the canonical kwarg."""
    import backend.app.services.salary as salary_service

    src = inspect.getsource(salary_service.SalaryService.analyze)
    assert "years_experience=" in src, (
        "backend/app/services/salary.py must call the chain with "
        "`years_experience=` to avoid silently dropping the value."
    )


def test_interview_chain_uses_jd_summary():
    """Chain takes `jd_summary`. Routes / services must convert any JD
    text input to that name before invoking the chain."""
    params = _params(InterviewSimulatorChain.generate_questions)
    assert "jd_summary" in params, "Renaming jd_summary breaks the chain"
    assert "jd_text" not in params, "jd_text is the route-side name only"


def test_ats_chain_required_inputs():
    """Pin the two real required inputs."""
    params = _params(ATSScannerChain.scan_document)
    assert "document_content" in params
    assert "jd_text" in params
    assert params["document_content"].default is inspect.Parameter.empty, (
        "document_content must remain required (no silent empty scans)"
    )
    assert params["jd_text"].default is inspect.Parameter.empty, (
        "jd_text must remain required"
    )
