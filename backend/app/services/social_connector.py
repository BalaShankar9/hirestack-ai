"""
Social Profile Connector
Fetches and extracts structured career data from external profiles (GitHub, LinkedIn, Portfolio, Twitter).
"""
import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import httpx
import structlog

logger = structlog.get_logger()

CONNECT_TIMEOUT = 15  # seconds


class SocialConnector:
    """Connects to external profiles and extracts career-relevant data."""

    async def connect(self, platform: str, url: str, profile_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Dispatch to platform-specific connector."""
        url = url.strip()
        if not url:
            raise ValueError("URL is required")

        if platform == "github":
            return await self._connect_github(url)
        elif platform == "linkedin":
            return await self._connect_linkedin(url, profile_data=profile_data)
        elif platform == "website":
            return await self._connect_website(url)
        elif platform == "twitter":
            return await self._connect_twitter(url)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    # ── GitHub ────────────────────────────────────────────────────

    async def _connect_github(self, url: str) -> Dict[str, Any]:
        """Fetch public GitHub profile via REST API (no auth required)."""
        username = self._extract_github_username(url)
        if not username:
            raise ValueError("Could not extract GitHub username from URL")

        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
            # Fetch user profile
            user_resp = await client.get(
                f"https://api.github.com/users/{username}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if user_resp.status_code == 404:
                raise ValueError(f"GitHub user '{username}' not found")
            if user_resp.status_code == 403:
                raise ValueError("GitHub API rate limit reached. Try again in a few minutes.")
            user_resp.raise_for_status()
            user_data = user_resp.json()

            # Fetch top repos (sorted by stars)
            repos_resp = await client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"sort": "stars", "direction": "desc", "per_page": 30},
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            repos_data = repos_resp.json() if repos_resp.status_code == 200 else []

        # Extract language statistics
        language_counts: Dict[str, int] = {}
        repos = []
        for repo in repos_data:
            if isinstance(repo, dict) and not repo.get("fork"):
                lang = repo.get("language")
                if lang:
                    language_counts[lang] = language_counts.get(lang, 0) + 1
                repos.append({
                    "name": repo.get("name"),
                    "description": repo.get("description", ""),
                    "language": lang,
                    "stars": repo.get("stargazers_count", 0),
                    "url": repo.get("html_url"),
                })

        total_repos_with_lang = sum(language_counts.values()) or 1
        top_languages = sorted(language_counts.keys(), key=lambda k: language_counts[k], reverse=True)[:8]
        language_summary = [
            {"language": lang, "repos": language_counts[lang], "percentage": round(language_counts[lang] / total_repos_with_lang * 100)}
            for lang in top_languages
        ]

        return {
            "status": "connected",
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "username": username,
                "bio": user_data.get("bio") or "",
                "name": user_data.get("name") or "",
                "company": user_data.get("company") or "",
                "location": user_data.get("location") or "",
                "public_repos": user_data.get("public_repos", 0),
                "followers": user_data.get("followers", 0),
                "following": user_data.get("following", 0),
                "top_languages": top_languages,
                "language_summary": language_summary,
                "top_repos": repos[:8],
                "profile_url": user_data.get("html_url"),
                "avatar_url": user_data.get("avatar_url"),
            },
        }

    def _extract_github_username(self, url: str) -> Optional[str]:
        """Extract GitHub username from URL."""
        # Handle: github.com/username, https://github.com/username, etc.
        url = url.rstrip("/")
        match = re.search(r"github\.com/([a-zA-Z0-9_-]+)/?$", url)
        if match:
            return match.group(1)
        # Maybe just a plain username
        if re.match(r"^[a-zA-Z0-9_-]+$", url):
            return url
        return None

    # ── LinkedIn ──────────────────────────────────────────────────

    async def _connect_linkedin(self, url: str, profile_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """LinkedIn: validate URL + AI-powered profile optimization analysis."""
        if not re.search(r"linkedin\.com/in/[a-zA-Z0-9_-]+", url):
            raise ValueError("Invalid LinkedIn URL. Expected format: linkedin.com/in/username")

        match = re.search(r"linkedin\.com/in/([a-zA-Z0-9_-]+)", url)
        slug = match.group(1) if match else ""

        result_data: Dict[str, Any] = {
            "slug": slug,
            "method": "ai_analysis",
        }

        # Always attempt AI analysis when profile data is available
        if profile_data:
            try:
                from ai_engine.client import AIClient
                from ai_engine.chains.linkedin_advisor import LinkedInAdvisorChain

                client = AIClient()
                chain = LinkedInAdvisorChain(client)
                analysis = await chain.analyze(profile_data)
                result_data["analysis"] = analysis
                logger.info("linkedin_analysis_complete", slug=slug, score=analysis.get("overall_score"))
            except Exception as e:
                logger.warning("linkedin_analysis_failed", error=str(e)[:200])
                result_data["analysis_error"] = str(e)[:200]

        return {
            "status": "connected",
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "data": result_data,
        }

    # ── Portfolio / Website ───────────────────────────────────────

    async def _connect_website(self, url: str) -> Dict[str, Any]:
        """Fetch website and extract metadata."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # SSRF protection: block requests to private/internal networks
        from urllib.parse import urlparse as _urlparse
        import socket
        from ipaddress import ip_address, ip_network

        _BLOCKED_NETWORKS = [
            ip_network("127.0.0.0/8"),
            ip_network("10.0.0.0/8"),
            ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"),
            ip_network("169.254.0.0/16"),  # AWS metadata
            ip_network("::1/128"),
            ip_network("fc00::/7"),
        ]

        parsed = _urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            raise ValueError("Invalid URL")

        try:
            # Resolve hostname to check the actual IP
            addr_info = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
            for family, _type, proto, canonname, sockaddr in addr_info:
                ip = ip_address(sockaddr[0])
                for network in _BLOCKED_NETWORKS:
                    if ip in network:
                        raise ValueError("URL resolves to a private/internal network address")
        except socket.gaierror:
            raise ValueError("Could not resolve hostname")

        try:
            async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "HireStack-AI/1.0 (Career Profile Connector)",
                })
                resp.raise_for_status()
                html = resp.text[:10000]  # Limit to first 10KB
        except httpx.HTTPStatusError as e:
            raise ValueError(f"Website returned {e.response.status_code}")
        except (httpx.ConnectError, httpx.TimeoutException):
            raise ValueError("Could not connect to website. Check the URL and try again.")

        # Extract metadata from HTML
        title = self._extract_html_tag(html, "title") or ""
        description = self._extract_meta(html, "description") or ""
        keywords = self._extract_meta(html, "keywords") or ""
        og_title = self._extract_meta(html, "og:title") or title
        og_description = self._extract_meta(html, "og:description") or description

        # Extract visible text snippet (strip HTML tags)
        import re as _re
        visible_text = _re.sub(r"<[^>]+>", " ", html)
        visible_text = _re.sub(r"\s+", " ", visible_text).strip()[:500]

        return {
            "status": "connected",
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "title": og_title or title,
                "description": og_description or description,
                "keywords": [k.strip() for k in keywords.split(",") if k.strip()][:10],
                "text_snippet": visible_text,
                "method": "metadata_extracted",
            },
        }

    def _extract_html_tag(self, html: str, tag: str) -> Optional[str]:
        match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else None

    def _extract_meta(self, html: str, name: str) -> Optional[str]:
        # Match both name= and property= attributes
        match = re.search(
            rf'<meta\s+(?:name|property)=["\'](?:{name})["\']\s+content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        if not match:
            # Try reversed attribute order
            match = re.search(
                rf'<meta\s+content=["\']([^"\']*)["\']\s+(?:name|property)=["\'](?:{name})["\']',
                html, re.IGNORECASE,
            )
        return match.group(1).strip() if match else None

    # ── Twitter / X ───────────────────────────────────────────────

    async def _connect_twitter(self, url: str) -> Dict[str, Any]:
        """Twitter/X: validate URL and extract handle."""
        match = re.search(r"(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)", url)
        if not match:
            # Maybe just a handle
            if re.match(r"^@?[a-zA-Z0-9_]+$", url):
                handle = url.lstrip("@")
            else:
                raise ValueError("Invalid Twitter/X URL. Expected format: twitter.com/handle or x.com/handle")
        else:
            handle = match.group(1)

        normalized_url = f"https://x.com/{handle}"

        return {
            "status": "linked",
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "handle": handle,
                "url": normalized_url,
                "method": "url_verified",
            },
        }
