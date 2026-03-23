"""
Company Intelligence Chain
Gathers and analyzes intelligence about a target company to improve application quality.
Uses web scraping + AI analysis to build a comprehensive company profile.
"""
import re
from typing import Dict, Any, Optional, List
import httpx
import structlog

logger = structlog.get_logger()


INTEL_SYSTEM = """You are an elite corporate intelligence analyst. Given raw web data about a company,
you extract and synthesize actionable intelligence for job applicants.

Your analysis helps candidates:
1. Tailor their CV/cover letter to the company's exact culture and values
2. Reference specific company initiatives, products, and achievements
3. Align their experience with the company's tech stack and methodology
4. Prepare for interviews with insider-level knowledge
5. Demonstrate genuine knowledge that impresses hiring managers

Be specific — cite real products, real values, real initiatives. Never fabricate company details.
If information is limited, say so and provide what you can infer from the available data.
Return ONLY valid JSON."""

INTEL_PROMPT = """Analyze this company for a job applicant targeting the role: {job_title}

COMPANY NAME: {company}
COMPANY WEBSITE DATA (extracted):
{web_data}

JOB DESCRIPTION EXCERPT:
{jd_excerpt}

Return a comprehensive intelligence report as JSON:
{{
  "company_overview": {{
    "name": "Official company name",
    "industry": "Primary industry",
    "size": "Startup/SMB/Enterprise/Corporation",
    "founded": "Year or 'Unknown'",
    "headquarters": "Location",
    "description": "2-3 sentence company description"
  }},
  "culture_and_values": {{
    "core_values": ["List of stated or inferred values"],
    "work_culture": "Description of work environment (remote, hybrid, in-office, etc.)",
    "mission_statement": "Company mission or purpose",
    "employee_sentiment": "What employees likely value here"
  }},
  "tech_and_tools": {{
    "tech_stack": ["Technologies they use or mention"],
    "methodologies": ["Agile, Scrum, DevOps, etc."],
    "products": ["Key products or services"]
  }},
  "recent_news": {{
    "highlights": ["Recent achievements, launches, funding rounds, or news"],
    "growth_signals": ["Signs of growth or change"]
  }},
  "application_strategy": {{
    "keywords_to_use": ["Specific terms from their culture/tech to include in your application"],
    "values_to_emphasize": ["Which of YOUR values align with theirs"],
    "things_to_mention": ["Specific company facts to reference in cover letter/interview"],
    "things_to_avoid": ["Topics or approaches that wouldn't resonate"],
    "interview_topics": ["Likely discussion points based on company focus"]
  }},
  "competitive_position": {{
    "competitors": ["Key competitors"],
    "differentiators": ["What makes this company unique"],
    "challenges": ["Industry challenges they face"]
  }},
  "confidence": "high|medium|low",
  "data_sources": ["Where the intelligence came from"]
}}"""


INTEL_FROM_JD_PROMPT = """The company website was not accessible. Analyze the job description to extract
all possible company intelligence for an applicant.

COMPANY NAME: {company}
JOB TITLE: {job_title}

FULL JOB DESCRIPTION:
{jd_text}

Extract every clue about the company from the JD: culture signals, tech stack, team size,
growth stage, values, work style, etc. Return the same JSON format as a full intel report,
but mark confidence as "low" since it's inferred from JD only."""


class CompanyIntelChain:
    """Gathers intelligence about a target company for application improvement."""

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def gather_intel(
        self,
        company: str,
        job_title: str,
        jd_text: str,
        company_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Gather comprehensive company intelligence."""
        web_data = ""
        data_sources = []

        # Step 1: Try to fetch company website
        if company_url:
            web_data = await self._fetch_website(company_url)
            if web_data:
                data_sources.append(f"Website: {company_url}")

        # Step 2: If no URL provided, try to guess it
        if not web_data and company:
            guessed_url = self._guess_company_url(company)
            if guessed_url:
                web_data = await self._fetch_website(guessed_url)
                if web_data:
                    data_sources.append(f"Website: {guessed_url}")

        # Step 3: Extract intel from JD text (always — even if we have web data)
        jd_signals = self._extract_jd_signals(jd_text)
        if jd_signals:
            data_sources.append("Job description analysis")

        # Step 4: AI analysis
        if web_data:
            # Full analysis with web data
            prompt = INTEL_PROMPT.format(
                company=company,
                job_title=job_title,
                web_data=web_data[:6000],
                jd_excerpt=jd_text[:2000],
            )
        else:
            # JD-only analysis
            prompt = INTEL_FROM_JD_PROMPT.format(
                company=company,
                job_title=job_title,
                jd_text=jd_text[:5000],
            )

        try:
            result = await self.ai_client.complete_json(
                prompt=prompt,
                system=INTEL_SYSTEM,
                max_tokens=3000,
                temperature=0.3,
                task_type="reasoning",
            )
        except Exception as e:
            logger.warning("company_intel_ai_failed", error=str(e)[:200])
            result = self._fallback_intel(company, jd_text)

        # Enrich with data sources
        result["data_sources"] = data_sources or ["Job description inference"]
        result.setdefault("company_overview", {"name": company})
        result.setdefault("culture_and_values", {})
        result.setdefault("tech_and_tools", {})
        result.setdefault("application_strategy", {})
        result.setdefault("confidence", "low" if not web_data else "medium")

        return result

    async def _fetch_website(self, url: str) -> str:
        """Fetch and extract text from a company website."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "HireStack-AI/1.0 (Career Intelligence Bot)",
                    "Accept": "text/html",
                })
                if resp.status_code != 200:
                    return ""
                html = resp.text[:20000]
        except Exception as e:
            logger.info("company_website_fetch_failed", url=url, error=str(e)[:100])
            return ""

        # Extract useful text from HTML
        text = self._extract_text_from_html(html)
        return text[:8000] if text else ""

    def _extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML, focusing on about/values/culture content."""
        # Remove script/style tags
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Extract meta description
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

        # Strip all HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return f"Title: {title}\nDescription: {description}\nContent: {text[:6000]}"

    def _guess_company_url(self, company: str) -> Optional[str]:
        """Guess the company's website URL from the name."""
        # Clean company name
        clean = re.sub(r"\s*(Inc|Ltd|LLC|Corp|Limited|PLC|GmbH|SA|AG)\.?\s*$", "", company, flags=re.IGNORECASE)
        clean = re.sub(r"[^a-zA-Z0-9]", "", clean).lower()
        if len(clean) < 2:
            return None
        return f"https://www.{clean}.com"

    def _extract_jd_signals(self, jd_text: str) -> str:
        """Extract company culture signals from the JD text."""
        signals = []
        lower = jd_text.lower()

        # Tech stack signals
        tech_keywords = ["react", "python", "aws", "docker", "kubernetes", "typescript",
                         "node", "java", "go", "rust", "terraform", "jenkins", "ci/cd"]
        found_tech = [t for t in tech_keywords if t in lower]
        if found_tech:
            signals.append(f"Tech stack mentions: {', '.join(found_tech)}")

        # Culture signals
        if "remote" in lower:
            signals.append("Remote work mentioned")
        if "hybrid" in lower:
            signals.append("Hybrid work model")
        if "agile" in lower or "scrum" in lower:
            signals.append("Agile/Scrum methodology")
        if "startup" in lower:
            signals.append("Startup environment")
        if "diversity" in lower or "inclusion" in lower:
            signals.append("DEI focus")

        return "; ".join(signals)

    def _fallback_intel(self, company: str, jd_text: str) -> Dict[str, Any]:
        """Return minimal intel when AI fails."""
        return {
            "company_overview": {"name": company, "description": "Intelligence gathering limited"},
            "culture_and_values": {"core_values": [], "work_culture": "Unknown"},
            "tech_and_tools": {"tech_stack": [], "products": []},
            "application_strategy": {
                "keywords_to_use": [],
                "values_to_emphasize": ["adaptability", "initiative"],
                "things_to_mention": [f"Your interest in {company}"],
            },
            "confidence": "low",
        }
