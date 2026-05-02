"""Phase 1.1 — GitHubUserProvider unit tests.

Pure-function, fake-httpx-client tests. No live network unless
RUN_RECON_LIVE=1 (one optional smoke test for that mode).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ai_engine.agents.sub_agents.atlas.sources.github_user import (
    GitHubUserProvider,
    _classify_recency,
)


# ───── Fake httpx (mirrors the recon_swarm test pattern) ─────


class _FakeResp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return self._payload if isinstance(self._payload, str) else ""


class _FakeClient:
    def __init__(self, route_map: dict) -> None:
        self._routes = route_map
        self.calls: list[str] = []

    async def get(self, url: str, **_kw: Any) -> _FakeResp:
        self.calls.append(url)
        # Longest-prefix wins.
        best = None
        best_len = -1
        for prefix, resp in self._routes.items():
            if url.startswith(prefix) and len(prefix) > best_len:
                best = resp
                best_len = len(prefix)
        return best if best is not None else _FakeResp(404, {})

    async def aclose(self) -> None:
        pass


# ───── username normalization ─────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("alice", "alice"),
        ("@alice", "alice"),
        ("  Alice  ", "alice"),
        ("https://github.com/Alice/", "alice"),
        ("https://github.com/alice/repo/issues", "alice"),
        ("a-very-long-username-" + "x" * 40, ("a-very-long-username-" + "x" * 40)[:39].lower()),
        ("", None),
        ("   ", None),
        ("!!!", None),
    ],
)
def test_normalize_username(raw, expected):
    assert GitHubUserProvider._normalize_username(raw) == expected


# ───── recency classifier ─────


def _iso_n_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat().replace("+00:00", "Z")


def test_recency_active():
    assert _classify_recency(_iso_n_days_ago(10)) == "active"


def test_recency_recent():
    assert _classify_recency(_iso_n_days_ago(180)) == "recent"


def test_recency_stale():
    assert _classify_recency(_iso_n_days_ago(800)) == "stale"


def test_recency_none_and_unknown():
    assert _classify_recency(None) == "none"
    assert _classify_recency("") == "none"
    assert _classify_recency("not-a-date") == "unknown"


# ───── fetch happy path ─────


def _run(coro):
    return asyncio.run(coro)


def test_fetch_happy_path_extracts_languages_and_aggregates():
    user_payload = {
        "name": "Ada Lovelace",
        "bio": "Engineer",
        "company": "@analytical-engine",
        "blog": "https://ada.example",
        "location": "London",
        "hireable": True,
        "public_repos": 3,
        "followers": 200,
        "created_at": "2018-01-01T00:00:00Z",
    }
    repos_payload = [
        {"language": "Python", "size": 5000, "stargazers_count": 100, "forks_count": 10,
         "pushed_at": _iso_n_days_ago(5)},
        {"language": "Python", "size": 2000, "stargazers_count": 5, "forks_count": 0,
         "pushed_at": _iso_n_days_ago(40)},
        {"language": "Rust", "size": 800, "stargazers_count": 60, "forks_count": 2,
         "pushed_at": _iso_n_days_ago(120)},
    ]
    client = _FakeClient({
        "https://api.github.com/users/ada": _FakeResp(200, user_payload),
        "https://api.github.com/users/ada/repos": _FakeResp(200, repos_payload),
    })
    p = GitHubUserProvider(http_client=client)

    result = _run(p.fetch(username="ada"))

    assert result.success is True
    assert result.provider == "github_user"
    assert result.layer == 1
    raw = result.raw
    # Top languages weighted by size: Python 7000 first, Rust 800 second.
    assert raw["top_languages"][0] == {"name": "Python", "size_kb": 7000}
    assert raw["top_languages"][1] == {"name": "Rust", "size_kb": 800}
    assert raw["total_stars"] == 165
    assert raw["total_forks"] == 12
    assert raw["repos_with_traction"] == 2  # Python(100) + Rust(60)
    assert raw["leadership_signal"] is True
    assert raw["recency_band"] == "active"
    assert raw["name"] == "Ada Lovelace"
    assert raw["hireable"] is True


def test_fetch_user_404_returns_failure_no_raise():
    client = _FakeClient({})  # everything 404s
    p = GitHubUserProvider(http_client=client)
    result = _run(p.fetch(username="ghost-user"))
    assert result.success is False
    assert "404" in (result.error or "")


def test_fetch_repos_failure_still_returns_success_with_empty_repo_signals():
    client = _FakeClient({
        "https://api.github.com/users/bob": _FakeResp(200, {"public_repos": 0}),
        # /repos URL deliberately absent → 404
    })
    p = GitHubUserProvider(http_client=client)
    result = _run(p.fetch(username="bob"))
    assert result.success is True
    raw = result.raw
    assert raw["top_languages"] == []
    assert raw["total_stars"] == 0
    assert raw["recency_band"] == "none"
    assert raw["leadership_signal"] is False


def test_fetch_empty_username_short_circuits():
    p = GitHubUserProvider(http_client=_FakeClient({}))
    result = _run(p.fetch(username="   "))
    assert result.success is False
    assert result.error == "empty username"


def test_fetch_swallows_unexpected_exceptions():
    class _BoomClient:
        async def get(self, url: str, **_: Any) -> Any:
            raise RuntimeError("network boom")

        async def aclose(self) -> None:
            pass

    p = GitHubUserProvider(http_client=_BoomClient())
    result = _run(p.fetch(username="anyone"))
    assert result.success is False
    assert "network boom" in (result.error or "")


def test_top_languages_capped_at_ten():
    user_payload = {"public_repos": 12}
    repos_payload = [
        {"language": f"Lang{i}", "size": (12 - i) * 100, "stargazers_count": 0, "forks_count": 0,
         "pushed_at": _iso_n_days_ago(30)}
        for i in range(12)
    ]
    client = _FakeClient({
        "https://api.github.com/users/poly": _FakeResp(200, user_payload),
        "https://api.github.com/users/poly/repos": _FakeResp(200, repos_payload),
    })
    p = GitHubUserProvider(http_client=client)
    result = _run(p.fetch(username="poly"))
    assert len(result.raw["top_languages"]) == 10
    # First entry is the largest.
    assert result.raw["top_languages"][0]["name"] == "Lang0"


# ───── Optional live smoke test ─────


@pytest.mark.skipif(
    os.getenv("RUN_RECON_LIVE") != "1",
    reason="set RUN_RECON_LIVE=1 to hit live GitHub API",
)
def test_live_github_user_octocat():
    p = GitHubUserProvider()
    result = _run(p.fetch(username="octocat"))
    assert result.success is True
    assert result.raw["username"] == "octocat"
    assert result.raw["public_repos"] >= 1
