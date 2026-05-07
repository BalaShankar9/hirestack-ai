"""Tests for the SSRF guard (PR m5-pr15)."""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import patch

import pytest

from app.core.safe_fetch import (
    GuardConfig,
    UnsafeURLError,
    assert_safe_url,
    is_enforced,
    safe_get,
)


def _stub_resolver(*ips: str):
    def fake_getaddrinfo(host: str, *_args: Any, **_kw: Any):
        return [(socket.AF_INET, None, None, "", (ip, 0)) for ip in ips]
    return patch("app.core.safe_fetch.socket.getaddrinfo", side_effect=fake_getaddrinfo)


# ── scheme + literal IP ────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "ftp://example.com/file",
    "file:///etc/passwd",
    "gopher://example.com",
])
def test_blocks_non_http_schemes(url: str) -> None:
    with pytest.raises(UnsafeURLError, match="bad_scheme"):
        assert_safe_url(url)


@pytest.mark.parametrize("url", [
    "http://10.0.0.1/admin",
    "http://192.168.1.5/",
    "http://172.16.5.5/",
    "http://127.0.0.1:8000/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://[fe80::1]/",
])
def test_blocks_dangerous_literal_ips(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        assert_safe_url(url)


def test_blocks_metadata_hostname() -> None:
    with pytest.raises(UnsafeURLError, match="metadata_host"):
        assert_safe_url("http://metadata.google.internal/")


def test_blocks_extra_host() -> None:
    cfg = GuardConfig(extra_blocked_hosts=("internal.corp",))
    with pytest.raises(UnsafeURLError, match="blocked_host"):
        assert_safe_url("http://internal.corp/api", config=cfg)


# ── DNS resolution paths ───────────────────────────────────────────────
def test_blocks_hostname_resolving_to_private() -> None:
    with _stub_resolver("10.0.5.5"):
        with pytest.raises(UnsafeURLError, match="blocked_ip"):
            assert_safe_url("http://attacker.example/")


def test_blocks_mixed_result_set_failing_closed() -> None:
    with _stub_resolver("8.8.8.8", "192.168.0.1"):
        with pytest.raises(UnsafeURLError, match="private"):
            assert_safe_url("http://mixed.example/")


def test_allows_public_address() -> None:
    with _stub_resolver("8.8.8.8"):
        assert_safe_url("https://public.example/")


def test_dns_failure_raises() -> None:
    def boom(*_a: Any, **_kw: Any):
        raise socket.gaierror(8, "nodename nor servname provided")
    with patch("app.core.safe_fetch.socket.getaddrinfo", side_effect=boom):
        with pytest.raises(UnsafeURLError, match="dns_failure"):
            assert_safe_url("http://noexist.example/")


# ── relaxation knobs ───────────────────────────────────────────────────
def test_allow_private_relaxes_block() -> None:
    assert_safe_url("http://10.0.0.1/", config=GuardConfig(allow_private=True))


def test_allow_loopback_relaxes_block() -> None:
    assert_safe_url("http://127.0.0.1/", config=GuardConfig(allow_loopback=True))


# ── enforcement flag ───────────────────────────────────────────────────
def test_enforcement_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAFE_FETCH_ENFORCE", raising=False)
    assert is_enforced() is True


@pytest.mark.parametrize("val", ["0", "false", "FALSE", "no", "off"])
def test_enforcement_off_via_env(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv("SAFE_FETCH_ENFORCE", val)
    assert is_enforced() is False


# ── safe_get integration: blocked URL never reaches httpx ──────────────
@pytest.mark.asyncio
async def test_safe_get_blocks_before_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAFE_FETCH_ENFORCE", "true")
    called: list[str] = []

    class FakeClient:
        async def get(self, url: str, **_kw: Any):
            called.append(url)

    with pytest.raises(UnsafeURLError):
        await safe_get("http://169.254.169.254/", client=FakeClient())
    assert called == []


@pytest.mark.asyncio
async def test_safe_get_passthrough_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAFE_FETCH_ENFORCE", "false")

    class FakeResp:
        status_code = 200

    class FakeClient:
        async def get(self, url: str, **_kw: Any):
            return FakeResp()

    resp = await safe_get("http://169.254.169.254/", client=FakeClient())
    assert resp.status_code == 200
