"""
Contract tests for `classify_ai_error` and `_extract_retry_after`.

These two functions sit on the hot error path of every pipeline run:
when a Gemini call raises, `classify_ai_error` decides what HTTP code +
user-facing message gets surfaced to the frontend (and which retry
budget the orchestrator reserves). A miscategorisation here means a
caller sees the wrong remediation hint or the system retries against
quotas it should have respected.

The function uses substring matching on the lowercased error string,
so each branch is fragile to upstream wording changes. These tests
pin the canonical wordings the function currently catches and prove
each branch maps to the correct response shape — so any regression
(typo, deleted branch, swapped ordering) fails loudly here, not in
production.
"""
from __future__ import annotations

import pytest

from app.services.pipeline_runtime import (
    _extract_retry_after,
    classify_ai_error,
)


# ── Branch 1: invalid API key (401) ───────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        "API key not valid. Please pass a valid API key.",
        "API_KEY_INVALID: rejected",
        "API keys are not supported by this endpoint",
        "Expected OAuth2 access token but found api key",
        "credentials_missing for project",
    ],
)
def test_invalid_api_key_returns_401(msg: str) -> None:
    out = classify_ai_error(RuntimeError(msg))
    assert out is not None, f"branch should match: {msg!r}"
    assert out["code"] == 401
    assert "Gemini" in out["message"]
    assert "API key" in out["message"] or "GEMINI_API_KEY" in out["message"]


def test_invalid_api_key_match_is_case_insensitive() -> None:
    """All branches lowercase the error string, so the exact case in the
    raised exception must not change the outcome."""
    upper = classify_ai_error(RuntimeError("API KEY NOT VALID"))
    lower = classify_ai_error(RuntimeError("api key not valid"))
    mixed = classify_ai_error(RuntimeError("Api Key Not Valid"))
    assert upper is not None and lower is not None and mixed is not None
    assert upper["code"] == lower["code"] == mixed["code"] == 401


# ── Branch 2: permission denied (403) ─────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    ["Permission denied for this resource", "PERMISSION_DENIED on Gemini"],
)
def test_permission_denied_returns_403(msg: str) -> None:
    out = classify_ai_error(RuntimeError(msg))
    assert out is not None
    assert out["code"] == 403
    assert "permission" in out["message"].lower()


# ── Branch 3: model not found (404) ───────────────────────────────────


def test_model_not_found_with_404_returns_404() -> None:
    out = classify_ai_error(RuntimeError("Resource not found (404)"))
    assert out is not None
    assert out["code"] == 404
    assert "model" in out["message"].lower()


def test_model_not_found_with_model_keyword_returns_404() -> None:
    out = classify_ai_error(RuntimeError("Model gemini-bogus not found"))
    assert out is not None
    assert out["code"] == 404


def test_not_found_without_model_or_404_does_not_match_404_branch() -> None:
    """Bare 'not found' (e.g. 'project not found') must NOT be classified
    as a model issue — that would mislead the user into editing
    GEMINI_MODEL when the real fix is project setup."""
    out = classify_ai_error(RuntimeError("project not found in registry"))
    # Either falls through to None or to a different (non-404) branch.
    if out is not None:
        assert out["code"] != 404


# ── Branch 4: rate limit / quota (429) ────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        "Resource exhausted",
        "RESOURCE EXHAUSTED on quota",
        "rate limit reached for model",
        "HTTP 429 returned from upstream",
    ],
)
def test_rate_limit_returns_429(msg: str) -> None:
    out = classify_ai_error(RuntimeError(msg))
    assert out is not None
    assert out["code"] == 429
    assert "rate limit" in out["message"].lower() or "wait" in out["message"].lower()
    # Even when no retry-after hint is parseable, the key must exist
    # so the orchestrator's contract (always-present field) holds.
    assert "retry_after_seconds" in out


def test_rate_limit_extracts_retry_after_from_natural_language() -> None:
    out = classify_ai_error(RuntimeError("429: please retry in 12s"))
    assert out is not None
    assert out["code"] == 429
    assert out["retry_after_seconds"] == 12


def test_rate_limit_extracts_retry_after_from_proto_dict() -> None:
    out = classify_ai_error(
        RuntimeError("rate limit; details: {retryDelay': '7s'}")
    )
    assert out is not None
    assert out["code"] == 429
    assert out["retry_after_seconds"] == 7


def test_rate_limit_with_no_hint_has_none_retry_after() -> None:
    out = classify_ai_error(RuntimeError("rate limit reached"))
    assert out is not None
    assert out["retry_after_seconds"] is None


# ── Branch 5: unmatched errors fall through ───────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        "Some unrelated runtime crash",
        "ConnectionResetError on socket",
        "ValueError: bad input",
        "",
    ],
)
def test_unmatched_errors_return_none(msg: str) -> None:
    """When no branch matches, the function MUST return None so the
    caller can fall back to a generic 500. Returning a partial dict
    here would mask the real failure mode."""
    assert classify_ai_error(RuntimeError(msg)) is None


# ── Branch ordering: API key wins over model-not-found if both ────────


def test_api_key_takes_precedence_over_other_branches() -> None:
    """The function checks branches in source order: api-key → permission
    → not-found → rate-limit. If both 'api key' and 'not found' appear
    in the same message, the user's primary problem is the bad key —
    fixing the model name won't help. Pin that ordering."""
    msg = "API key not valid; model gemini-1.5 not found (404)"
    out = classify_ai_error(RuntimeError(msg))
    assert out is not None
    assert out["code"] == 401, "api-key branch must win"


def test_permission_takes_precedence_over_not_found() -> None:
    msg = "permission denied; model not found (404)"
    out = classify_ai_error(RuntimeError(msg))
    assert out is not None
    assert out["code"] == 403


# ── _extract_retry_after edge cases ───────────────────────────────────


def test_extract_retry_after_natural_language_seconds() -> None:
    assert _extract_retry_after("please retry in 5s") == 5
    assert _extract_retry_after("Retry in 30S now") == 30


def test_extract_retry_after_rounds_up_fractional_seconds() -> None:
    """0.4s must become 1s, not 0 — never tell the orchestrator it can
    retry immediately when the provider asked for a delay."""
    assert _extract_retry_after("retry in 0.4s") == 1
    assert _extract_retry_after("retry in 2.1s") == 3
    assert _extract_retry_after("retry in 2.0s") == 2


def test_extract_retry_after_proto_retry_delay_dict() -> None:
    assert _extract_retry_after("retryDelay': '15s'") == 15


def test_extract_retry_after_returns_none_on_no_match() -> None:
    assert _extract_retry_after("totally generic error") is None
    assert _extract_retry_after("") is None


def test_extract_retry_after_floor_is_one_second() -> None:
    """Even '0s' must clamp to 1 to avoid hot-spinning the API."""
    assert _extract_retry_after("retry in 0s") == 1


def test_extract_retry_after_natural_language_takes_precedence() -> None:
    """Both formats present → the natural-language form is checked first
    in the source. Pin that precedence."""
    msg = "retry in 4s; retryDelay': '99s'"
    assert _extract_retry_after(msg) == 4


# ── Type contract: classify_ai_error always returns dict-or-None ──────


def test_return_value_is_dict_or_none() -> None:
    """Callers do `if (resp := classify_ai_error(e)):` — anything other
    than a dict-or-None breaks that pattern."""
    for msg in [
        "API key not valid",
        "permission denied",
        "model not found 404",
        "rate limit",
        "unrelated",
    ]:
        out = classify_ai_error(RuntimeError(msg))
        assert out is None or isinstance(out, dict)


def test_classified_dicts_always_have_code_and_message() -> None:
    """Every classified branch must populate at least these two keys —
    they are the minimum contract the API layer relies on."""
    for msg in [
        "API key not valid",
        "permission denied",
        "model not found 404",
        "rate limit",
    ]:
        out = classify_ai_error(RuntimeError(msg))
        assert out is not None, msg
        assert "code" in out and isinstance(out["code"], int)
        assert "message" in out and isinstance(out["message"], str)
        assert out["message"], "message must be non-empty user-facing text"
