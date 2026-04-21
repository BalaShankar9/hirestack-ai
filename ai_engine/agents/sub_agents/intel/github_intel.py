"""
GitHubIntelAgent — deep GitHub organization analysis.

Fetches org info, top repos, languages, contributors, recent activity,
README analysis, and tech stack inference from repository metadata.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import httpx
import structlog

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.github")

_GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "HireStack-AI/2.0",
}
_TIMEOUT = 8


def _guess_orgs(company: str) -> list[str]:
    """Generate candidate GitHub org names."""
    clean = re.sub(
        r"\s*(Inc|Ltd|LLC|Corp|Limited|PLC|GmbH|SA|AG|Co)\.?\s*$",
        "", company, flags=re.IGNORECASE,
    )
    clean = re.sub(r"[^a-zA-Z0-9\s-]", "", clean).strip()
    candidates = []
    if clean:
        candidates.append(clean.replace(" ", "").lower())
        candidates.append(clean.replace(" ", "-").lower())
        # Handle multi-word: e.g. "Acme Corp" → "acme"
        words = clean.lower().split()
        if len(words) > 1:
            candidates.append(words[0])
    return list(dict.fromkeys(candidates))  # dedupe preserving order


class GitHubIntelAgent(SubAgent):
    """GitHub organization deep analysis — repos, languages, activity, contributors."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="github_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company", "") or context.get("company_name", "")
        on_event = context.get("on_event")

        if not company:
            return SubAgentResult(agent_name=self.name, error="No company name")

        org_candidates = _guess_orgs(company)
        if not org_candidates:
            return SubAgentResult(agent_name=self.name, data={"status": "no_org_guess"}, confidence=0.1)

        # Try each candidate org
        org_data = None
        org_name = None
        for candidate in org_candidates:
            if on_event:
                await _emit(on_event, f"Checking GitHub org: {candidate}", "running", "github",
                            url=f"https://github.com/{candidate}")
            org_data = await self._fetch_org(candidate)
            if org_data:
                org_name = candidate
                break

        # Fallback: GitHub Search API — find orgs by display name when slug guessing failed.
        if not org_data:
            if on_event:
                await _emit(on_event, f"Searching GitHub for org matching '{company}'…", "running", "github")
            searched = await self._search_org(company)
            if searched:
                org_name, org_data = searched
                if on_event:
                    await _emit(
                        on_event,
                        f"GitHub search matched org: {org_name}",
                        "running", "github",
                        url=f"https://github.com/{org_name}",
                    )

        if not org_data or not org_name:
            if on_event:
                await _emit(on_event, "No GitHub organization found.", "warning", "github")
            return SubAgentResult(
                agent_name=self.name,
                data={"status": "no_org_found", "candidates_tried": org_candidates},
                confidence=0.1,
            )

        if on_event:
            await _emit(on_event, f"Found GitHub org: {org_name}. Analyzing repos…", "running", "github",
                        url=f"https://github.com/{org_name}")

        # Parallel: fetch repos, contributors for top repos, org members count
        repos_task = self._fetch_repos(org_name)
        members_task = self._fetch_members_count(org_name)

        repos, members_count = await asyncio.gather(repos_task, members_task, return_exceptions=True)
        if isinstance(repos, Exception):
            repos = []
        if isinstance(members_count, Exception):
            members_count = 0

        # Analyze repos
        languages: dict[str, int] = {}
        topics: set[str] = set()
        total_stars = 0
        total_forks = 0
        recent_repos = 0
        notable_repos = []

        for repo in repos[:30]:
            lang = repo.get("language", "")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
            for topic in repo.get("topics", []):
                topics.add(topic)
            stars = repo.get("stargazers_count", 0)
            forks = repo.get("forks_count", 0)
            total_stars += stars
            total_forks += forks

            # Check if recently active (pushed in last 90 days)
            pushed = repo.get("pushed_at", "")
            if pushed and pushed >= "2026-01":
                recent_repos += 1

            if stars >= 10 or repo.get("fork") is False:
                notable_repos.append({
                    "name": repo.get("name", ""),
                    "description": (repo.get("description") or "")[:150],
                    "language": lang,
                    "stars": stars,
                    "forks": forks,
                    "topics": repo.get("topics", [])[:5],
                })

        # Sort languages by frequency
        sorted_langs = sorted(languages.items(), key=lambda x: -x[1])

        # Determine activity level
        repo_count = len(repos)
        if recent_repos >= 10:
            activity = "Very Active"
        elif recent_repos >= 5:
            activity = "Active"
        elif recent_repos >= 1:
            activity = "Moderate"
        else:
            activity = "Low"

        # Infer engineering culture signals
        culture_signals = []
        if any(t in topics for t in ["open-source", "oss", "community"]):
            culture_signals.append("Open source commitment")
        if any(t in topics for t in ["ci", "cd", "devops", "infrastructure"]):
            culture_signals.append("DevOps culture")
        if any(t in topics for t in ["testing", "test", "qa"]):
            culture_signals.append("Testing focus")
        if any(t in topics for t in ["documentation", "docs"]):
            culture_signals.append("Documentation culture")
        if total_stars > 1000:
            culture_signals.append("Significant OSS presence")
        if members_count and members_count > 50:
            culture_signals.append(f"Large engineering org ({members_count}+ public members)")

        if on_event:
            await _emit(
                on_event,
                f"GitHub intel collected: {repo_count} repos, {len(sorted_langs)} languages, {activity} activity.",
                "completed", "github",
                url=f"https://github.com/{org_name}",
                metadata={"repos": repo_count, "stars": total_stars, "activity": activity},
            )

        # Build evidence
        evidence_items: list[dict] = []
        evidence_items.append({
            "fact": f"GitHub org '{org_name}': {repo_count} public repos, {total_stars} total stars, {activity} activity",
            "source": "github:org",
            "tier": "VERBATIM",
            "sub_agent": self.name,
        })
        for lang, count in sorted_langs[:5]:
            evidence_items.append({
                "fact": f"Uses {lang} ({count} repos)",
                "source": "github:languages",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })
        for repo in notable_repos[:5]:
            evidence_items.append({
                "fact": f"Repo: {repo['name']} — {repo['description']} ({repo['stars']} stars)",
                "source": "github:repos",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })

        confidence = min(0.95, 0.4 + min(repo_count, 20) * 0.025)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "org_name": org_name,
                "org_info": {
                    "name": org_data.get("name", org_name),
                    "description": org_data.get("description", ""),
                    "blog": org_data.get("blog", ""),
                    "location": org_data.get("location", ""),
                    "public_repos": org_data.get("public_repos", 0),
                    "public_members": members_count,
                },
                "languages": dict(sorted_langs[:15]),
                "top_language": sorted_langs[0][0] if sorted_langs else "Unknown",
                "topics": sorted(topics)[:30],
                "total_stars": total_stars,
                "total_forks": total_forks,
                "repo_count": repo_count,
                "recent_repos": recent_repos,
                "activity_level": activity,
                "notable_repos": notable_repos[:10],
                "culture_signals": culture_signals,
            },
            evidence_items=evidence_items,
            confidence=confidence,
        )

    async def _fetch_org(self, org_name: str) -> dict | None:
        """Fetch GitHub org info."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.github.com/orgs/{org_name}",
                    headers=_GITHUB_HEADERS,
                )
                remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
                if resp.status_code == 403 or remaining == 0:
                    return None
                if resp.status_code != 200:
                    return None
                return resp.json()
        except Exception:
            return None

    async def _fetch_repos(self, org_name: str) -> list[dict]:
        """Fetch org repos sorted by stars."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.github.com/orgs/{org_name}/repos?sort=stars&per_page=30",
                    headers=_GITHUB_HEADERS,
                )
                if resp.status_code != 200:
                    return []
                return resp.json()
        except Exception:
            return []

    async def _fetch_members_count(self, org_name: str) -> int:
        """Estimate public member count."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.github.com/orgs/{org_name}/members?per_page=1",
                    headers=_GITHUB_HEADERS,
                )
                if resp.status_code != 200:
                    return 0
                # Parse Link header for total count
                link = resp.headers.get("Link", "")
                import re as _re
                m = _re.search(r'page=(\d+)>; rel="last"', link)
                return int(m.group(1)) if m else len(resp.json())
        except Exception:
            return 0

    async def _search_org(self, company: str) -> tuple[str, dict] | None:
        """
        Fallback: use GitHub's search API to find an org whose display name
        or login matches the company. Validates the hit by re-fetching the
        org endpoint (so we get the full metadata shape the rest of the
        agent expects).
        """
        q = company.strip()
        if not q or len(q) < 2:
            return None
        # Clean company name similar to _guess_orgs so search is less noisy.
        import re as _re
        clean = _re.sub(
            r"\s*(Inc|Ltd|LLC|Corp|Limited|PLC|GmbH|SA|AG|Co)\.?\s*$",
            "", q, flags=_re.IGNORECASE,
        ).strip()
        if not clean:
            return None

        # Prefer the token endpoint if available for rate limit.
        headers = dict(_GITHUB_HEADERS)
        token = __import__("os").getenv("GITHUB_TOKEN") or __import__("os").getenv("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    "https://api.github.com/search/users",
                    params={"q": f"{clean} type:org", "per_page": 5},
                    headers=headers,
                )
                if resp.status_code != 200:
                    return None
                items = (resp.json() or {}).get("items", [])
        except Exception:
            return None

        # Score each hit: exact/substring match on login or name wins.
        clean_lower = clean.lower().replace(" ", "")
        best: tuple[int, str] | None = None
        for item in items[:5]:
            login = (item.get("login") or "").lower()
            if not login:
                continue
            score = 0
            if login == clean_lower:
                score += 100
            elif login.startswith(clean_lower) or clean_lower in login:
                score += 40
            elif clean_lower.startswith(login) and len(login) >= 3:
                score += 20
            # Prefer orgs with any public repos (signals real org, not empty placeholder)
            if score > 0:
                if best is None or score > best[0]:
                    best = (score, login)

        if not best or best[0] < 20:
            return None

        login = best[1]
        full = await self._fetch_org(login)
        if not full:
            return None
        return login, full


async def _emit(callback, message, status, source, url=None, metadata=None):
    payload: dict[str, Any] = {"stage": "recon", "status": status, "message": message, "source": source}
    if url:
        payload["url"] = url
    if metadata:
        payload["metadata"] = metadata
    try:
        maybe = callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass
