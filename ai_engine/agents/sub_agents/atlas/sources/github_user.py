"""ATLAS v2 — GitHub user provider (zero-config, public REST API).

Fetches a candidate's public GitHub profile + repos and extracts
candidate-side signals that feed `CandidateFusion`:

  - top languages weighted by repo size (kB)
  - most recent push (→ "active" / "stale" recency band)
  - aggregate stars, forks, public-repo count
  - leadership signal proxy (repos owned + stargazer-count > 50)

GitHub's public REST API is free up to 60 req/hr unauthenticated and
5,000 req/hr with a token (set GITHUB_TOKEN). On 404 / network /
HTTP error, returns ``success=False`` without raising — the fusion
layer treats absence as "no signal", not as a hard failure.

Activation flag (for the future orchestrator wiring): the provider
class is always importable; whether the orchestrator actually CALLS
it is gated by ``RECON_GITHUB_USER_PROVIDER=real`` in the parent
slice that wires it in. This file is pure provider logic.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from ai_engine.agents.sub_agents.recon_swarm.schemas import ProviderResult

logger = logging.getLogger(__name__)


_GH_USER_URL = "https://api.github.com/users/{user}"
_GH_USER_REPOS_URL = "https://api.github.com/users/{user}/repos?per_page=100&type=owner&sort=updated"

# Recency bands for "most recently pushed repo" (days).
_ACTIVE_THRESHOLD_DAYS = 90
_STALE_THRESHOLD_DAYS = 365


class GitHubUserProvider:
    """Zero-config public GitHub user provider for ATLAS candidate fusion."""

    name = "github_user"
    layer = 1

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        token: Optional[str] = None,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = http_client
        self._token = token or os.getenv("GITHUB_TOKEN")
        self._timeout_s = timeout_s

    async def fetch(self, *, username: str, **_: Any) -> ProviderResult:
        s = time.perf_counter()
        slug = self._normalize_username(username)
        if not slug:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="empty username",
            )
        client, owned = await self._get_client()
        try:
            user_resp = await client.get(_GH_USER_URL.format(user=slug))
            if getattr(user_resp, "status_code", 0) != 200:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error=f"user lookup status={user_resp.status_code}",
                )
            repos_resp = await client.get(_GH_USER_REPOS_URL.format(user=slug))
            repos: List[Dict[str, Any]] = []
            if getattr(repos_resp, "status_code", 0) == 200:
                repos_payload = repos_resp.json()
                if isinstance(repos_payload, list):
                    repos = repos_payload
            payload = self._extract(user_resp.json() or {}, repos, slug)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("github_user fetch failed user=%s exc=%s", slug, exc)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error=str(exc)[:200],
            )
        finally:
            if owned:
                try:
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _normalize_username(username: str) -> Optional[str]:
        s = (username or "").strip()
        if not s:
            return None
        # Accept "@handle" and full URLs like "https://github.com/handle".
        if s.startswith("@"):
            s = s[1:]
        if "github.com/" in s:
            s = s.split("github.com/", 1)[1]
        s = s.strip("/").split("/", 1)[0]
        # GitHub handles: alphanumeric and hyphens, max 39 chars.
        cleaned = "".join(c for c in s if c.isalnum() or c == "-").strip("-")
        if not cleaned:
            return None
        return cleaned[:39].lower()

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "HireStack-AI-Atlas-Candidate",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.AsyncClient(timeout=self._timeout_s, headers=headers), True

    @staticmethod
    def _extract(
        user_payload: Dict[str, Any],
        repos: List[Dict[str, Any]],
        slug: str,
    ) -> Dict[str, Any]:
        # 1. Top languages weighted by repo size (kB) — size is a better
        #    proxy for actual code investment than repo count.
        lang_size_kb: Dict[str, int] = {}
        for r in repos:
            lang = r.get("language")
            size = int(r.get("size") or 0)
            if lang and size > 0:
                lang_size_kb[lang] = lang_size_kb.get(lang, 0) + size
        top_languages = [
            {"name": lang, "size_kb": kb}
            for lang, kb in sorted(lang_size_kb.items(), key=lambda kv: kv[1], reverse=True)[:10]
        ]

        # 2. Recency band from the most recent push across owned repos.
        most_recent_push = None
        for r in repos:
            pa = r.get("pushed_at")
            if pa and (most_recent_push is None or pa > most_recent_push):
                most_recent_push = pa
        recency = _classify_recency(most_recent_push)

        # 3. Aggregates.
        total_stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
        total_forks = sum(int(r.get("forks_count") or 0) for r in repos)
        repos_with_traction = sum(
            1 for r in repos if int(r.get("stargazers_count") or 0) >= 50
        )

        return {
            "username": slug,
            "name": user_payload.get("name") or "",
            "bio": user_payload.get("bio") or "",
            "company": user_payload.get("company") or "",
            "blog": user_payload.get("blog") or "",
            "location": user_payload.get("location") or "",
            "hireable": bool(user_payload.get("hireable")),
            "public_repos": int(user_payload.get("public_repos") or 0),
            "followers": int(user_payload.get("followers") or 0),
            "created_at": user_payload.get("created_at") or "",
            "top_languages": top_languages,
            "most_recent_push": most_recent_push or "",
            "recency_band": recency,
            "total_stars": total_stars,
            "total_forks": total_forks,
            "repos_with_traction": repos_with_traction,
            "leadership_signal": repos_with_traction >= 1,
        }


def _classify_recency(most_recent_push: Optional[str]) -> str:
    """Bucket the most-recent push timestamp into active/recent/stale/none."""
    if not most_recent_push:
        return "none"
    from datetime import datetime, timezone
    try:
        # GitHub returns ISO-8601 with trailing Z.
        ts = most_recent_push.rstrip("Z")
        pushed = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return "unknown"
    delta_days = (datetime.now(timezone.utc) - pushed).days
    if delta_days < _ACTIVE_THRESHOLD_DAYS:
        return "active"
    if delta_days < _STALE_THRESHOLD_DAYS:
        return "recent"
    return "stale"
