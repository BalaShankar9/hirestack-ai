"""
Document Generator Chain
Creates personalized application documents based on user profile and target job
"""
from typing import Dict, Any, List, Optional

import structlog

from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.chains.document_generator")


DOCUMENT_SYSTEM = """You are an expert resume writer, cover letter specialist, and professional document creator.

Your expertise includes:
- ATS-optimized resume writing
- Compelling cover letter composition
- Portfolio presentation
- Case study development
- Professional communication

Create documents that are:
- Tailored to the specific job and company
- Achievement-focused with quantified results
- Professionally formatted
- Keyword-optimized for ATS systems
- Authentic to the candidate's experience

Never fabricate experience or achievements. Enhance presentation of real accomplishments."""


# ── Strategic Tailored CV Prompt ──────────────────────────────────────

TAILORED_CV_SYSTEM = """You are an elite career strategist, professional CV writer, and talent positioning expert with 20+ years of experience placing candidates in top roles.

YOUR MISSION: Create a TAILORED CV that positions the candidate as the strongest possible match for the target role. This is about STRATEGIC POSITIONING — presenting the candidate's REAL background in the most compelling, relevant way possible.

YOUR APPROACH:
1. **Foundation**: Use ALL of the candidate's real experience as the base — never invent or fabricate roles, companies, or achievements
2. **Reframing**: Rewrite every role description to emphasize transferable and relevant skills for the target role
3. **Strategic Highlighting**: Surface hidden relevance in existing experience:
   - Identify transferable skills the candidate may not have thought to highlight
   - Reframe job duties using industry-standard terminology matching the target role
   - Emphasize projects, accomplishments, and responsibilities most relevant to the JD
   - Quantify achievements wherever data supports it (team sizes, budgets, timelines, percentages)
4. **Skills Mapping**: Bridge the language gap between the candidate's experience and the target job's requirements
   - Map the candidate's existing skills to the JD's language
   - Highlight coursework, certifications, side projects, and self-study that demonstrate relevant abilities
5. **Keyword Optimization**: Naturally weave ALL job description keywords into the CV where the candidate has genuine supporting experience

AUTHENTICITY RULES:
- NEVER fabricate companies, roles, projects, or achievements the candidate did not have
- NEVER invent metrics or statistics — only quantify where the candidate's real experience supports it
- Every claim must be rooted in the candidate's actual background
- Job titles must match what the candidate actually held (you may note equivalent titles in parentheses)
- Dates must match the candidate's real timeline — do not fill employment gaps with fictional roles
- If there are genuine gaps, focus on strengthening the presentation of what IS there
- The CV must be 100% defensible in an interview

FORMAT: Return the CV as clean, professional HTML (NOT markdown). Use semantic HTML:
- <h1> for the candidate's name
- <h2> for section headers (Professional Summary, Core Skills, Professional Experience, Education, etc.)
- <h3> for company/role headers
- <p> for descriptions
- <ul><li> for achievement bullet points
- <strong> for emphasis on key metrics and skills
- <em> for dates and locations

The CV MUST be ATS-friendly: clean semantic HTML, no tables, no complex CSS, no images.
Aim for 2-3 pages of content. Be detailed and thorough."""


TAILORED_CV_PROMPT = """Create a strategically tailored CV for this candidate targeting this specific role.

═══════════════════════════════════════
TARGET ROLE: {job_title} at {company}
═══════════════════════════════════════

JOB DESCRIPTION:
{jd_text}

═══════════════════════════════════════
CANDIDATE'S CURRENT PROFILE (parsed):
═══════════════════════════════════════
{user_profile}

═══════════════════════════════════════
ORIGINAL RESUME TEXT:
═══════════════════════════════════════
{resume_text}

═══════════════════════════════════════
GAP ANALYSIS:
═══════════════════════════════════════
Compatibility Score: {compatibility}%
Key Gaps: {key_gaps}
Strengths: {strengths}
{company_intel_section}
═══════════════════════════════════════

Now create a TAILORED CV that:
1. Positions this candidate as the strongest possible match for the role
2. Uses their real experience as the foundation
3. Strategically reframes and highlights skills to close the identified gaps
4. Naturally incorporates ALL key job description keywords where supported by real experience
5. Includes quantified achievements backed by real accomplishments
6. Feels 100% authentic, professional, and interview-defensible
7. Is structured for maximum ATS compatibility
8. Where company intelligence is provided above, subtly reflect the company's values, culture, and language throughout

Return ONLY the HTML CV content. No explanations, no markdown fences, just clean HTML starting with <h1>."""


# ── Strategic Tailored Cover Letter Prompt ────────────────────────────

TAILORED_CL_SYSTEM = """You are an elite career strategist and compelling storyteller who writes cover letters that consistently land interviews.

YOUR APPROACH:
1. Open with a specific, attention-grabbing hook — NEVER "I am writing to apply for..."
2. Show genuine understanding of the company and what they're trying to achieve
3. Connect the candidate's (enhanced) experience directly to the role's key requirements
4. Tell a compelling narrative that makes the candidate's career trajectory feel purposeful and natural
5. Include 2-3 specific achievements with metrics that demonstrate direct relevance
6. Close with confidence and a clear call to action

STYLE:
- Conversational yet professional
- Specific, not generic
- Confident without being arrogant
- Shows personality and genuine enthusiasm
- 3-4 paragraphs, 300-400 words

FORMAT: Return as clean HTML using <p>, <strong>, <em>, <br/> tags.
Start directly with the salutation (Dear...). No <h1> headers needed."""


TAILORED_CL_PROMPT = """Write a compelling, strategically crafted cover letter.

TARGET: {job_title} at {company}

JOB REQUIREMENTS:
{jd_text}

CANDIDATE PROFILE:
{user_profile}
{company_intel_section}
CANDIDATE STRENGTHS: {strengths}

KEY GAPS BEING ADDRESSED: {key_gaps}

Write a cover letter that:
1. Opens with a compelling, specific hook related to the company or industry (use the company intelligence above)
2. Demonstrates GENUINE, SPECIFIC knowledge of the company — name their mission, culture, or values from the intel above
3. Connects the candidate's experience to EVERY key requirement
4. Includes 2-3 specific achievement metrics
5. Addresses the candidate's career narrative naturally
6. Closes with a confident call to action

Return ONLY the HTML content starting with <p>Dear. No markdown, no explanations."""


# ── Strategic Tailored Personal Statement Prompt ──────────────────────

TAILORED_PS_SYSTEM = """You are an elite admissions consultant and professional storyteller with 20+ years of experience crafting personal statements that secure positions at top-tier companies.

YOUR MISSION: Create a deeply compelling personal statement that makes the hiring manager feel they MUST meet this candidate. This is about authentic narrative — weaving the candidate's journey into a story that naturally demonstrates why they are perfect for this role.

YOUR APPROACH:
1. **Hook**: Open with a vivid, specific moment or insight that immediately captures attention
2. **Journey**: Tell the candidate's professional story as a purposeful narrative arc
3. **Motivation**: Show genuine, specific passion for this company and role — not generic enthusiasm
4. **Value**: Articulate unique value through concrete examples and achievements
5. **Vision**: Paint a picture of how the candidate will contribute and grow

STYLE:
- First person, authentic voice
- Specific, never generic — every sentence should only work for THIS candidate at THIS company
- Confident but humble — let achievements speak
- Emotionally intelligent — shows self-awareness and growth
- 500-700 words, 4-5 paragraphs

AUTHENTICITY RULES:
- Never fabricate experiences — enhance the presentation of real ones
- Use real details from the candidate's background
- Show genuine understanding of the company
- Demonstrate growth mindset and learning from challenges

FORMAT: Return as clean, professional HTML.
- <p> for paragraphs
- <strong> for key emphasis points
- <em> for subtle emphasis
- No headers needed — start directly with the opening paragraph
- Each paragraph should flow naturally into the next"""


TAILORED_PS_PROMPT = """Write a compelling personal statement for this candidate targeting this specific role.

═══════════════════════════════════════
TARGET ROLE: {job_title} at {company}
═══════════════════════════════════════

JOB DESCRIPTION:
{jd_text}

═══════════════════════════════════════
CANDIDATE'S PROFILE:
═══════════════════════════════════════
{user_profile}

═══════════════════════════════════════
ORIGINAL RESUME TEXT:
═══════════════════════════════════════
{resume_text}

═══════════════════════════════════════
GAP ANALYSIS:
═══════════════════════════════════════
Compatibility Score: {compatibility}%
Strengths: {strengths}
Areas for Growth: {key_gaps}

═══════════════════════════════════════

Write a personal statement that:
1. Opens with a vivid, attention-grabbing hook specific to this candidate
2. Tells a purposeful career narrative showing growth and intentionality
3. Demonstrates specific knowledge of {company} and genuine enthusiasm
4. Connects the candidate's unique strengths directly to role requirements
5. Addresses career transitions or gaps positively as evidence of adaptability
6. Closes with a forward-looking vision of their contribution
7. Feels 100% authentic — a real person, not a template

Return ONLY the HTML content starting with <p>. No markdown, no explanations."""


# ── Strategic Tailored Portfolio / Evidence Showcase Prompt ────────────

TAILORED_PORTFOLIO_SYSTEM = """You are an elite portfolio consultant and technical writer who transforms project experiences into compelling evidence showcases that win interviews.

YOUR MISSION: Create a professional evidence portfolio document that proves the candidate's capabilities through concrete projects, achievements, and evidence. Each item should be presented as irrefutable proof of their skills.

YOUR APPROACH:
1. **Strategic Selection**: Highlight projects most relevant to the target role
2. **Impact Focus**: Lead with quantified results and business impact
3. **Technical Depth**: Show genuine technical understanding without jargon overload
4. **Narrative**: Each project tells a mini-story: problem → approach → result
5. **Proof Points**: Every claim has evidence backing it up

FORMAT: Return as clean, professional HTML document with:
- <h2> for "Evidence Portfolio" header
- <h3> for each project/evidence item title
- <div class="project-card"> wrapping each item
- <p> for descriptions
- <ul><li> for key achievements and metrics
- <strong> for emphasis on metrics, technologies, and impact
- <em> for roles and dates
- Include a brief intro paragraph explaining the portfolio's relevance to the role"""


TAILORED_PORTFOLIO_PROMPT = """Create an evidence portfolio document for this candidate targeting this role.

═══════════════════════════════════════
TARGET ROLE: {job_title} at {company}
═══════════════════════════════════════

JOB DESCRIPTION:
{jd_text}

═══════════════════════════════════════
CANDIDATE'S PROFILE:
═══════════════════════════════════════
{user_profile}

═══════════════════════════════════════
ORIGINAL RESUME TEXT:
═══════════════════════════════════════
{resume_text}

═══════════════════════════════════════
GAP ANALYSIS:
═══════════════════════════════════════
Compatibility: {compatibility}%
Strengths: {strengths}
Key Gaps: {key_gaps}

═══════════════════════════════════════

Create an evidence portfolio that:
1. Opens with a brief intro connecting the candidate's work to {company}'s needs
2. Presents 4-6 project/evidence items, prioritized by relevance to the JD
3. Each item includes: title, role, problem solved, approach, key technologies, and quantified results
4. Emphasizes transferable skills that bridge any identified gaps
5. Uses ONLY real experiences from the resume — do not fabricate projects
6. Shows a pattern of growth and increasing responsibility
7. If the candidate lacks traditional projects, highlight:
   - Work achievements at previous employers
   - Self-directed learning projects mentioned in their background
   - Open source contributions or personal projects
   - Relevant coursework or certifications

Return ONLY the HTML content starting with <h2>. No markdown fences, no explanations."""


CV_GENERATOR_PROMPT = """Create a professional, ATS-optimized CV for this candidate targeting this role:

CANDIDATE PROFILE:
{user_profile}

TARGET ROLE: {job_title} at {company}

JOB REQUIREMENTS:
{job_requirements}

GAP ANALYSIS INSIGHTS:
{gap_insights}

Create a compelling CV in markdown format that:
1. Highlights relevant experience and achievements
2. Uses keywords from the job description
3. Quantifies achievements wherever possible
4. Emphasizes strengths identified in the gap analysis
5. Addresses gaps subtly through positioning
6. Follows a clean, professional format

Structure:
- Name and Contact Info
- Professional Summary (tailored to role)
- Key Skills/Competencies
- Professional Experience (achievements, not just duties)
- Education
- Certifications (if applicable)
- Notable Projects (if applicable)

Return the CV in clean markdown format."""


COVER_LETTER_PROMPT = """Write a compelling, personalized cover letter:

CANDIDATE PROFILE:
{user_profile}

TARGET ROLE: {job_title}
TARGET COMPANY: {company}

COMPANY INFO:
{company_info}

JOB REQUIREMENTS:
{job_requirements}

CANDIDATE STRENGTHS:
{strengths}

Write a cover letter that:
1. Opens with a compelling, specific hook
2. Shows genuine knowledge of the company
3. Connects experience to role requirements
4. Addresses potential concerns proactively
5. Demonstrates cultural fit
6. Includes specific achievement examples
7. Closes with clear interest and call to action

Keep it to 3-4 paragraphs. Be personable but professional.

Return the cover letter in markdown format."""


MOTIVATION_STATEMENT_PROMPT = """Create a company-specific motivation statement:

CANDIDATE PROFILE:
{user_profile}

TARGET COMPANY: {company}

COMPANY INFO:
{company_info}

TARGET ROLE: {job_title}

Write a compelling motivation statement that demonstrates:
1. Deep research into the company
2. Understanding of company mission and values
3. Genuine enthusiasm for the specific role
4. Alignment between candidate goals and company direction
5. Specific ways the candidate can contribute
6. Long-term vision at the company

This should feel authentic and specific, not generic.

Return ONLY valid JSON:
```json
{{
  "motivation_statement": {{
    "opening": "Compelling opening paragraph",
    "company_alignment": "Why this company specifically",
    "value_proposition": "What unique value you bring",
    "immediate_contributions": ["How you can help right away"],
    "growth_vision": "Where you see yourself growing",
    "closing": "Powerful closing statement"
  }},
  "company_research": {{
    "recent_news": ["Relevant company developments"],
    "culture_fit": ["How you align with culture"],
    "mission_alignment": "Connection to company mission",
    "industry_insights": ["Your understanding of their market"]
  }}
}}
```"""


PORTFOLIO_DESCRIPTION_PROMPT = """Create professional descriptions for the candidate's projects:

CANDIDATE PROFILE:
{user_profile}

TARGET ROLE: {job_title}

EXISTING PROJECTS:
{projects}

For each project, create a compelling portfolio description that:
1. Clearly explains the problem solved
2. Highlights technical approach
3. Quantifies impact where possible
4. Connects to target role requirements

Return ONLY valid JSON:
```json
{{
  "portfolio_items": [
    {{
      "title": "Project Title",
      "tagline": "One-line description",
      "problem_statement": "What problem this solved",
      "solution_overview": "How you solved it",
      "key_features": ["Feature highlights"],
      "technical_stack": ["Technologies used"],
      "your_role": "Your specific contribution",
      "impact_metrics": ["Quantified results"],
      "lessons_learned": ["Key takeaways"],
      "presentation_tips": ["How to discuss in interviews"]
    }}
  ]
}}
```"""


class DocumentGeneratorChain:
    """Chain for generating personalized application documents."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def generate_cv(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        job_requirements: Dict[str, Any],
        gap_insights: Dict[str, Any] = None
    ) -> str:
        """Generate a tailored CV."""
        import json
        try:
            prompt = CV_GENERATOR_PROMPT.format(
                user_profile=json.dumps(user_profile, indent=2),
                job_title=job_title,
                company=company,
                job_requirements=json.dumps(job_requirements, indent=2),
                gap_insights=json.dumps(gap_insights or {}, indent=2)
            )

            return await self.ai_client.complete(
                prompt=prompt,
                system=DOCUMENT_SYSTEM,
                temperature=0.5,
                max_tokens=4000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_cv.failed", error=str(exc)[:200])
            return ""

    # Phase D.1 — variant style nudges appended to CV_GENERATOR_PROMPT.
    # Kept short and orthogonal so cost ≈ 1.4× (research/evidence shared
    # by caller, only the drafting LLM call doubles).
    CV_VARIANT_STYLES: Dict[str, Dict[str, str]] = {
        "concise": {
            "label": "Concise",
            "nudge": (
                "VARIANT STYLE: CONCISE — favour short, punchy bullets, "
                "drop filler words, keep the document under one page worth "
                "of content, lead every bullet with an action verb."
            ),
        },
        "narrative": {
            "label": "Narrative",
            "nudge": (
                "VARIANT STYLE: NARRATIVE — write in flowing prose where "
                "appropriate, expand the professional summary, frame "
                "achievements as connected stories rather than isolated "
                "bullets. Keep it scannable but human."
            ),
        },
    }

    async def generate_cv_variants(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        job_requirements: Dict[str, Any],
        gap_insights: Dict[str, Any] = None,
        variants: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate multiple CV variants in parallel.

        Returns a list of dicts: ``[{"variant": "concise", "label": "Concise",
        "content": "..."}, ...]``.  Variants with empty content (LLM
        failure) are still returned — caller decides how to surface failure.
        """
        import asyncio
        import json

        variant_keys = variants or ["concise", "narrative"]
        # Filter to known styles, preserving order
        variant_keys = [v for v in variant_keys if v in self.CV_VARIANT_STYLES]
        if not variant_keys:
            return []

        base_payload = dict(
            user_profile=json.dumps(user_profile, indent=2),
            job_title=job_title,
            company=company,
            job_requirements=json.dumps(job_requirements, indent=2),
            gap_insights=json.dumps(gap_insights or {}, indent=2),
        )

        async def _run_variant(key: str) -> Dict[str, Any]:
            style = self.CV_VARIANT_STYLES[key]
            try:
                prompt = CV_GENERATOR_PROMPT.format(**base_payload) + (
                    "\n\n" + style["nudge"]
                )
                content = await self.ai_client.complete(
                    prompt=prompt,
                    system=DOCUMENT_SYSTEM,
                    temperature=0.55 if key == "concise" else 0.7,
                    max_tokens=4000,
                    task_type="drafting",
                )
            except Exception as exc:
                logger.warning(
                    "generate_cv_variant.failed",
                    variant=key,
                    error=str(exc)[:200],
                )
                content = ""
            return {
                "variant": key,
                "label": style["label"],
                "content": content or "",
            }

        results = await asyncio.gather(
            *[_run_variant(k) for k in variant_keys],
            return_exceptions=False,
        )
        return list(results)

    async def generate_cover_letter(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        company_info: Dict[str, Any],
        job_requirements: Dict[str, Any],
        strengths: List[Dict[str, Any]] = None
    ) -> str:
        """Generate a personalized cover letter."""
        import json
        try:
            prompt = COVER_LETTER_PROMPT.format(
                user_profile=json.dumps(user_profile, indent=2),
                job_title=job_title,
                company=company,
                company_info=json.dumps(company_info or {}, indent=2),
                job_requirements=json.dumps(job_requirements, indent=2),
                strengths=json.dumps(strengths or [], indent=2)
            )

            return await self.ai_client.complete(
                prompt=prompt,
                system=DOCUMENT_SYSTEM,
                temperature=0.6,
                max_tokens=2000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_cover_letter.failed", error=str(exc)[:200])
            return ""

    async def generate_motivation_statement(
        self,
        user_profile: Dict[str, Any],
        company: str,
        company_info: Dict[str, Any],
        job_title: str
    ) -> Dict[str, Any]:
        """Generate a company-specific motivation statement."""
        import json
        try:
            prompt = MOTIVATION_STATEMENT_PROMPT.format(
                user_profile=json.dumps(user_profile, indent=2),
                company=company,
                company_info=json.dumps(company_info or {}, indent=2),
                job_title=job_title
            )

            return await self.ai_client.complete_json(
                prompt=prompt,
                system=DOCUMENT_SYSTEM,
                temperature=0.6,
                max_tokens=3000,
                task_type="reasoning",
            )
        except Exception as exc:
            logger.warning("generate_motivation_statement.failed", error=str(exc)[:200])
            return {}

    async def generate_portfolio_descriptions(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        projects: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate professional portfolio descriptions."""
        import json
        try:
            prompt = PORTFOLIO_DESCRIPTION_PROMPT.format(
                user_profile=json.dumps(user_profile, indent=2),
                job_title=job_title,
                projects=json.dumps(projects, indent=2)
            )

            return await self.ai_client.complete_json(
                prompt=prompt,
                system=DOCUMENT_SYSTEM,
                temperature=0.5,
                max_tokens=4000,
                task_type="reasoning",
            )
        except Exception as exc:
            logger.warning("generate_portfolio_descriptions.failed", error=str(exc)[:200])
            return {}

    async def generate_all_documents(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        company_info: Dict[str, Any],
        job_requirements: Dict[str, Any],
        gap_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate complete application package."""
        # Generate all documents
        cv = await self.generate_cv(
            user_profile, job_title, company,
            job_requirements, gap_analysis
        )

        cover_letter = await self.generate_cover_letter(
            user_profile, job_title, company,
            company_info, job_requirements,
            gap_analysis.get("strengths", [])
        )

        motivation = await self.generate_motivation_statement(
            user_profile, company, company_info, job_title
        )

        portfolio = await self.generate_portfolio_descriptions(
            user_profile, job_title,
            user_profile.get("projects", [])
        )

        return {
            "cv": cv,
            "cover_letter": cover_letter,
            "motivation_statement": motivation,
            "portfolio": portfolio
        }

    # ── Strategic Tailored Document Generation ────────────────────────

    async def generate_tailored_personal_statement(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
        resume_text: str = "",
    ) -> str:
        """Generate an elite personal statement in HTML."""
        import json
        try:
            compatibility = gap_analysis.get("compatibility_score", 50)
            skill_gaps = gap_analysis.get("skill_gaps", [])
            strengths = gap_analysis.get("strengths", [])
            key_gaps_str = ", ".join(
                g.get("skill", "") for g in skill_gaps[:8] if isinstance(g, dict)
            ) or "None identified"
            strengths_str = ", ".join(
                s.get("area", "") for s in strengths[:8] if isinstance(s, dict)
            ) or "Strong overall profile"

            prompt = TAILORED_PS_PROMPT.format(
                job_title=job_title,
                company=company,
                jd_text=jd_text[:3000],
                user_profile=json.dumps(user_profile, indent=2)[:3000],
                resume_text=(resume_text or "No resume text provided")[:2000],
                compatibility=compatibility,
                key_gaps=key_gaps_str,
                strengths=strengths_str,
            )

            return await self.ai_client.complete(
                prompt=prompt,
                system=TAILORED_PS_SYSTEM,
                temperature=0.65,
                max_tokens=4000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_tailored_personal_statement.failed", error=str(exc)[:200])
            return ""

    # Phase D.3 — variant style nudges for personal statement.
    PS_VARIANT_STYLES: Dict[str, Dict[str, str]] = {
        "concise": {
            "label": "Concise",
            "nudge": (
                "VARIANT STYLE: CONCISE — keep paragraphs tight, lead "
                "with the strongest 2 hooks, avoid hedging language, aim "
                "for ≤350 words. Punchy sentences win."
            ),
        },
        "narrative": {
            "label": "Narrative",
            "nudge": (
                "VARIANT STYLE: NARRATIVE — open with a personal story "
                "or pivotal moment, weave evidence into a flowing arc, "
                "let the why-this-company come through emotionally as "
                "well as logically. 450–600 words is fine."
            ),
        },
    }

    async def generate_tailored_personal_statement_variants(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
        resume_text: str = "",
        variants: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Phase D.3 — generate multiple personal-statement variants in parallel.

        Returns ``[{variant, label, content}, ...]``.  Per-variant
        try/except so one failure doesn't kill the others.
        """
        import asyncio
        import json

        variant_keys = variants or list(self.PS_VARIANT_STYLES.keys())
        variant_keys = [v for v in variant_keys if v in self.PS_VARIANT_STYLES]
        if not variant_keys:
            return []

        compatibility = gap_analysis.get("compatibility_score", 50)
        skill_gaps = gap_analysis.get("skill_gaps", [])
        strengths = gap_analysis.get("strengths", [])
        key_gaps_str = ", ".join(
            g.get("skill", "") for g in skill_gaps[:8] if isinstance(g, dict)
        ) or "None identified"
        strengths_str = ", ".join(
            s.get("area", "") for s in strengths[:8] if isinstance(s, dict)
        ) or "Strong overall profile"

        base_prompt = TAILORED_PS_PROMPT.format(
            job_title=job_title,
            company=company,
            jd_text=(jd_text or "")[:3000],
            user_profile=json.dumps(user_profile, indent=2)[:3000],
            resume_text=(resume_text or "No resume text provided")[:2000],
            compatibility=compatibility,
            key_gaps=key_gaps_str,
            strengths=strengths_str,
        )

        async def _run_variant(key: str) -> Dict[str, Any]:
            style = self.PS_VARIANT_STYLES[key]
            try:
                content = await self.ai_client.complete(
                    prompt=base_prompt + "\n\n" + style["nudge"],
                    system=TAILORED_PS_SYSTEM,
                    temperature=0.55 if key == "concise" else 0.75,
                    max_tokens=4000,
                    task_type="drafting",
                )
            except Exception as exc:
                logger.warning(
                    "generate_tailored_personal_statement_variant.failed",
                    variant=key,
                    error=str(exc)[:200],
                )
                content = ""
            return {
                "variant": key,
                "label": style["label"],
                "content": content or "",
            }

        results = await asyncio.gather(*[_run_variant(k) for k in variant_keys])
        return list(results)

    async def generate_tailored_portfolio(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
        resume_text: str = "",
    ) -> str:
        """Generate a professional evidence portfolio in HTML."""
        import json
        try:
            compatibility = gap_analysis.get("compatibility_score", 50)
            skill_gaps = gap_analysis.get("skill_gaps", [])
            strengths = gap_analysis.get("strengths", [])
            key_gaps_str = ", ".join(
                g.get("skill", "") for g in skill_gaps[:8] if isinstance(g, dict)
            ) or "None identified"
            strengths_str = ", ".join(
                s.get("area", "") for s in strengths[:8] if isinstance(s, dict)
            ) or "Strong overall profile"

            prompt = TAILORED_PORTFOLIO_PROMPT.format(
                job_title=job_title,
                company=company,
                jd_text=jd_text[:3000],
                user_profile=json.dumps(user_profile, indent=2)[:3000],
                resume_text=(resume_text or "No resume text provided")[:2000],
                compatibility=compatibility,
                key_gaps=key_gaps_str,
                strengths=strengths_str,
            )

            return await self.ai_client.complete(
                prompt=prompt,
                system=TAILORED_PORTFOLIO_SYSTEM,
                temperature=0.55,
                max_tokens=6000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_tailored_portfolio.failed", error=str(exc)[:200])
            return ""

    async def generate_tailored_cv(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
        resume_text: str = "",
        company_intel: str = "",
    ) -> str:
        """Generate a strategically tailored CV with experience enhancement."""
        import json
        try:
            # Extract context from gap analysis
            compatibility = gap_analysis.get("compatibility_score", 50)
            skill_gaps = gap_analysis.get("skill_gaps", [])
            strengths = gap_analysis.get("strengths", [])
            key_gaps_str = ", ".join(
                g.get("skill", "") for g in skill_gaps[:10] if isinstance(g, dict)
            ) or "None identified"
            strengths_str = ", ".join(
                s.get("area", "") for s in strengths[:10] if isinstance(s, dict)
            ) or "Strong overall profile"
            company_intel_section = (
                f"\n═══════════════════════════════════════\n"
                f"COMPANY INTELLIGENCE:\n"
                f"═══════════════════════════════════════\n"
                f"{company_intel}\n"
                if company_intel else ""
            )

            prompt = TAILORED_CV_PROMPT.format(
                job_title=job_title,
                company=company,
                jd_text=jd_text[:4000],  # Truncate long JDs
                user_profile=json.dumps(user_profile, indent=2)[:4000],
                resume_text=(resume_text or "No resume text provided")[:3000],
                compatibility=compatibility,
                key_gaps=key_gaps_str,
                strengths=strengths_str,
                company_intel_section=company_intel_section,
            )

            return await self.ai_client.complete(
                prompt=prompt,
                system=TAILORED_CV_SYSTEM,
                temperature=0.55,
                max_tokens=6000,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_tailored_cv.failed", error=str(exc)[:200])
            return ""

    async def generate_tailored_cv_variants(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
        resume_text: str = "",
        company_intel: str = "",
        variants: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Phase D.2 — generate multiple tailored-CV variants in parallel.

        Mirrors generate_tailored_cv but produces N stylistic variants
        from the same TAILORED_CV_PROMPT base + a short style nudge.
        Returns ``[{variant, label, content}, ...]``.  Per-variant
        try/except so one bad variant doesn't kill the others.
        """
        import asyncio
        import json

        variant_keys = variants or list(self.CV_VARIANT_STYLES.keys())
        variant_keys = [v for v in variant_keys if v in self.CV_VARIANT_STYLES]
        if not variant_keys:
            return []

        compatibility = gap_analysis.get("compatibility_score", 50)
        skill_gaps = gap_analysis.get("skill_gaps", [])
        strengths = gap_analysis.get("strengths", [])
        key_gaps_str = ", ".join(
            g.get("skill", "") for g in skill_gaps[:10] if isinstance(g, dict)
        ) or "None identified"
        strengths_str = ", ".join(
            s.get("area", "") for s in strengths[:10] if isinstance(s, dict)
        ) or "Strong overall profile"
        company_intel_section = (
            f"\n═══════════════════════════════════════\n"
            f"COMPANY INTELLIGENCE:\n"
            f"═══════════════════════════════════════\n"
            f"{company_intel}\n"
            if company_intel else ""
        )

        base_prompt = TAILORED_CV_PROMPT.format(
            job_title=job_title,
            company=company,
            jd_text=(jd_text or "")[:4000],
            user_profile=json.dumps(user_profile, indent=2)[:4000],
            resume_text=(resume_text or "No resume text provided")[:3000],
            compatibility=compatibility,
            key_gaps=key_gaps_str,
            strengths=strengths_str,
            company_intel_section=company_intel_section,
        )

        async def _run_variant(key: str) -> Dict[str, Any]:
            style = self.CV_VARIANT_STYLES[key]
            try:
                content = await self.ai_client.complete(
                    prompt=base_prompt + "\n\n" + style["nudge"],
                    system=TAILORED_CV_SYSTEM,
                    temperature=0.55 if key == "concise" else 0.7,
                    max_tokens=6000,
                    task_type="drafting",
                )
            except Exception as exc:
                logger.warning(
                    "generate_tailored_cv_variant.failed",
                    variant=key,
                    error=str(exc)[:200],
                )
                content = ""
            return {
                "variant": key,
                "label": style["label"],
                "content": content or "",
            }

        results = await asyncio.gather(*[_run_variant(k) for k in variant_keys])
        return list(results)

    async def generate_tailored_cover_letter(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
        company_intel: str = "",
    ) -> str:
        """Generate a strategically tailored cover letter."""
        import json
        try:
            skill_gaps = gap_analysis.get("skill_gaps", [])
            strengths = gap_analysis.get("strengths", [])
            key_gaps_str = ", ".join(
                g.get("skill", "") for g in skill_gaps[:6] if isinstance(g, dict)
            ) or "None identified"
            strengths_str = ", ".join(
                s.get("area", "") for s in strengths[:6] if isinstance(s, dict)
            ) or "Strong overall profile"
            company_intel_section = (
                f"\nCOMPANY INTELLIGENCE (use this to write with genuine specificity):\n"
                f"{company_intel}\n\n"
                if company_intel else ""
            )

            prompt = TAILORED_CL_PROMPT.format(
                job_title=job_title,
                company=company,
                jd_text=jd_text[:3000],
                user_profile=json.dumps(user_profile, indent=2)[:3000],
                key_gaps=key_gaps_str,
                strengths=strengths_str,
                company_intel_section=company_intel_section,
            )

            return await self.ai_client.complete(
                prompt=prompt,
                system=TAILORED_CL_SYSTEM,
                temperature=0.65,
                max_tokens=2500,
                task_type="drafting",
            )
        except Exception as exc:
            logger.warning("generate_tailored_cover_letter.failed", error=str(exc)[:200])
            return ""
