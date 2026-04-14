"""
Company Intelligence Chain — Multi-Source Intel Gathering
Gathers intelligence from multiple sources about a target company:
  1. Company website (homepage, about, careers pages)
  2. Job description analysis (culture signals, tech stack, requirements)
  3. GitHub organization (repos, languages, activity)
  4. Public API data where available

Returns a structured intel report used by document generation agents.
"""
import re
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
import httpx
import structlog

logger = structlog.get_logger()


IntelEventCallback = Callable[[Dict[str, Any]], Awaitable[None] | None]


INTEL_SYSTEM = """You are an elite corporate intelligence analyst. Given raw data from multiple sources
about a company, you extract and synthesize actionable intelligence for job applicants.

Your analysis must be:
- FACTUAL: Only state what the data supports. Never fabricate company details.
- SPECIFIC: Cite real products, real values, real tech. Generic advice is useless.
- ACTIONABLE: Every insight should help the candidate write a better application or prepare for an interview.
- HONEST: If data is limited, say so. Mark confidence levels accurately.

Return ONLY valid JSON."""

INTEL_PROMPT = """Analyze all gathered data about this company for a job applicant targeting: {job_title}

COMPANY NAME: {company}

=== SOURCE 1: COMPANY WEBSITE ===
{web_data}

=== SOURCE 2: JOB DESCRIPTION ===
{jd_excerpt}

=== SOURCE 3: GITHUB PRESENCE ===
{github_data}

=== SOURCE 4: CAREERS PAGE ===
{careers_data}

Return a comprehensive intelligence report as JSON:
{{
  "company_overview": {{
    "name": "Official company name",
    "industry": "Primary industry/sector",
    "sub_industry": "Specific niche (e.g., 'EdTech', 'FinTech', 'DevTools')",
    "size": "Startup (<50) / Scale-up (50-500) / Enterprise (500-5000) / Corporation (5000+)",
    "stage": "Pre-seed / Seed / Series A-C / Growth / Public / Bootstrapped",
    "founded": "Year or 'Unknown'",
    "headquarters": "City, Country",
    "offices": ["Other office locations if mentioned"],
    "website": "URL",
    "description": "2-3 sentence company description based on facts"
  }},
  "culture_and_values": {{
    "core_values": ["Stated or clearly inferred values"],
    "mission_statement": "Company mission or purpose statement",
    "work_style": "Remote / Hybrid / In-office / Flexible",
    "work_environment": "Description of day-to-day work culture",
    "team_structure": "How teams are organized (squads, pods, departments, etc.)",
    "diversity_and_inclusion": "Any DEI initiatives or statements",
    "employee_benefits": ["Benefits mentioned in JD or careers page"],
    "red_flags": ["Any potential concerns (high turnover language, unrealistic expectations, etc.)"]
  }},
  "tech_and_engineering": {{
    "tech_stack": ["All technologies mentioned or inferred"],
    "programming_languages": ["Specific languages"],
    "frameworks": ["Specific frameworks"],
    "infrastructure": ["Cloud, CI/CD, monitoring tools"],
    "methodologies": ["Agile, Scrum, Kanban, DevOps, etc."],
    "engineering_culture": "How they approach engineering (move fast, quality-first, etc.)",
    "open_source": "Any open-source involvement or contributions",
    "github_stats": {{
      "public_repos": 0,
      "top_languages": ["Languages from GitHub repos"],
      "notable_repos": ["Popular or interesting repositories"],
      "activity_level": "Active / Moderate / Low / None"
    }}
  }},
  "products_and_services": {{
    "main_products": ["Primary products or services"],
    "target_market": "Who they sell to (B2B, B2C, Enterprise, SMB, Developer)",
    "pricing_model": "Freemium / Subscription / Enterprise / Usage-based / Unknown",
    "key_features": ["Notable product features or capabilities"],
    "recent_launches": ["Recent product launches or major updates"]
  }},
  "market_position": {{
    "competitors": ["Direct competitors"],
    "differentiators": ["What sets them apart"],
    "market_trends": ["Relevant industry trends"],
    "challenges": ["Industry or company-specific challenges"],
    "growth_trajectory": "Growing rapidly / Steady growth / Mature / Declining / Unknown"
  }},
  "recent_developments": {{
    "news_highlights": ["Recent funding, acquisitions, partnerships, launches"],
    "growth_signals": ["Hiring surge, new offices, product expansion"],
    "leadership": ["Key leaders mentioned (CEO, CTO, VP Eng, etc.)"],
    "awards_recognition": ["Awards, rankings, press mentions"]
  }},
  "hiring_intelligence": {{
    "hiring_volume": "Aggressive / Moderate / Selective / Unknown",
    "interview_process": ["Known or inferred interview stages"],
    "interview_style": "Technical / Behavioral / Case study / Take-home / Unknown",
    "team_hiring_for": "Which team this role belongs to",
    "seniority_signals": "What level they actually want (may differ from title)",
    "salary_range": "Any mentioned salary/compensation info",
    "must_have_skills": ["Non-negotiable requirements from JD"],
    "nice_to_have_skills": ["Preferred but not required"],
    "hidden_requirements": ["Unstated requirements inferred from context"]
  }},
  "application_strategy": {{
    "tone": "What tone to use in application (formal, conversational, technical, passionate)",
    "keywords_to_use": ["Exact terms from their ecosystem to include"],
    "values_to_emphasize": ["Personal values that align with company"],
    "things_to_mention": ["Specific facts to reference in cover letter"],
    "things_to_avoid": ["Topics, styles, or claims that won't resonate"],
    "differentiator_opportunities": ["How to stand out from other candidates"],
    "cover_letter_hooks": ["Opening line ideas based on company intel"],
    "interview_prep_topics": ["Likely discussion topics for interview"],
    "questions_to_ask": ["Smart questions to ask the interviewer, based on intel"]
  }},
  "confidence": "high|medium|low",
  "data_completeness": {{
    "website_data": true,
    "jd_analysis": true,
    "github_data": false,
    "careers_page": false
  }},
  "data_sources": ["List of actual data sources used"]
}}"""


INTEL_FROM_JD_PROMPT = """The company website was not accessible. Analyze the job description thoroughly
to extract ALL possible company intelligence.

COMPANY NAME: {company}
JOB TITLE: {job_title}

FULL JOB DESCRIPTION:
{jd_text}

Extract every clue: culture signals, tech stack, team size, growth stage, values, work style,
interview hints, salary signals, hidden requirements, red flags.

Return the same comprehensive JSON format, but mark confidence appropriately.
Fields you cannot determine should be "Unknown" or empty arrays."""


class CompanyIntelChain:
    """Multi-source intelligence gathering for target companies."""

    def __init__(self, ai_client):
        self.ai_client = ai_client
        self._event_callback: Optional[IntelEventCallback] = None

    async def gather_intel(
        self,
        company: str,
        job_title: str,
        jd_text: str,
        company_url: Optional[str] = None,
        on_event: Optional[IntelEventCallback] = None,
    ) -> Dict[str, Any]:
        """Gather comprehensive multi-source company intelligence."""
        data_sources = []
        self._event_callback = on_event

        try:
            await self._emit_event(
                status="running",
                message=f"Starting Recon for {company or 'target company'}.",
                source="recon",
            )

            # Run all data gathering in parallel
            web_task = self._gather_website_data(company, company_url)
            github_task = self._gather_github_data(company)
            careers_task = self._gather_careers_data(company, company_url)
            jd_signals = self._extract_jd_signals(jd_text)

            if jd_signals:
                await self._emit_event(
                    status="completed",
                    message="Extracted company and role signals from the job description.",
                    source="job_description",
                    metadata={"signals": jd_signals},
                )

            web_data, github_data, careers_data = await asyncio.gather(
                web_task, github_task, careers_task,
                return_exceptions=True,
            )

            # Handle exceptions
            if isinstance(web_data, Exception):
                web_data = ""
            if isinstance(github_data, Exception):
                github_data = ""
            if isinstance(careers_data, Exception):
                careers_data = ""

            if web_data:
                data_sources.append("Company website")
            if github_data:
                data_sources.append("GitHub organization")
            if careers_data:
                data_sources.append("Careers page")
            if jd_signals:
                data_sources.append("Job description analysis")

            await self._emit_event(
                status="running",
                message="Synthesizing findings into a company intelligence report.",
                source="analysis",
            )

            # Build the prompt with all available data
            if web_data or github_data or careers_data:
                prompt = INTEL_PROMPT.format(
                    company=company,
                    job_title=job_title,
                    web_data=web_data[:5000] if web_data else "Not available",
                    jd_excerpt=jd_text[:3000],
                    github_data=github_data[:2000] if github_data else "Not available",
                    careers_data=careers_data[:2000] if careers_data else "Not available",
                )
            else:
                prompt = INTEL_FROM_JD_PROMPT.format(
                    company=company,
                    job_title=job_title,
                    jd_text=jd_text[:5000],
                )

            try:
                result = await self.ai_client.complete_json(
                    prompt=prompt,
                    system=INTEL_SYSTEM,
                    max_tokens=4000,
                    temperature=0.2,
                    task_type="reasoning",
                )
            except Exception as e:
                logger.warning("company_intel_ai_failed", error=str(e)[:200])
                await self._emit_event(
                    status="warning",
                    message="Intel synthesis fell back to JD-only inference after the model call failed.",
                    source="analysis",
                    metadata={"error": str(e)[:200]},
                )
                result = self._fallback_intel(company, jd_text)

            # Enrich with metadata
            result["data_sources"] = data_sources or ["Job description inference only"]
            result.setdefault("company_overview", {"name": company})
            result.setdefault("culture_and_values", {})
            result.setdefault("tech_and_engineering", {})
            result.setdefault("products_and_services", {})
            result.setdefault("market_position", {})
            result.setdefault("recent_developments", {})
            result.setdefault("hiring_intelligence", {})
            result.setdefault("application_strategy", {})

            # Set confidence based on data completeness
            has_web = bool(web_data)
            has_github = bool(github_data)
            has_careers = bool(careers_data)
            source_count = sum([has_web, has_github, has_careers, bool(jd_signals)])

            if source_count >= 3:
                result["confidence"] = "high"
            elif source_count >= 2:
                result["confidence"] = "medium"
            else:
                result["confidence"] = "low"

            result["data_completeness"] = {
                "website_data": has_web,
                "jd_analysis": True,
                "github_data": has_github,
                "careers_page": has_careers,
            }

            await self._emit_event(
                status="completed",
                message=f"Recon complete with {len(result['data_sources'])} usable signal source(s).",
                source="recon",
                metadata={
                    "confidence": result["confidence"],
                    "data_sources": result["data_sources"],
                },
            )

            return result
        finally:
            self._event_callback = None

    # ── Website Data ──────────────────────────────────────────────

    async def _gather_website_data(self, company: str, company_url: Optional[str]) -> str:
        """Fetch company homepage and about page."""
        urls_to_try = []

        if company_url:
            urls_to_try.append(company_url)

        for candidate in self._guess_company_url(company):
            if candidate not in urls_to_try:
                urls_to_try.append(candidate)

        for url in urls_to_try:
            await self._emit_event(
                status="running",
                message=f"Checking company website: {url}",
                source="website",
                url=url,
            )
            homepage = await self._fetch_page(url)
            if not homepage:
                await self._emit_event(
                    status="warning",
                    message=f"No readable content found at {url}.",
                    source="website",
                    url=url,
                )
                continue

            # Also try to fetch /about page
            about_data = ""
            base = url.rstrip("/")
            for about_path in ["/about", "/about-us", "/company"]:
                about_url = base + about_path
                await self._emit_event(
                    status="running",
                    message=f"Checking company about page: {about_url}",
                    source="website",
                    url=about_url,
                )
                about_data = await self._fetch_page(about_url)
                if about_data:
                    await self._emit_event(
                        status="completed",
                        message=f"Found about/company content at {about_url}.",
                        source="website",
                        url=about_url,
                    )
                    break

            combined = homepage
            if about_data:
                combined += "\n\n=== ABOUT PAGE ===\n" + about_data

            await self._emit_event(
                status="completed",
                message=f"Company website content captured from {url}.",
                source="website",
                url=url,
            )

            return combined

        await self._emit_event(
            status="warning",
            message="No usable company website content was found.",
            source="website",
        )

        return ""

    # ── GitHub Data ───────────────────────────────────────────────

    async def _gather_github_data(self, company: str) -> str:
        """Fetch public GitHub org data."""
        org_name = self._guess_github_org(company)
        if not org_name:
            await self._emit_event(
                status="warning",
                message="Could not infer a GitHub organization name from the company name.",
                source="github",
            )
            return ""

        try:
            await self._emit_event(
                status="running",
                message=f"Checking GitHub organization: {org_name}",
                source="github",
                url=f"https://github.com/{org_name}",
            )
            async with httpx.AsyncClient(timeout=8) as client:
                # Fetch org info
                resp = await client.get(
                    f"https://api.github.com/orgs/{org_name}",
                    headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "HireStack-AI/1.0"},
                )
                remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
                if resp.status_code == 403 or remaining == 0:
                    await self._emit_event(
                        status="warning",
                        message=f"GitHub API rate limit exhausted — skipping GitHub intel for {org_name}.",
                        source="github",
                        url=f"https://github.com/{org_name}",
                    )
                    return ""
                if resp.status_code != 200:
                    await self._emit_event(
                        status="warning",
                        message=f"GitHub organization lookup returned {resp.status_code} for {org_name}.",
                        source="github",
                        url=f"https://github.com/{org_name}",
                    )
                    return ""

                org = resp.json()
                info_parts = [
                    f"GitHub Organization: {org.get('name', org_name)}",
                    f"Description: {org.get('description', 'N/A')}",
                    f"Public repos: {org.get('public_repos', 0)}",
                    f"Blog: {org.get('blog', 'N/A')}",
                    f"Location: {org.get('location', 'N/A')}",
                ]

                # Fetch top repos
                repos_resp = await client.get(
                    f"https://api.github.com/orgs/{org_name}/repos?sort=stars&per_page=10",
                    headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "HireStack-AI/1.0"},
                )
                if repos_resp.status_code == 200:
                    repos = repos_resp.json()
                    if repos:
                        info_parts.append("\nTop repositories:")
                        languages = set()
                        for r in repos[:10]:
                            stars = r.get("stargazers_count", 0)
                            lang = r.get("language", "")
                            desc = r.get("description", "")[:80]
                            info_parts.append(f"  - {r['name']}: {desc} ({lang}, {stars} stars)")
                            if lang:
                                languages.add(lang)
                        if languages:
                            info_parts.append(f"\nLanguages used: {', '.join(sorted(languages))}")

                await self._emit_event(
                    status="completed",
                    message=f"GitHub intel collected for {org_name}.",
                    source="github",
                    url=f"https://github.com/{org_name}",
                    metadata={"public_repos": org.get("public_repos", 0)},
                )

                return "\n".join(info_parts)

        except Exception as e:
            logger.info("github_intel_failed", org=org_name, error=str(e)[:100])
            await self._emit_event(
                status="warning",
                message=f"GitHub lookup failed for {org_name}.",
                source="github",
                url=f"https://github.com/{org_name}",
                metadata={"error": str(e)[:100]},
            )
            return ""

    # ── Careers Page ──────────────────────────────────────────────

    async def _gather_careers_data(self, company: str, company_url: Optional[str]) -> str:
        """Fetch company careers/jobs page for additional intel."""
        urls_to_try = []

        if company_url:
            base = company_url.rstrip("/")
            urls_to_try.extend([
                base + "/careers",
                base + "/jobs",
                base + "/careers/",
                base + "/join-us",
                base + "/work-with-us",
            ])

        guessed_candidates = self._guess_company_url(company)
        for guessed in guessed_candidates:
            base = guessed.rstrip("/")
            urls_to_try.extend([base + "/careers", base + "/jobs"])

        for url in urls_to_try:
            await self._emit_event(
                status="running",
                message=f"Checking careers page: {url}",
                source="careers",
                url=url,
            )
            data = await self._fetch_page(url)
            if data and len(data) > 100:
                await self._emit_event(
                    status="completed",
                    message=f"Careers content found at {url}.",
                    source="careers",
                    url=url,
                )
                return data

        await self._emit_event(
            status="warning",
            message="No usable careers page content was found.",
            source="careers",
        )

        return ""

    # ── Utilities ─────────────────────────────────────────────────

    async def _emit_event(
        self,
        *,
        status: str,
        message: str,
        source: str,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._event_callback:
            return

        payload: Dict[str, Any] = {
            "stage": "recon",
            "status": status,
            "message": message,
            "source": source,
        }
        if url:
            payload["url"] = url
        if metadata:
            payload["metadata"] = metadata

        try:
            maybe = self._event_callback(payload)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as e:
            logger.debug("company_intel_event_emit_failed", error=str(e)[:100])

    async def _fetch_page(self, url: str) -> str:
        """Fetch and extract text from a web page."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; HireStack-AI/1.0; Career Intelligence)",
                    "Accept": "text/html",
                })
                if resp.status_code != 200:
                    return ""
                html = resp.text[:25000]
        except Exception as e:
            logger.debug("page_fetch_failed", url=url, error=str(e)[:80])
            return ""

        return self._extract_text_from_html(html)

    def _extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML."""
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        meta_match = re.search(
            r'<meta\s+(?:name|property)=["\'](?:description|og:description)["\']\s+content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        if not meta_match:
            meta_match = re.search(
                r'<meta\s+content=["\']([^"\']*)["\']\s+(?:name|property)=["\'](?:description|og:description)["\']',
                html, re.IGNORECASE,
            )
        description = meta_match.group(1).strip() if meta_match else ""

        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        return f"Title: {title}\nDescription: {description}\nContent: {text[:6000]}"

    def _guess_company_url(self, company: str) -> list:
        """Guess company website URL candidates across common TLDs."""
        clean = re.sub(r"\s*(Inc|Ltd|LLC|Corp|Limited|PLC|GmbH|SA|AG|Co)\.?\s*$", "", company, flags=re.IGNORECASE)
        clean = re.sub(r"[^a-zA-Z0-9]", "", clean).lower()
        if len(clean) < 2:
            return []
        # Ordered by prevalence: .com first, then tech-heavy TLDs
        return [
            f"https://www.{clean}.com",
            f"https://{clean}.io",
            f"https://{clean}.ai",
            f"https://{clean}.co",
        ]

    def _guess_github_org(self, company: str) -> Optional[str]:
        """Guess GitHub organization name."""
        clean = re.sub(r"\s*(Inc|Ltd|LLC|Corp|Limited|PLC|GmbH|SA|AG|Co)\.?\s*$", "", company, flags=re.IGNORECASE)
        clean = re.sub(r"[^a-zA-Z0-9\s-]", "", clean).strip()
        # Try common patterns
        candidates = [
            clean.replace(" ", "").lower(),
            clean.replace(" ", "-").lower(),
        ]
        return candidates[0] if candidates else None

    def _extract_jd_signals(self, jd_text: str) -> str:
        """Extract structured signals from JD text."""
        signals = []
        lower = jd_text.lower()

        tech_keywords = [
            "react", "angular", "vue", "svelte", "next.js", "nuxt",
            "python", "javascript", "typescript", "java", "go", "rust", "c#", "ruby", "php", "scala", "kotlin",
            "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
            "postgresql", "mongodb", "redis", "elasticsearch", "kafka",
            "graphql", "rest", "grpc", "microservices",
            "ci/cd", "jenkins", "github actions", "circleci",
            "machine learning", "ai", "deep learning", "nlp", "llm",
        ]
        found_tech = [t for t in tech_keywords if t in lower]
        if found_tech:
            signals.append(f"Tech: {', '.join(found_tech)}")

        if "remote" in lower:
            signals.append("Remote work")
        if "hybrid" in lower:
            signals.append("Hybrid model")
        if "on-site" in lower or "onsite" in lower:
            signals.append("On-site required")
        if "agile" in lower or "scrum" in lower:
            signals.append("Agile/Scrum")
        if "startup" in lower:
            signals.append("Startup environment")
        if "series" in lower:
            signals.append("VC-backed")
        if "diversity" in lower or "inclusion" in lower:
            signals.append("DEI focus")
        if "equity" in lower or "stock" in lower:
            signals.append("Equity compensation")
        if any(w in lower for w in ["unlimited pto", "unlimited vacation", "flexible time"]):
            signals.append("Flexible time off")

        # Salary signals
        salary_match = re.search(r'[\$£€]\s*(\d{2,3})[,.]?\d{0,3}\s*[-–to]+\s*[\$£€]?\s*(\d{2,3})[,.]?\d{0,3}', jd_text)
        if salary_match:
            signals.append(f"Salary range: {salary_match.group(0)}")

        return "; ".join(signals)

    def _fallback_intel(self, company: str, jd_text: str) -> Dict[str, Any]:
        """Minimal intel when AI fails."""
        signals = self._extract_jd_signals(jd_text)
        return {
            "company_overview": {"name": company, "description": f"Intelligence limited. JD signals: {signals}"},
            "culture_and_values": {"core_values": [], "work_style": "Unknown"},
            "tech_and_engineering": {"tech_stack": [], "github_stats": {"activity_level": "Unknown"}},
            "products_and_services": {"main_products": []},
            "hiring_intelligence": {"must_have_skills": [], "nice_to_have_skills": []},
            "application_strategy": {
                "keywords_to_use": [],
                "values_to_emphasize": ["adaptability", "initiative"],
                "things_to_mention": [f"Your genuine interest in {company}"],
                "cover_letter_hooks": [],
                "questions_to_ask": [],
            },
            "confidence": "low",
        }
