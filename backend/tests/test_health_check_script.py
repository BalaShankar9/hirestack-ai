"""Unit tests for scripts/health_check.py (S10-F4).

The deploy workflow calls this script as the production health gate.
It had ZERO test coverage before this commit. These tests pin every
exit-code branch of the `_check()` helper plus the main() classifier.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "health_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("health_check_script", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["health_check_script"] = mod
    spec.loader.exec_module(mod)
    return mod


hc = _load_module()


# ── _check() branches ──────────────────────────────────────────────

def test_check_passes_on_expected_status() -> None:
    with patch.object(hc, "_http_get", return_value=(200, '{"status": "ok"}')):
        r = hc._check("t", "http://x", critical=True, expect_status=200,
                      expect_json_key="status")
    assert r.passed
    assert r.critical
    assert "200" in r.detail


def test_check_fails_on_wrong_status() -> None:
    with patch.object(hc, "_http_get", return_value=(503, "")):
        r = hc._check("t", "http://x", critical=True, expect_status=200)
    assert not r.passed
    assert "503" in r.detail and "expected 200" in r.detail


def test_check_fails_on_missing_body_substring() -> None:
    with patch.object(hc, "_http_get", return_value=(200, "<html>nope</html>")):
        r = hc._check("t", "http://x", critical=True,
                      expect_body_contains="Swagger UI")
    assert not r.passed
    assert "Swagger UI" in r.detail


def test_check_fails_on_invalid_json_when_key_expected() -> None:
    with patch.object(hc, "_http_get", return_value=(200, "not-json{")):
        r = hc._check("t", "http://x", critical=True,
                      expect_json_key="status")
    assert not r.passed
    assert "not valid JSON" in r.detail


def test_check_fails_on_missing_json_key() -> None:
    with patch.object(hc, "_http_get", return_value=(200, '{"other": 1}')):
        r = hc._check("t", "http://x", critical=True,
                      expect_json_key="status")
    assert not r.passed
    assert "status" in r.detail


def test_check_handles_http_error() -> None:
    from urllib import error as urlerror
    err = urlerror.HTTPError("http://x", 502, "Bad Gateway", hdrs=None, fp=None)
    with patch.object(hc, "_http_get", side_effect=err):
        r = hc._check("t", "http://x", critical=True)
    assert not r.passed
    assert "HTTPError 502" in r.detail


def test_check_handles_url_error() -> None:
    from urllib import error as urlerror
    with patch.object(hc, "_http_get", side_effect=urlerror.URLError("conn refused")):
        r = hc._check("t", "http://x", critical=True)
    assert not r.passed
    assert "URLError" in r.detail


def test_check_handles_arbitrary_exception() -> None:
    with patch.object(hc, "_http_get", side_effect=TimeoutError("slow")):
        r = hc._check("t", "http://x", critical=False)
    assert not r.passed
    assert "TimeoutError" in r.detail
    assert not r.critical


def test_check_records_latency_ms_as_int() -> None:
    with patch.object(hc, "_http_get", return_value=(200, "<html")):
        r = hc._check("t", "http://x", critical=True, expect_body_contains="<html")
    assert isinstance(r.latency_ms, int)
    assert r.latency_ms >= 0


# ── main() exit codes ─────────────────────────────────────────────

def _stub_get_factory(spec: dict[str, tuple[int, str]]):
    """Map URL substring -> (status, body)."""
    def stub(url, *, timeout=10.0):
        for needle, response in spec.items():
            if needle in url:
                return response
        raise AssertionError(f"unexpected url: {url}")
    return stub


def test_main_returns_0_when_all_green(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hc, "_http_get", _stub_get_factory({
        "/health":       (200, '{"status": "ok"}'),
        "/openapi.json": (200, '{"openapi": "3.1.0"}'),
        "/docs":         (200, "<html>Swagger UI</html>"),
        "/":             (200, "<html>hi</html>"),
    }))
    monkeypatch.setattr(sys, "argv", [
        "health_check.py", "--backend", "https://api.x", "--frontend", "https://app.x",
    ])
    rc = hc.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "PASS" in out


def test_main_returns_2_when_only_non_critical_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hc, "_http_get", _stub_get_factory({
        "/health":       (200, '{"status": "ok"}'),
        "/openapi.json": (200, '{"openapi": "3.1.0"}'),
        "/docs":         (404, ""),  # non-critical fail
        "/":             (200, "<html>hi</html>"),
    }))
    monkeypatch.setattr(sys, "argv", [
        "health_check.py", "--backend", "https://api.x", "--frontend", "https://app.x",
    ])
    rc = hc.main()
    assert rc == 2
    assert "DEGRADED" in capsys.readouterr().out


def test_main_returns_1_when_a_critical_check_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(hc, "_http_get", _stub_get_factory({
        "/health":       (500, ""),
        "/openapi.json": (200, '{"openapi": "3.1.0"}'),
        "/docs":         (200, "<html>Swagger UI</html>"),
        "/":             (200, "<html>hi</html>"),
    }))
    monkeypatch.setattr(sys, "argv", [
        "health_check.py", "--backend", "https://api.x", "--frontend", "https://app.x",
    ])
    rc = hc.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "NOT GREEN" in out
    assert "backend.health" in out


def test_main_strips_trailing_slash_on_urls(monkeypatch) -> None:
    seen: list[str] = []

    def stub(url, *, timeout=10.0):
        seen.append(url)
        return (200, '{"status": "ok", "openapi": "3.1.0"}<html')

    monkeypatch.setattr(hc, "_http_get", stub)
    monkeypatch.setattr(sys, "argv", [
        "health_check.py",
        "--backend",  "https://api.x///",
        "--frontend", "https://app.x/",
    ])
    hc.main()
    # No URL must contain a doubled slash after the host.
    for u in seen:
        host_and_path = u.split("://", 1)[1]
        assert "//" not in host_and_path, f"trailing slash leaked into URL: {u}"


# ── deploy.yml integration ────────────────────────────────────────

def test_deploy_workflow_invokes_health_check_script() -> None:
    """S10-F4 wires scripts/health_check.py into the deploy workflow."""
    deploy_yml = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert "scripts/health_check.py" in deploy_yml, (
        "deploy.yml no longer invokes scripts/health_check.py; the "
        "deploy gate has regressed to ad-hoc curl. See S10-F4."
    )
