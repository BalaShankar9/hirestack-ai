"""Tests that ghost_check.fetch_posting honours the SSRF gate (PR m6-pr20)."""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import patch

import pytest

from app.api.routes import ghost_check as gc


def _stub_resolver(*ips: str):
    def fake(host: str, *_a: Any, **_k: Any):
        return [(socket.AF_INET, None, None, "", (ip, 0)) for ip in ips]

    return patch("app.core.safe_fetch.socket.getaddrinfo", side_effect=fake)


@pytest.mark.asyncio
async def test_fetch_posting_blocks_metadata_ip() -> None:
    """Direct literal metadata IP is refused before the socket opens."""
    status, final, body = await gc.fetch_posting("http://169.254.169.254/latest/meta-data/")
    assert status == 0
    assert body == ""


@pytest.mark.asyncio
async def test_fetch_posting_blocks_loopback() -> None:
    status, _final, body = await gc.fetch_posting("http://127.0.0.1:8080/foo")
    assert status == 0
    assert body == ""


@pytest.mark.asyncio
async def test_fetch_posting_blocks_dns_to_private() -> None:
    """Public-looking host that resolves to RFC1918 must be refused."""
    with _stub_resolver("10.0.5.5"):
        status, _f, body = await gc.fetch_posting("http://attacker.example/job/1")
    assert status == 0
    assert body == ""
