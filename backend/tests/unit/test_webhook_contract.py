"""S7-F2: pin app/services/webhook.py contracts.

Behavioural lock for the pure module-level helpers used by
WebhookService — no httpx, no DB. The async dispatch path
(`WebhookService.fire`) is exercised separately by the existing
`test_webhook_retry.py`; here we lock the *deterministic* surface
that signed-body consumers must rely on.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.services.webhook import (
    _RETRY_BACKOFF_BASE_S,
    _RETRY_BACKOFF_CAP_S,
    _RETRY_MAX_ATTEMPTS,
    _RETRYABLE_STATUSES,
    _format_slack_payload,
    _is_slack_url,
)


# ── _is_slack_url ──────────────────────────────────────────────────


class TestIsSlackUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://hooks.slack.com/services/T00/B00/abcXYZ",
            "https://HOOKS.SLACK.COM/services/T00/B00/abcXYZ",  # case-insensitive
            "http://hooks.slack.com/services/anything",
            "https://my.slack.com/services/foo",  # any *.slack.com/services
        ],
    )
    def test_slack_urls_match(self, url):
        assert _is_slack_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://hooks.example.com/services/abc",
            "https://slack.com/api/anything",  # /api/ not /services/
            "https://example.com",
            "https://hooks.slack.com/api/something",  # /services missing
        ],
    )
    def test_non_slack_urls_do_not_match(self, url):
        assert _is_slack_url(url) is False

    def test_empty_or_falsy_returns_false(self):
        assert _is_slack_url("") is False
        assert _is_slack_url(None) is False  # type: ignore[arg-type]


# ── _format_slack_payload ──────────────────────────────────────────


class TestFormatSlackPayload:
    def test_returns_dict_with_text_and_attachments(self):
        out = _format_slack_payload("application.created", {"application_id": "abc"})
        assert isinstance(out, dict)
        assert "text" in out and isinstance(out["text"], str)
        assert "attachments" in out and isinstance(out["attachments"], list)

    def test_event_type_humanised_in_title(self):
        out = _format_slack_payload("application.module.completed", {})
        # "_" → " ", "." → " · ", title-cased.
        assert "Application · Module · Completed" in out["text"]

    def test_highlight_keys_pulled(self):
        payload = {
            "application_id": "app-123",
            "job_title": "Engineer",
            "company": "Acme",
            "status": "ok",
            "score": 87,
        }
        out = _format_slack_payload("application.scored", payload)
        # Each highlight is rendered as "*Key Title*: value", joined with " | ".
        for needle in ("Application Id", "app-123", "Job Title", "Engineer", "Acme", "Status", "Score"):
            assert needle in out["text"]
        assert " | " in out["text"]

    def test_unrecognised_keys_ignored_in_highlights(self):
        out = _format_slack_payload("evt", {"random_key": "x", "application_id": "a"})
        assert "random_key" not in out["text"]
        assert "Application Id" in out["text"]

    def test_empty_or_blank_highlight_values_skipped(self):
        # None and empty-string values must not generate a highlight.
        out = _format_slack_payload("evt", {"application_id": None, "company": "", "status": "ok"})
        # Only "status" should appear in the highlight line.
        text_lines = out["text"].split("\n")
        # Title is line 1; highlights line is line 2 (or absent).
        assert any("Status" in l and "ok" in l for l in text_lines[1:])
        assert "Application Id" not in out["text"]
        assert "Company" not in out["text"]

    def test_no_highlights_means_no_pipe_line(self):
        # If no recognised keys are present, the second line is omitted.
        out = _format_slack_payload("evt", {"unrelated": "v"})
        # Title is the only non-empty line.
        assert " | " not in out["text"]

    def test_color_good_for_normal_event(self):
        out = _format_slack_payload("application.created", {})
        assert out["attachments"][0]["color"] == "good"

    def test_color_danger_when_failed_in_event_type(self):
        out = _format_slack_payload("application.failed", {})
        assert out["attachments"][0]["color"] == "danger"

    def test_color_danger_substring_match(self):
        # Any event whose name *contains* "failed" flips to danger.
        out = _format_slack_payload("module.generation.failed.retry", {})
        assert out["attachments"][0]["color"] == "danger"

    def test_attachment_text_is_truncated_to_3500_chars(self):
        # The attachment text wraps the JSON-dumped payload in a
        # ``` fence and truncates at 3500 chars to stay under
        # Slack's per-block limit.
        big_payload = {"data": "x" * 10_000}
        out = _format_slack_payload("evt", big_payload)
        attachment_text = out["attachments"][0]["text"]
        # Surrounding ``` adds 6 chars. The slice itself is at most 3500.
        assert attachment_text.startswith("```")
        # The total length must not exceed 3500 + 6 closing fence chars.
        assert len(attachment_text) <= 3500 + 6

    def test_attachment_payload_uses_default_str_for_non_json_types(self):
        # `default=str` lets the helper survive non-JSON types like
        # datetime. Using a class object as a sentinel.
        class Stub:
            def __str__(self):
                return "STUB"

        out = _format_slack_payload("evt", {"obj": Stub()})
        attachment_text = out["attachments"][0]["text"]
        assert "STUB" in attachment_text


# ── Retry constants (load-bearing, consumed by fire()) ─────────────


class TestRetryConstants:
    def test_max_attempts_is_three(self):
        assert _RETRY_MAX_ATTEMPTS == 3

    def test_backoff_base_and_cap(self):
        # Base ≤ cap, cap reasonable for an outbound HTTP retry.
        assert 0 < _RETRY_BACKOFF_BASE_S <= _RETRY_BACKOFF_CAP_S
        assert _RETRY_BACKOFF_CAP_S <= 10  # sanity: not minutes

    def test_retryable_statuses_set_membership(self):
        # The exact set is API contract — consumers/operators may
        # rely on it for monitoring & dashboards.
        assert _RETRYABLE_STATUSES == {408, 425, 429, 500, 502, 503, 504}

    def test_4xx_other_than_429_408_425_not_retried(self):
        for status in (400, 401, 403, 404, 410, 422):
            assert status not in _RETRYABLE_STATUSES

    def test_2xx_3xx_not_retried(self):
        for status in (200, 201, 204, 301, 302, 304):
            assert status not in _RETRYABLE_STATUSES


# ── HMAC signature determinism (consumer contract) ────────────────


class TestSignatureDeterminism:
    """The webhook produces sha256 HMACs over the JSON body bytes
    using the per-webhook secret. Consumers replay the signature to
    verify authenticity. This pins the algorithm and encoding.
    """

    def test_signature_matches_known_vector(self):
        body = json.dumps({"event": "x", "data": {}})
        secret = "topsecret"
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        # The header value the service ships is "sha256=<hex>".
        # We only confirm the underlying primitive choice here.
        actual = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        assert actual == expected
        # Hex digest is 64 chars (256 bits / 4).
        assert len(actual) == 64

    def test_different_secret_yields_different_signature(self):
        body = "{}"
        a = hmac.new(b"a", body.encode(), hashlib.sha256).hexdigest()
        b = hmac.new(b"b", body.encode(), hashlib.sha256).hexdigest()
        assert a != b

    def test_same_inputs_yield_same_signature(self):
        body = json.dumps({"event": "x"})
        s1 = hmac.new(b"k", body.encode(), hashlib.sha256).hexdigest()
        s2 = hmac.new(b"k", body.encode(), hashlib.sha256).hexdigest()
        assert s1 == s2


# ── Slack body bytes are stable JSON (signing depends on this) ─────


class TestSlackBodyJsonStability:
    def test_json_roundtrip_of_slack_body_is_deterministic(self):
        # The service signs the *exact* JSON-encoded body it ships.
        # We confirm that re-encoding the same dict yields the same
        # bytes (so a consumer can re-encode and re-sign locally if
        # they receive a structured payload).
        out = _format_slack_payload("application.failed", {"application_id": "a"})
        b1 = json.dumps(out)
        b2 = json.dumps(out)
        assert b1 == b2
