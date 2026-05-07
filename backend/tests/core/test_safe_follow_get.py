"""Tests for safe_follow_get (PR m6-pr20).

Covers:
  • Per-hop SSRF revalidation on 30x redirects.
  • max_bytes truncation.
  • Relative Location resolution.
  • too_many_redirects raises UnsafeURLError.
  • Public destination passes through.
"""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.core.safe_fetch import (
    SafeFetchResult,
    UnsafeURLError,
    safe_follow_get,
)


def _stub_resolver_per_host(mapping: dict[str, list[str]]):
    """Resolve different hosts to different IPs (DNS-rebinding sims)."""

    def fake(host: str, *_a: Any, **_k: Any):
        ips = mapping.get(host, ["8.8.8.8"])
        return [(socket.AF_INET, None, None, "", (ip, 0)) for ip in ips]

    return patch("app.core.safe_fetch.socket.getaddrinfo", side_effect=fake)


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_blocks_redirect_to_metadata_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """A public host that 30x to 169.254.169.254 must be refused."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
        # If the guard ever lets this through, it'd be very bad.
        return httpx.Response(200, text="LEAKED METADATA")

    # Patch the AsyncClient ctor to force MockTransport.
    real_ctor = httpx.AsyncClient.__init__

    def spy_init(self, *a, **kw):  # type: ignore[no-redef]
        kw["transport"] = _mock_transport(handler)
        return real_ctor(self, *a, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy_init)

    with _stub_resolver_per_host({"public.example": ["8.8.8.8"]}):
        with pytest.raises(UnsafeURLError):
            await safe_follow_get("http://public.example/", timeout=2.0)


@pytest.mark.asyncio
async def test_truncates_body_at_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    big = b"x" * (1024 * 1024)  # 1 MB

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    real_ctor = httpx.AsyncClient.__init__
    monkeypatch.setattr(
        httpx.AsyncClient,
        "__init__",
        lambda self, *a, **kw: real_ctor(
            self, *a, **{**kw, "transport": _mock_transport(handler)}
        ),
    )

    with _stub_resolver_per_host({"public.example": ["8.8.8.8"]}):
        result = await safe_follow_get(
            "http://public.example/big",
            timeout=2.0,
            max_bytes=4096,
        )
    assert isinstance(result, SafeFetchResult)
    assert result.status_code == 200
    assert len(result.body) == 4096


@pytest.mark.asyncio
async def test_relative_redirect_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/jobs/123"})
        return httpx.Response(200, text=f"FINAL {request.url}")

    real_ctor = httpx.AsyncClient.__init__
    monkeypatch.setattr(
        httpx.AsyncClient,
        "__init__",
        lambda self, *a, **kw: real_ctor(
            self, *a, **{**kw, "transport": _mock_transport(handler)}
        ),
    )

    with _stub_resolver_per_host({"public.example": ["8.8.8.8"]}):
        result = await safe_follow_get("http://public.example/", timeout=2.0)
    assert result.status_code == 200
    assert "/jobs/123" in result.body
    assert len(result.redirect_chain) == 2


@pytest.mark.asyncio
async def test_too_many_redirects_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Loop forever between two paths.
        next_path = "/b" if request.url.path == "/a" else "/a"
        return httpx.Response(302, headers={"location": next_path})

    real_ctor = httpx.AsyncClient.__init__
    monkeypatch.setattr(
        httpx.AsyncClient,
        "__init__",
        lambda self, *a, **kw: real_ctor(
            self, *a, **{**kw, "transport": _mock_transport(handler)}
        ),
    )

    with _stub_resolver_per_host({"public.example": ["8.8.8.8"]}):
        with pytest.raises(UnsafeURLError, match="too_many_redirects"):
            await safe_follow_get(
                "http://public.example/a",
                timeout=2.0,
                max_redirects=2,
            )


@pytest.mark.asyncio
async def test_blocks_initial_url_on_loopback() -> None:
    with pytest.raises(UnsafeURLError):
        await safe_follow_get("http://127.0.0.1/", timeout=2.0)
