"""Module whitelist enforcement tests — Rank 8.

The ``GenerationJobRequest`` validator must:
  - Accept all known snake_case and camelCase module names
  - Reject unknown module names (including SQL injection strings)
  - Reject an empty modules list (no-op requests)
  - Reject lists that contain even one unknown module
  - Reject oversized lists (> 20 modules)

``RetryModulesRequest`` shares the same whitelist and has the additional
constraint that an empty list is explicitly rejected.

Run with:
    pytest tests/unit/test_module_whitelist_enforcement.py -v
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.routes.generate.schemas import (
    ALLOWED_JOB_MODULES,
    GenerationJobRequest,
    RetryModulesRequest,
)

_VALID_APP_ID = "00000000-0000-4000-8000-000000000001"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_req(**kwargs) -> GenerationJobRequest:
    return GenerationJobRequest(application_id=_VALID_APP_ID, **kwargs)


def _make_retry(**kwargs) -> RetryModulesRequest:
    return RetryModulesRequest(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# GenerationJobRequest
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerationJobRequestModules:
    """Whitelist enforcement on GenerationJobRequest.requested_modules."""

    @pytest.mark.parametrize("module", sorted(ALLOWED_JOB_MODULES))
    def test_all_allowed_modules_accepted_individually(self, module: str) -> None:
        req = _make_req(requested_modules=[module])
        assert module in req.requested_modules

    def test_empty_modules_list_accepted(self) -> None:
        """An empty list means 'generate all defaults' — it is valid."""
        req = _make_req(requested_modules=[])
        assert req.requested_modules == []

    def test_multiple_valid_modules_accepted(self) -> None:
        req = _make_req(requested_modules=["cv", "coverLetter", "scorecard"])
        assert len(req.requested_modules) == 3

    def test_unknown_module_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _make_req(requested_modules=["unknown_module"])
        assert "Unknown module" in str(exc_info.value)

    def test_sql_injection_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_req(requested_modules=["cv'; DROP TABLE generation_jobs; --"])

    def test_html_injection_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_req(requested_modules=["<script>alert(1)</script>"])

    def test_mixed_valid_and_invalid_rejected(self) -> None:
        """One bad module poisons the whole list."""
        with pytest.raises(ValidationError) as exc_info:
            _make_req(requested_modules=["cv", "INVALID_MODULE", "scorecard"])
        assert "Unknown module" in str(exc_info.value)

    def test_whitespace_only_module_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_req(requested_modules=["   "])

    def test_case_sensitive_rejection(self) -> None:
        """Module names are case-sensitive; 'CV' is not the same as 'cv'."""
        with pytest.raises(ValidationError):
            _make_req(requested_modules=["CV"])

    def test_oversized_list_rejected(self) -> None:
        # Repeat a valid module 21 times to hit the max-20 guard
        with pytest.raises(ValidationError) as exc_info:
            _make_req(requested_modules=["cv"] * 21)
        assert "max 20" in str(exc_info.value).lower() or "Too many" in str(exc_info.value)

    def test_exactly_20_modules_accepted(self) -> None:
        """Boundary: exactly 20 valid modules must be accepted."""
        modules = (list(ALLOWED_JOB_MODULES) * 3)[:20]
        req = _make_req(requested_modules=modules)
        assert len(req.requested_modules) == 20

    def test_camelcase_variants_accepted(self) -> None:
        for mod in ("coverLetter", "personalStatement", "learningPlan", "gaps"):
            req = _make_req(requested_modules=[mod])
            assert mod in req.requested_modules

    def test_snake_case_variants_accepted(self) -> None:
        for mod in ("cover_letter", "personal_statement", "learning_plan"):
            req = _make_req(requested_modules=[mod])
            assert mod in req.requested_modules


class TestGenerationJobRequestApplicationId:
    """application_id validation on GenerationJobRequest."""

    def test_empty_application_id_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            GenerationJobRequest(application_id="", requested_modules=[])
        assert "required" in str(exc_info.value).lower()

    def test_whitespace_only_application_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GenerationJobRequest(application_id="   ", requested_modules=[])

    def test_over_200_char_application_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GenerationJobRequest(application_id="a" * 201, requested_modules=[])

    def test_exactly_200_char_application_id_accepted(self) -> None:
        req = GenerationJobRequest(application_id="a" * 200, requested_modules=[])
        assert len(req.application_id) == 200


# ─────────────────────────────────────────────────────────────────────────────
# RetryModulesRequest
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryModulesRequest:
    """RetryModulesRequest shares the whitelist but requires a non-empty list."""

    def test_valid_single_module_accepted(self) -> None:
        req = _make_retry(modules=["cv"])
        assert req.modules == ["cv"]

    def test_empty_list_rejected(self) -> None:
        """Retry with no modules is a user error — reject explicitly."""
        with pytest.raises(ValidationError) as exc_info:
            _make_retry(modules=[])
        assert "one module" in str(exc_info.value).lower() or "least" in str(exc_info.value).lower()

    def test_unknown_module_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_retry(modules=["not_a_real_module"])

    def test_mixed_valid_invalid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_retry(modules=["cv", "injected_module"])

    def test_oversized_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_retry(modules=["cv"] * 21)


class TestWhitelistContents:
    """Structural invariants on ALLOWED_JOB_MODULES itself."""

    def test_whitelist_is_nonempty(self) -> None:
        assert len(ALLOWED_JOB_MODULES) > 0

    def test_all_entries_are_nonempty_strings(self) -> None:
        for mod in ALLOWED_JOB_MODULES:
            assert isinstance(mod, str) and mod.strip() == mod and mod

    def test_no_duplicates_in_whitelist(self) -> None:
        """ALLOWED_JOB_MODULES is a set — duplicates are structurally impossible,
        but if it's ever changed to a list this test will catch regressions."""
        as_list = list(ALLOWED_JOB_MODULES)
        assert len(as_list) == len(set(as_list))

    def test_core_modules_present(self) -> None:
        """The four core document types must always be in the whitelist."""
        for mod in ("cv", "cover_letter", "personal_statement", "portfolio"):
            assert mod in ALLOWED_JOB_MODULES, f"Core module '{mod}' missing from whitelist"
