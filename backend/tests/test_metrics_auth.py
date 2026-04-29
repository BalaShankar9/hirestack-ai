"""S11-F1: /metrics endpoint authentication contract.

Pins the four states of the auth gate so a future config refactor
cannot silently re-open the metrics surface in production.

Behaviour matrix:

| environment | metrics_auth_token | header              | expected            |
|-------------|--------------------|---------------------|---------------------|
| development | ""                 | none                | 200 (open)          |
| production  | ""                 | none                | 403 (misconfigured) |
| any         | "secret"           | none                | 401 (missing)       |
| any         | "secret"           | "Bearer wrong"      | 403 (invalid)       |
| any         | "secret"           | "Bearer secret"     | 200                 |
"""
from __future__ import annotations

import pytest


def _make_request(auth_header: str | None) -> object:
    """Minimal Request stub exposing only `.headers.get(...)`."""

    class _Hdrs:
        def __init__(self, value: str | None) -> None:
            self._v = value

        def get(self, name: str, default: str = "") -> str:
            if name == "Authorization":
                return self._v if self._v is not None else default
            return default

    class _Req:
        headers = _Hdrs(auth_header)

    return _Req()


def _settings_with(monkeypatch, *, env: str, token: str) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "environment", env, raising=True)
    monkeypatch.setattr(cfg.settings, "metrics_auth_token", token, raising=True)


def test_metrics_open_in_dev_when_no_token(monkeypatch) -> None:
    _settings_with(monkeypatch, env="development", token="")
    from main import _check_metrics_auth

    assert _check_metrics_auth(_make_request(None)) is None


def test_metrics_locked_in_prod_when_no_token(monkeypatch) -> None:
    _settings_with(monkeypatch, env="production", token="")
    from main import _check_metrics_auth

    resp = _check_metrics_auth(_make_request(None))
    assert resp is not None
    assert resp.status_code == 403


def test_metrics_requires_bearer_when_token_set(monkeypatch) -> None:
    _settings_with(monkeypatch, env="production", token="s3cret")
    from main import _check_metrics_auth

    resp = _check_metrics_auth(_make_request(None))
    assert resp is not None
    assert resp.status_code == 401
    # WWW-Authenticate hint per RFC 7235.
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.parametrize(
    "header",
    [
        "Token s3cret",  # wrong scheme
        "bearer s3cret",  # case-sensitive scheme
        "Bearer s3cretx",  # off-by-one
        "Bearer ",  # empty token
    ],
)
def test_metrics_rejects_malformed_or_wrong_token(monkeypatch, header: str) -> None:
    _settings_with(monkeypatch, env="production", token="s3cret")
    from main import _check_metrics_auth

    resp = _check_metrics_auth(_make_request(header))
    # Either 401 (wrong scheme) or 403 (wrong value); both lock the surface.
    assert resp is not None
    assert resp.status_code in (401, 403)


def test_metrics_accepts_correct_bearer(monkeypatch) -> None:
    _settings_with(monkeypatch, env="production", token="s3cret")
    from main import _check_metrics_auth

    assert _check_metrics_auth(_make_request("Bearer s3cret")) is None


def test_metrics_uses_constant_time_compare() -> None:
    """Regression: ensure the implementation uses hmac.compare_digest,
    not == . A future refactor that drops to plain equality would
    introduce a timing oracle."""
    import inspect

    import main

    src = inspect.getsource(main._check_metrics_auth)
    assert "hmac.compare_digest" in src, (
        "S11-F1 contract drift: /metrics auth must use hmac.compare_digest "
        "to avoid timing oracles. Do not switch to == ."
    )
