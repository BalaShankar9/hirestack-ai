"""ai_engine view of the SSRF guard (PR m5-pr15).

The guard lives in ``backend/app/core/safe_fetch.py``. ai_engine imports
it via the conftest sys.path (``backend/`` on path). This test exists
so refactors that decouple ai_engine from backend will fail loudly.
"""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import patch

import pytest


def test_safe_fetch_importable_from_ai_engine_context() -> None:
    from app.core.safe_fetch import assert_safe_url, UnsafeURLError  # noqa: F401


def test_blocks_metadata_call_for_researcher_use_case() -> None:
    from app.core.safe_fetch import assert_safe_url, UnsafeURLError

    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://169.254.169.254/latest/")


def test_allows_public_research_target() -> None:
    from app.core.safe_fetch import assert_safe_url

    def fake(*_a: Any, **_kw: Any):
        return [(socket.AF_INET, None, None, "", ("1.1.1.1", 0))]

    with patch("app.core.safe_fetch.socket.getaddrinfo", side_effect=fake):
        assert_safe_url("https://docs.example.com/article")
