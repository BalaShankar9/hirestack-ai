"""Phase 1.2 — LinkedInPublicProvider unit tests."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_engine.agents.sub_agents.atlas.sources.linkedin_public import (
    LinkedInPublicProvider,
    _split_og_title,
)


# ───── Fake httpx ─────


class _FakeResp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> Any:
        return {}


class _FakeClient:
    def __init__(self, route_map: dict) -> None:
        self._routes = route_map
        self.calls: list[str] = []

    async def get(self, url: str, **_kw: Any) -> _FakeResp:
        self.calls.append(url)
        for prefix, resp in self._routes.items():
            if url.startswith(prefix):
                return resp
        return _FakeResp(404, "")

    async def aclose(self) -> None:
        pass


def _run(coro):
    return asyncio.run(coro)


# ───── slug normalization ─────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ada-lovelace", "ada-lovelace"),
        ("Ada-Lovelace", "ada-lovelace"),
        ("https://www.linkedin.com/in/ada-lovelace/", "ada-lovelace"),
        ("https://linkedin.com/in/ada-lovelace?foo=bar", "ada-lovelace"),
        ("linkedin.com/in/ada_lovelace/details/experience", "ada_lovelace"),
        ("", None),
        ("   ", None),
        ("!!!", None),
    ],
)
def test_normalize_slug(raw, expected):
    assert LinkedInPublicProvider._normalize_slug(raw) == expected


# ───── og:title splitter ─────


def test_split_og_title_standard():
    assert _split_og_title("Ada Lovelace - Staff Engineer at Acme | LinkedIn") == (
        "Ada Lovelace",
        "Staff Engineer at Acme",
    )


def test_split_og_title_no_dash():
    assert _split_og_title("Ada Lovelace | LinkedIn") == ("Ada Lovelace", "")


def test_split_og_title_no_linkedin_suffix():
    assert _split_og_title("Ada Lovelace - Engineer") == ("Ada Lovelace", "Engineer")


# ───── block detection ─────


def test_is_blocked_authwall():
    assert LinkedInPublicProvider._is_blocked("<html>Sign in to LinkedIn</html>") is True
    assert LinkedInPublicProvider._is_blocked("<div class='authwall'>") is True


def test_is_blocked_negative():
    assert LinkedInPublicProvider._is_blocked("<html><title>Profile</title></html>") is False


# ───── fetch happy path ─────


_HAPPY_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>Ada Lovelace - Staff Engineer at Acme | LinkedIn</title>
  <meta property="og:title" content="Ada Lovelace - Staff Engineer at Acme | LinkedIn" />
  <meta property="og:description" content="Building reliable systems at Acme. 10+ years." />
  <meta property="og:image" content="https://media.licdn.com/img.jpg" />
  <meta property="og:url" content="https://www.linkedin.com/in/ada-lovelace" />
</head>
<body>Profile content</body>
</html>
"""


def test_fetch_happy_path_extracts_meta():
    client = _FakeClient({
        "https://www.linkedin.com/in/ada-lovelace": _FakeResp(200, _HAPPY_HTML),
    })
    p = LinkedInPublicProvider(http_client=client)
    result = _run(p.fetch(profile_slug="ada-lovelace"))
    assert result.success is True
    assert result.provider == "linkedin_public"
    raw = result.raw
    assert raw["slug"] == "ada-lovelace"
    assert raw["name"] == "Ada Lovelace"
    assert raw["headline"] == "Staff Engineer at Acme"
    assert raw["description"].startswith("Building reliable systems")
    assert raw["image_url"] == "https://media.licdn.com/img.jpg"
    assert raw["profile_url"] == "https://www.linkedin.com/in/ada-lovelace"


# ───── fetch failure modes ─────


def test_fetch_999_login_wall_returns_failure():
    client = _FakeClient({
        "https://www.linkedin.com/in/ada-lovelace": _FakeResp(999, ""),
    })
    p = LinkedInPublicProvider(http_client=client)
    result = _run(p.fetch(profile_slug="ada-lovelace"))
    assert result.success is False
    assert "999" in (result.error or "")


def test_fetch_200_with_authwall_html_returns_failure():
    blocked_html = "<html><body>Sign in to LinkedIn to continue</body></html>"
    client = _FakeClient({
        "https://www.linkedin.com/in/ada-lovelace": _FakeResp(200, blocked_html),
    })
    p = LinkedInPublicProvider(http_client=client)
    result = _run(p.fetch(profile_slug="ada-lovelace"))
    assert result.success is False
    assert "authwall" in (result.error or "")


def test_fetch_empty_slug_short_circuits():
    p = LinkedInPublicProvider(http_client=_FakeClient({}))
    result = _run(p.fetch(profile_slug="   "))
    assert result.success is False
    assert result.error == "empty profile slug"


def test_fetch_swallows_unexpected_exceptions():
    class _BoomClient:
        async def get(self, url: str, **_: Any) -> Any:
            raise RuntimeError("network down")

        async def aclose(self) -> None:
            pass

    p = LinkedInPublicProvider(http_client=_BoomClient())
    result = _run(p.fetch(profile_slug="ada"))
    assert result.success is False
    assert "network down" in (result.error or "")


def test_fetch_200_empty_body_returns_failure():
    client = _FakeClient({
        "https://www.linkedin.com/in/ada-lovelace": _FakeResp(200, ""),
    })
    p = LinkedInPublicProvider(http_client=client)
    result = _run(p.fetch(profile_slug="ada-lovelace"))
    assert result.success is False


def test_extract_minimal_html_no_meta():
    """Minimal HTML with only title — extractor must not blow up."""
    html = "<html><head><title>Bob - Eng | LinkedIn</title></head></html>"
    client = _FakeClient({
        "https://www.linkedin.com/in/bob": _FakeResp(200, html),
    })
    p = LinkedInPublicProvider(http_client=client)
    result = _run(p.fetch(profile_slug="bob"))
    assert result.success is True
    raw = result.raw
    assert raw["name"] == "Bob"
    assert raw["headline"] == "Eng"
    assert raw["image_url"] == ""
    assert raw["description"] == ""


def test_ua_index_rotation():
    """Different ua_index values pick different UA strings."""
    p0 = LinkedInPublicProvider(ua_index=0)
    p1 = LinkedInPublicProvider(ua_index=1)
    p2 = LinkedInPublicProvider(ua_index=2)
    p3 = LinkedInPublicProvider(ua_index=3)  # wraps
    assert p0._ua != p1._ua != p2._ua
    assert p0._ua == p3._ua
