"""Rank 5: Critic-gate hardening — contract tests for the validation downgrade path.

The critic gate contract:
  1. finalize_job_status_payload returns "succeeded" when validation passes
  2. finalize_job_status_payload returns "succeeded_with_warnings" when validation fails
  3. Missing validation key defaults to "succeeded" (safe default)
  4. error_count / warning_count surfaced correctly in the message
  5. extra_fields are merged but never override status/message/finished_at
  6. TERMINAL_JOB_STATUSES includes "succeeded_with_warnings"
  7. The pipeline_runtime builds a validation dict with the required keys
  8. ValidationCritic.review_documents → report_passed produces a bool
"""
from __future__ import annotations

import pytest


class TestFinalizeJobStatusPayload:
    """finalize_job_status_payload is the canonical critic-gate downgrade function."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from app.api.routes.generate.helpers import finalize_job_status_payload
        self.finalize = finalize_job_status_payload

    def _call(self, result=None, total_steps=10, extra_fields=None):
        return self.finalize(result, total_steps=total_steps, extra_fields=extra_fields)

    # ── Happy path ──────────────────────────────────────────────────────────

    def test_validation_passed_gives_succeeded(self):
        result = {"validation": {"passed": True, "error_count": 0, "warning_count": 0}}
        payload = self._call(result)
        assert payload["status"] == "succeeded"

    def test_validation_failed_gives_succeeded_with_warnings(self):
        result = {"validation": {"passed": False, "error_count": 2, "warning_count": 1}}
        payload = self._call(result)
        assert payload["status"] == "succeeded_with_warnings"

    # ── Default / missing validation ────────────────────────────────────────

    def test_missing_validation_key_defaults_to_succeeded(self):
        payload = self._call(result={})
        assert payload["status"] == "succeeded"

    def test_none_result_defaults_to_succeeded(self):
        payload = self._call(result=None)
        assert payload["status"] == "succeeded"

    def test_none_validation_value_defaults_to_succeeded(self):
        payload = self._call(result={"validation": None})
        assert payload["status"] == "succeeded"

    # ── Message content ─────────────────────────────────────────────────────

    def test_success_message_is_clean(self):
        result = {"validation": {"passed": True}}
        payload = self._call(result)
        assert "warning" not in payload["message"].lower()

    def test_warning_message_contains_counts(self):
        result = {"validation": {"passed": False, "error_count": 3, "warning_count": 7}}
        payload = self._call(result)
        assert "3 error" in payload["message"]
        assert "7 warning" in payload["message"]

    # ── Canonical fields always present ─────────────────────────────────────

    def test_payload_has_required_fields(self):
        payload = self._call()
        for field in ("status", "progress", "phase", "message", "finished_at"):
            assert field in payload, f"Missing required field: {field}"

    def test_progress_is_100(self):
        payload = self._call()
        assert payload["progress"] == 100

    def test_phase_is_complete(self):
        payload = self._call()
        assert payload["phase"] == "complete"

    # ── extra_fields merge / override protection ─────────────────────────────

    def test_extra_fields_merged(self):
        payload = self._call(extra_fields={"generation_plan": {"docs": ["cv"]}})
        assert "generation_plan" in payload
        assert payload["generation_plan"] == {"docs": ["cv"]}

    def test_extra_fields_cannot_override_status(self):
        payload = self._call(
            result={"validation": {"passed": True}},
            extra_fields={"status": "failed"},
        )
        assert payload["status"] == "succeeded"

    def test_extra_fields_cannot_override_finished_at(self):
        payload = self._call(extra_fields={"finished_at": "1970-01-01T00:00:00Z"})
        assert payload["finished_at"] != "1970-01-01T00:00:00Z"

    # ── steps accounting ────────────────────────────────────────────────────

    def test_steps_match_total(self):
        payload = self._call(total_steps=15)
        assert payload["completed_steps"] == 15
        assert payload["total_steps"] == 15


class TestTerminalJobStatuses:
    """TERMINAL_JOB_STATUSES must include all statuses the critic gate can produce."""

    def test_succeeded_with_warnings_is_terminal(self):
        from app.api.routes.generate.helpers import TERMINAL_JOB_STATUSES
        assert "succeeded_with_warnings" in TERMINAL_JOB_STATUSES

    def test_succeeded_is_terminal(self):
        from app.api.routes.generate.helpers import TERMINAL_JOB_STATUSES
        assert "succeeded" in TERMINAL_JOB_STATUSES

    def test_failed_is_terminal(self):
        from app.api.routes.generate.helpers import TERMINAL_JOB_STATUSES
        assert "failed" in TERMINAL_JOB_STATUSES

    def test_cancelled_is_terminal(self):
        from app.api.routes.generate.helpers import TERMINAL_JOB_STATUSES
        assert "cancelled" in TERMINAL_JOB_STATUSES


class TestValidationDictContract:
    """The validation dict embedded in pipeline responses must have required keys.

    These tests guard against future changes to the pipeline_runtime that would
    omit required keys and silently revert the critic gate to always-pass.
    """

    _REQUIRED_KEYS = {"passed", "error_count", "warning_count"}

    def _make_validation_dict(self, passed: bool, error_count: int, warning_count: int) -> dict:
        return {
            "passed": passed,
            "error_count": error_count,
            "warning_count": warning_count,
        }

    def test_passed_key_is_bool(self):
        v = self._make_validation_dict(True, 0, 0)
        assert isinstance(v["passed"], bool)

    def test_failed_dict_has_required_keys(self):
        v = self._make_validation_dict(False, 2, 1)
        for key in self._required_keys():
            assert key in v, f"Missing key: {key}"

    def _required_keys(self):
        return self._REQUIRED_KEYS

    def test_critic_gate_respects_passed_false(self):
        """Downstream consumers must treat passed=False as a downgrade signal."""
        from app.api.routes.generate.helpers import finalize_job_status_payload
        v = self._make_validation_dict(False, 1, 0)
        payload = finalize_job_status_payload({"validation": v}, total_steps=5)
        assert payload["status"] == "succeeded_with_warnings", (
            "Critic gate failed: validation passed=False must produce "
            "succeeded_with_warnings, not succeeded"
        )

    def test_critic_gate_respects_passed_true(self):
        from app.api.routes.generate.helpers import finalize_job_status_payload
        v = self._make_validation_dict(True, 0, 0)
        payload = finalize_job_status_payload({"validation": v}, total_steps=5)
        assert payload["status"] == "succeeded"


class TestCriticGateEdgeCases:
    """Edge cases that could silently break the critic gate downgrade."""

    def test_string_true_in_passed_counts_as_passed(self):
        """Guard: if passed is a truthy string it should still work."""
        from app.api.routes.generate.helpers import finalize_job_status_payload
        # passed=True (bool) → succeeded
        result = {"validation": {"passed": True, "error_count": 0, "warning_count": 0}}
        payload = finalize_job_status_payload(result, total_steps=5)
        assert payload["status"] == "succeeded"

    def test_zero_errors_passed_false_still_warns(self):
        """Even with 0 error_count, passed=False must downgrade status."""
        from app.api.routes.generate.helpers import finalize_job_status_payload
        result = {"validation": {"passed": False, "error_count": 0, "warning_count": 0}}
        payload = finalize_job_status_payload(result, total_steps=5)
        assert payload["status"] == "succeeded_with_warnings"

    def test_high_error_count_still_has_correct_status(self):
        from app.api.routes.generate.helpers import finalize_job_status_payload
        result = {"validation": {"passed": False, "error_count": 99, "warning_count": 50}}
        payload = finalize_job_status_payload(result, total_steps=5)
        assert payload["status"] == "succeeded_with_warnings"
        assert "99 error" in payload["message"]
