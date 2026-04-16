"""
Universal Document Generator Chain
Creates universal career documents from profile data alone — no job description targeting.
"""
from typing import Dict, Any, List
import json

import structlog

from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.chains.universal_doc_generator")


UNIVERSAL_RESUME_SYSTEM = """You are an elite professional resume writer with 20+ years of experience.

YOUR MISSION: Create a comprehensive, polished UNIVERSAL RESUME — a master resume that showcases the candidate's complete professional story. This resume is NOT tailored to any specific job; it is the candidate's definitive professional document.

FORMAT: Return clean, professional HTML (NOT markdown):
- <h1> for the candidate's name
- <div class="contact-info"> for contact details (email, phone, location, LinkedIn, GitHub)
- <h2> for section headers
- <h3> for role/company headers
- <p> for descriptions
- <ul><li> for achievement bullets
- <strong> for metrics and emphasis
- <em> for dates and locations

STRUCTURE:
1. Name + Contact Info + Professional Links
2. Professional Summary (3-4 lines capturing career essence)
3. Core Competencies (skills grid, grouped by category)
4. Professional Experience (all roles, achievement-focused, quantified)
5. Education
6. Certifications & Licenses (if any)
7. Notable Projects (if any)
8. Languages (if multilingual)

RULES:
- Include ALL experience — this is the complete picture
- Lead every bullet with a strong action verb
- Quantify achievements wherever possible
- Use clean, ATS-friendly HTML with no tables or complex CSS
- Aim for 2-3 pages of content
- Never fabricate — only present what the candidate has actually done"""


UNIVERSAL_RESUME_PROMPT = """Create a universal master resume for this candidate.

═══════════════════════════════════════
CANDIDATE PROFILE:
═══════════════════════════════════════
Name: {name}
Title: {title}
Summary: {summary}

Contact: {contact_info}
Social Links: {social_links}

SKILLS:
{skills}

EXPERIENCE:
{experience}

EDUCATION:
{education}

CERTIFICATIONS:
{certifications}

PROJECTS:
{projects}

LANGUAGES:
{languages}

ACHIEVEMENTS:
{achievements}
═══════════════════════════════════════

Create a comprehensive, beautifully structured universal resume that:
1. Presents the COMPLETE professional story
2. Highlights all achievements with quantified metrics
3. Groups skills logically by category
4. Orders experience reverse-chronologically
5. Is ATS-optimized with clean semantic HTML

Return ONLY the HTML content starting with <h1>. No markdown, no explanations."""


FULL_CV_SYSTEM = """You are an academic and professional CV specialist with expertise in comprehensive career documentation.

YOUR MISSION: Create a FULL CURRICULUM VITAE — a complete, detailed record of the candidate's entire professional and academic history. Unlike a resume, a CV has NO page limit and includes EVERYTHING.

A CV differs from a resume:
- Resume: 1-2 pages, targeted, selective
- CV: Comprehensive, no page limit, includes all experience, education, publications, presentations, awards

FORMAT: Return clean HTML:
- <h1> for name, <h2> for sections, <h3> for sub-items
- <p>, <ul><li>, <strong>, <em>
- Include ALL sections even if sparse

SECTIONS (in order):
1. Personal Information (name, contact, links)
2. Professional Summary
3. Education (all degrees, institutions, dates, GPA, thesis if applicable)
4. Professional Experience (every role, detailed descriptions)
5. Skills & Technical Competencies
6. Certifications & Professional Development
7. Projects & Portfolio
8. Publications & Presentations (if any)
9. Awards & Achievements
10. Languages
11. Professional Memberships (if any)
12. References (Available upon request)"""


FULL_CV_PROMPT = """Create a comprehensive Curriculum Vitae for this candidate.

═══════════════════════════════════════
CANDIDATE PROFILE:
═══════════════════════════════════════
Name: {name}
Title: {title}
Summary: {summary}

Contact: {contact_info}
Social Links: {social_links}

SKILLS:
{skills}

EXPERIENCE:
{experience}

EDUCATION:
{education}

CERTIFICATIONS:
{certifications}

PROJECTS:
{projects}

LANGUAGES:
{languages}

ACHIEVEMENTS:
{achievements}
═══════════════════════════════════════

Create a comprehensive CV that includes EVERY detail of this candidate's career.
Be thorough and detailed — this is their complete professional record.

Return ONLY the HTML content starting with <h1>. No markdown, no explanations."""


PERSONAL_STATEMENT_SYSTEM = """You are an expert personal branding consultant who crafts compelling career narratives.

YOUR MISSION: Write a universal PERSONAL STATEMENT — a 500-700 word narrative that captures who this person is professionally, their career journey, values, and what drives them. This is NOT targeted at any specific company; it is their authentic professional story.

APPROACH:
1. Open with a vivid hook that reveals character
2. Tell the career journey as a purposeful narrative
3. Highlight defining moments and pivotal decisions
4. Show growth, learning, and evolution
5. Articulate professional values and mission
6. Close with a forward-looking vision

STYLE: First person, authentic, specific, 4-5 paragraphs
FORMAT: Clean HTML with <p>, <strong>, <em>. Start with <p>."""


PERSONAL_STATEMENT_PROMPT = """Write a universal personal statement for this candidate.

═══════════════════════════════════════
CANDIDATE PROFILE:
═══════════════════════════════════════
Name: {name}
Title: {title}
Summary: {summary}

EXPERIENCE:
{experience}

EDUCATION:
{education}

SKILLS:
{skills}

ACHIEVEMENTS:
{achievements}
═══════════════════════════════════════

Write a compelling 500-700 word personal statement that:
1. Opens with an engaging hook specific to this person's journey
2. Tells their career story as a purposeful narrative
3. Shows growth, learning, and passion
4. Articulates their professional mission and values
5. Feels 100% authentic — a real person, not a template

Return ONLY the HTML content starting with <p>. No markdown, no explanations."""


PORTFOLIO_SYSTEM = """You are a portfolio consultant who transforms experiences into compelling showcases.

YOUR MISSION: Create a professional PORTFOLIO SHOWCASE document that presents the candidate's projects and certifications as evidence of their capabilities. Each project should be a mini case study.

FORMAT: Clean HTML:
- <h2> for "Portfolio Showcase" header
- <h3> for each project/certification title
- <div class="project-card"> wrapping each item
- <p>, <ul><li>, <strong>, <em>
- Include an introductory paragraph about the candidate"""


PORTFOLIO_PROMPT = """Create a portfolio showcase for this candidate.

═══════════════════════════════════════
CANDIDATE: {name} — {title}
═══════════════════════════════════════

PROJECTS:
{projects}

CERTIFICATIONS:
{certifications}

KEY SKILLS:
{skills}

ACHIEVEMENTS:
{achievements}
═══════════════════════════════════════

{evidence_section}

Create a portfolio showcase that:
1. Opens with a brief intro about the candidate's expertise
2. Presents each project as: Title → Problem → Approach → Technologies → Results
3. Lists certifications with issuer and credential details
4. Highlights how projects demonstrate key skills
5. Shows a pattern of growth and capability

Return ONLY the HTML content starting with <h2>. No markdown, no explanations."""


class UniversalDocGeneratorChain:
    """Chain for generating universal career documents from profile data alone."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    def _format_profile_fields(self, profile: Dict[str, Any]) -> Dict[str, str]:
        """Format profile fields for prompt insertion."""
        return {
            "name": profile.get("name") or "Not provided",
            "title": profile.get("title") or "Professional",
            "summary": profile.get("summary") or "No summary provided",
            "contact_info": json.dumps(profile.get("contact_info") or {}, indent=2),
            "social_links": json.dumps(profile.get("social_links") or {}, indent=2),
            "skills": json.dumps(profile.get("skills") or [], indent=2)[:3000],
            "experience": json.dumps(profile.get("experience") or [], indent=2)[:4000],
            "education": json.dumps(profile.get("education") or [], indent=2)[:2000],
            "certifications": json.dumps(profile.get("certifications") or [], indent=2)[:2000],
            "projects": json.dumps(profile.get("projects") or [], indent=2)[:3000],
            "languages": json.dumps(profile.get("languages") or [], indent=2)[:1000],
            "achievements": json.dumps(profile.get("achievements") or [], indent=2)[:2000],
        }

    async def generate_universal_resume(self, profile: Dict[str, Any]) -> str:
        """Generate a comprehensive universal resume from profile data."""
        try:
            fields = self._format_profile_fields(profile)
            prompt = UNIVERSAL_RESUME_PROMPT.format(**fields)
            return await self.ai_client.complete(
                prompt=prompt,
                system=UNIVERSAL_RESUME_SYSTEM,
                temperature=0.5,
                max_tokens=6000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_universal_resume.failed", error=str(exc)[:200])
            return ""

    async def generate_full_cv(self, profile: Dict[str, Any]) -> str:
        """Generate a comprehensive CV from profile data."""
        try:
            fields = self._format_profile_fields(profile)
            prompt = FULL_CV_PROMPT.format(**fields)
            return await self.ai_client.complete(
                prompt=prompt,
                system=FULL_CV_SYSTEM,
                temperature=0.5,
                max_tokens=8000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_full_cv.failed", error=str(exc)[:200])
            return ""

    async def generate_personal_statement(self, profile: Dict[str, Any]) -> str:
        """Generate a universal personal statement."""
        try:
            fields = self._format_profile_fields(profile)
            prompt = PERSONAL_STATEMENT_PROMPT.format(**fields)
            return await self.ai_client.complete(
                prompt=prompt,
                system=PERSONAL_STATEMENT_SYSTEM,
                temperature=0.65,
                max_tokens=4000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_personal_statement.failed", error=str(exc)[:200])
            return ""

    async def generate_portfolio_showcase(
        self,
        profile: Dict[str, Any],
        evidence_items: List[Dict[str, Any]] | None = None,
    ) -> str:
        """Generate a portfolio showcase from projects, certs, and evidence."""
        fields = self._format_profile_fields(profile)

        evidence_section = ""
        if evidence_items:
            evidence_section = "EVIDENCE VAULT ITEMS:\n" + json.dumps(
                [
                    {"title": e.get("title"), "type": e.get("type"), "description": e.get("description"), "skills": e.get("skills")}
                    for e in evidence_items
                ],
                indent=2,
            )[:3000]

        prompt = PORTFOLIO_PROMPT.format(**fields, evidence_section=evidence_section)
        try:
            return await self.ai_client.complete(
                prompt=prompt,
                system=PORTFOLIO_SYSTEM,
                temperature=0.55,
                max_tokens=6000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_portfolio_showcase.failed", error=str(exc)[:200])
            return ""

    async def generate_all(
        self,
        profile: Dict[str, Any],
        evidence_items: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, str]:
        """Generate all four universal documents."""
        resume = await self.generate_universal_resume(profile)
        cv = await self.generate_full_cv(profile)
        statement = await self.generate_personal_statement(profile)
        portfolio = await self.generate_portfolio_showcase(profile, evidence_items)
        return {
            "universal_resume_html": resume,
            "full_cv_html": cv,
            "personal_statement_html": statement,
            "portfolio_html": portfolio,
        }
