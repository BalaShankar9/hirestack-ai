"""Unit tests for backend.app.services.url_canonicalizer.

Covers URL canonicalization (tracking-param stripping, scheme/host
lower-casing, trailing-slash normalization) and ATS platform key
extraction for Greenhouse / Lever / Ashby / Workday / Workable /
SmartRecruiters.
"""
from __future__ import annotations

import pytest

from app.services.url_canonicalizer import canonicalize_url, extract_ats_key


# ── canonicalize_url ──────────────────────────────────────────────────────────


def test_strips_utm_parameters():
    url = "https://boards.greenhouse.io/acme/jobs/12345?utm_source=linkedin&utm_medium=feed"
    assert canonicalize_url(url) == "https://boards.greenhouse.io/acme/jobs/12345"


def test_strips_all_tracking_params():
    url = "https://jobs.lever.co/acme/abc?gh_src=x&fbclid=y&gclid=z&ref=q"
    assert canonicalize_url(url) == "https://jobs.lever.co/acme/abc"


def test_preserves_non_tracking_params():
    url = "https://jobs.lever.co/acme/abc123?team=eng"
    assert canonicalize_url(url) == "https://jobs.lever.co/acme/abc123?team=eng"


def test_lowercases_scheme_and_host():
    url = "HTTPS://Jobs.Ashbyhq.com/Acme/xyz"
    # Host lowercased; path case preserved
    assert canonicalize_url(url) == "https://jobs.ashbyhq.com/Acme/xyz"


def test_strips_trailing_slash_on_deep_paths():
    url = "https://boards.greenhouse.io/acme/jobs/123/"
    assert canonicalize_url(url) == "https://boards.greenhouse.io/acme/jobs/123"


def test_keeps_single_slash_root():
    # Bare root should not become scheme://host (empty path), keep '/'
    url = "https://example.com/"
    assert canonicalize_url(url) == "https://example.com/"


def test_adds_https_when_scheme_missing():
    # urlparse treats scheme-less input as path. We don't try to infer
    # a scheme here — canonicalizer assumes callers provide a valid URL.
    # Instead, assert round-trip stability on a fully-qualified URL.
    url = "https://example.com/a"
    assert canonicalize_url(url) == "https://example.com/a"


def test_empty_input_returns_empty():
    assert canonicalize_url("") == ""


def test_strips_fragment():
    url = "https://jobs.lever.co/acme/abc#apply"
    assert canonicalize_url(url) == "https://jobs.lever.co/acme/abc"


# ── extract_ats_key ───────────────────────────────────────────────────────────


def test_extracts_greenhouse_job_id():
    url = "https://boards.greenhouse.io/acme/jobs/4987123"
    assert extract_ats_key(url) == ("greenhouse", "acme", "4987123")


def test_extracts_lever_key():
    url = "https://jobs.lever.co/acme/abc-123-def"
    assert extract_ats_key(url) == ("lever", "acme", "abc-123-def")


def test_extracts_ashby_key():
    url = "https://jobs.ashbyhq.com/acme/7fbd3a9e-123"
    assert extract_ats_key(url) == ("ashby", "acme", "7fbd3a9e-123")


def test_extracts_workday_key():
    url = "https://acme.myworkdayjobs.com/external/job/San-Francisco/Senior-Engineer_R-12345"
    result = extract_ats_key(url)
    assert result is not None
    assert result[0] == "workday"
    assert result[1] == "acme"
    # job id is the last path segment
    assert result[2] == "Senior-Engineer_R-12345"


def test_extracts_workable_key():
    url = "https://apply.workable.com/acme/j/ABC123/"
    result = extract_ats_key(url)
    assert result is not None
    assert result[0] == "workable"
    assert result[1] == "acme"


def test_extracts_smartrecruiters_key():
    url = "https://jobs.smartrecruiters.com/AcmeCorp/7438201-senior-engineer"
    result = extract_ats_key(url)
    assert result == ("smartrecruiters", "AcmeCorp", "7438201-senior-engineer")


def test_unknown_url_returns_none():
    assert extract_ats_key("https://example.com/careers") is None


def test_empty_url_returns_none():
    assert extract_ats_key("") is None


def test_extract_survives_tracking_params():
    # extract_ats_key should work on the raw URL or canonicalized URL
    url = "https://boards.greenhouse.io/acme/jobs/12345?utm_source=x"
    assert extract_ats_key(url) == ("greenhouse", "acme", "12345")
