"""
CareersIntelAgent — careers page deep analysis and open-role cross-reference.

Crawls careers/jobs pages, extracts open positions, team structure,
benefits, interview process hints, and hiring velocity signals.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import httpx
import structlog

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.careers")

_USER_AGENT = "Mozilla/5.0 (compatible; HireStack-AI/2.0; Career Intelligence)"
_TIMEOUT = 6

_CAREERS_PATHS = [
    "/careers", "/jobs", "/careers/", "/jobs/",
    "/join-us", "/join", "/work-with-us", "/hiring",
    "/open-positions", "/opportunities",
]

# Common ATS platforms in URLs
_ATS_PATTERNS = {
    "greenhouse": r"boards\.greenhouse\.io",
    "lever": r"jobs\.lever\.co",
    "workday": r"myworkdayjobs\.com",
    "ashby": r"jobs\.ashbyhq\.com",
    "bamboohr": r"[^/]+\.bamboohr\.com/careers",
    "icims": r"careers-[^.]+\.icims\.com",
    "smartrecruiters": r"jobs\.smartrecruiters\.com",
}


def _guess_urls(company: str, company_url: Optional[str]) -> list[str]:
    """Generate careers page URL candidates."""
    urls: list[str] = []
    bases: list[str] = []
    if company_url:
        bases.append(company_url.rstrip("/"))

    clean = re.sub(r"\s*(Inc|Ltd|LLC|Corp|Limited|PLC|GmbH|SA|AG|Co)\.?\s*$", "", company, flags=re.IGNORECASE)
    clean = re.sub(r"[^a-zA-Z0-9]", "", clean).lower()
    if len(clean) >= 2:
        bases.extend([f"https://www.{clean}.com", f"https://{clean}.io", f"https://{clean}.ai"])

    for base in bases:
        for path in _CAREERS_PATHS:
            urls.append(base + path)

    # Also try common ATS direct URLs
    if len(clean) >= 2:
        urls.append(f"https://boards.greenhouse.io/{clean}")
        urls.append(f"https://jobs.lever.co/{clean}")
        urls.append(f"https://jobs.ashbyhq.com/{clean}")
        urls.append(f"https://apply.workable.com/{clean}")

    return urls


class CareersIntelAgent(SubAgent):
    """Careers page analysis — open roles, team structure, benefits, ATS detection."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="careers_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company", "") or context.get("company_name", "")
        company_url = context.get("company_url")
        on_event = context.get("on_event")

        if not company:
            return SubAgentResult(agent_name=self.name, error="No company name")

        candidate_urls = _guess_urls(company, company_url)

        if on_event:
            await _emit(on_event, f"Scanning {len(candidate_urls)} careers page candidates…", "running", "careers")

        # Try all URLs in parallel with a batch approach
        # First batch: most likely URLs
        first_batch = candidate_urls[:8]
        second_batch = candidate_urls[8:16]

        careers_content = None
        careers_url = None

        for batch in [first_batch, second_batch]:
            if careers_content:
                break
            results = await asyncio.gather(
                *[_fetch(url) for url in batch],
                return_exceptions=True,
            )
            for url, result in zip(batch, results):
                if isinstance(result, Exception) or not result:
                    continue
                if len(result) > 200:
                    careers_content = result
                    careers_url = url
                    break

        if not careers_content:
            if on_event:
                await _emit(on_event, "No careers page found.", "warning", "careers")
            return SubAgentResult(
                agent_name=self.name,
                data={"status": "no_careers_page", "urls_tried": len(candidate_urls)},
                confidence=0.1,
            )

        if on_event:
            await _emit(on_event, f"Careers page found at {careers_url}. Analyzing…", "running", "careers", url=careers_url)

        # Extract careers-specific intel
        extracted = self._extract_careers_data(careers_content, careers_url or "")

        if on_event:
            role_count = extracted.get("estimated_open_roles", 0)
            await _emit(
                on_event,
                f"Careers intel gathered: ~{role_count} open roles detected.",
                "completed", "careers",
                url=careers_url,
                metadata={"open_roles": role_count, "ats": extracted.get("ats_platform", "unknown")},
            )

        # Build evidence
        evidence_items: list[dict] = []
        if extracted.get("ats_platform"):
            evidence_items.append({
                "fact": f"Company uses {extracted['ats_platform']} ATS",
                "source": "careers:ats",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })
        if extracted.get("benefits"):
            evidence_items.append({
                "fact": f"Benefits mentioned: {', '.join(extracted['benefits'][:8])}",
                "source": "careers:benefits",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })
        if extracted.get("teams_hiring"):
            evidence_items.append({
                "fact": f"Teams hiring: {', '.join(extracted['teams_hiring'][:8])}",
                "source": "careers:teams",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })
        evidence_items.append({
            "fact": f"Careers page content ({len(careers_content)} chars) from {careers_url}",
            "source": "careers:page",
            "tier": "VERBATIM",
            "sub_agent": self.name,
        })

        confidence = min(0.90, 0.4 + (0.1 if extracted.get("benefits") else 0) +
                         (0.15 if extracted.get("estimated_open_roles", 0) > 0 else 0) +
                         (0.1 if extracted.get("ats_platform") else 0))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "careers_url": careers_url,
                "full_text": self._clean_html(careers_content)[:8000],
                **extracted,
            },
            evidence_items=evidence_items,
            confidence=confidence,
        )

    def _extract_careers_data(self, html: str, url: str) -> dict[str, Any]:
        """Extract structured careers intel from HTML."""
        lower = html.lower()
        result: dict[str, Any] = {}

        # Detect ATS platform
        for name, pattern in _ATS_PATTERNS.items():
            if re.search(pattern, url, re.IGNORECASE):
                result["ats_platform"] = name
                break
        if "ats_platform" not in result:
            if "greenhouse" in lower:
                result["ats_platform"] = "greenhouse"
            elif "lever" in lower:
                result["ats_platform"] = "lever"
            elif "workday" in lower:
                result["ats_platform"] = "workday"

        # Estimate open roles count from job listing patterns
        role_patterns = re.findall(
            r'<(?:li|div|a|tr)[^>]*class=["\'][^"\']*(?:job|position|opening|role|listing)[^"\']*["\'][^>]*>',
            html, re.IGNORECASE,
        )
        result["estimated_open_roles"] = len(role_patterns) if role_patterns else 0

        # Extract benefits
        benefits = []
        benefit_keywords = [
            "health insurance", "dental", "vision", "401k", "401(k)", "equity",
            "stock options", "remote", "hybrid", "flexible hours", "unlimited pto",
            "unlimited vacation", "parental leave", "learning budget", "education",
            "gym", "wellness", "mental health", "free lunch", "snacks",
            "home office", "sabbatical", "childcare",
        ]
        for kw in benefit_keywords:
            if kw in lower:
                benefits.append(kw)
        result["benefits"] = benefits

        # Extract team names from headings
        teams = set()
        team_patterns = re.findall(
            r'(?:engineering|product|design|marketing|sales|data|security|platform|infrastructure|devops|mobile|frontend|backend|fullstack|full-stack|machine learning|ai|ml)',
            lower,
        )
        teams.update(t.title() for t in team_patterns)
        result["teams_hiring"] = sorted(teams)

        # Work model signals
        if "remote" in lower:
            result["work_model"] = "remote" if "fully remote" in lower or "100% remote" in lower else "hybrid/remote"
        elif "hybrid" in lower:
            result["work_model"] = "hybrid"
        elif "on-site" in lower or "onsite" in lower:
            result["work_model"] = "on-site"

        # Interview process hints
        interview_hints = []
        if "take-home" in lower or "take home" in lower:
            interview_hints.append("take-home assignment")
        if "pair programming" in lower:
            interview_hints.append("pair programming")
        if "system design" in lower:
            interview_hints.append("system design interview")
        if "behavioral" in lower:
            interview_hints.append("behavioral interview")
        if "culture fit" in lower or "culture add" in lower:
            interview_hints.append("culture assessment")
        if "technical screen" in lower:
            interview_hints.append("technical screen")
        result["interview_hints"] = interview_hints

        return result

    def _clean_html(self, html: str) -> str:
        """Strip HTML to text."""
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()


async def _fetch(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html"})
            if resp.status_code != 200:
                return ""
            return resp.text[:30000]
    except Exception:
        return ""


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
