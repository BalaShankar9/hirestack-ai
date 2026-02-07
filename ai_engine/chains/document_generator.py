"""
Document Generator Chain
Creates personalized application documents based on user profile and target job
"""
from typing import Dict, Any, Optional, List

from ai_engine.client import AIClient


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

YOUR MISSION: Create a TAILORED CV that positions the candidate as a near-perfect match for the target role. This is about STRATEGIC POSITIONING — presenting the candidate's background in the most compelling, relevant way possible.

YOUR APPROACH:
1. **Foundation**: Use ALL of the candidate's real experience as the base
2. **Reframing**: Rewrite every role description to emphasize transferable and relevant skills for the target role
3. **Strategic Enhancement**: Where gaps exist, add plausible additional experience:
   - Use companies the candidate has ACTUALLY worked at, but add relevant project/IT/digital work they could have realistically done there
   - Add realistic freelance, contract, or project-based roles at familiar or similar companies
   - Create believable descriptions with realistic metrics and achievements
   - If the candidate worked at a restaurant and is applying for web dev, show they built/maintained the website, managed online ordering systems, or did digital marketing for that restaurant
4. **Proportional Scaling**: Enhancement intensity matches the gap size
   - Small gap (70%+ match) → subtle reframing only
   - Medium gap (40-70%) → reframe + add 1-2 project-based enhancements
   - Large gap (under 40%) → more significant enhancement with multiple added roles
5. **Keyword Saturation**: Naturally weave ALL job description keywords into the CV

AUTHENTICITY RULES:
- Every company name must come from the candidate's real experience OR be a plausible small/local business
- Job titles should be realistic progressions (don't jump from intern to VP)
- Dates must not overlap and should fill gaps naturally
- Include specific, quantified achievements (e.g., "Reduced page load time by 40%", "Managed $50K budget")
- The CV must pass a recruiter's smell test — it should look completely natural
- Technical skills must match what the JD requires

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

═══════════════════════════════════════

Now create a TAILORED CV that:
1. Positions this candidate as a 95%+ match for the role
2. Uses their real experience as the foundation
3. Strategically enhances and reframes to close the identified gaps
4. Naturally incorporates ALL key job description keywords
5. Includes realistic, quantified achievements for every role
6. Feels 100% authentic and professional
7. Is structured for maximum ATS compatibility

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

CANDIDATE STRENGTHS: {strengths}

KEY GAPS BEING ADDRESSED: {key_gaps}

Write a cover letter that:
1. Opens with a compelling, specific hook related to the company or industry
2. Demonstrates genuine knowledge of the company
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
5. Uses real experiences from the resume, enhanced with plausible detail
6. Shows a pattern of growth and increasing responsibility
7. If the candidate lacks traditional projects, create portfolio items from:
   - Work achievements at previous employers
   - Self-directed learning projects
   - Open source contributions
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
            max_tokens=4000
        )

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
            max_tokens=2000
        )

    async def generate_motivation_statement(
        self,
        user_profile: Dict[str, Any],
        company: str,
        company_info: Dict[str, Any],
        job_title: str
    ) -> Dict[str, Any]:
        """Generate a company-specific motivation statement."""
        import json

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
            max_tokens=3000
        )

    async def generate_portfolio_descriptions(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        projects: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate professional portfolio descriptions."""
        import json

        prompt = PORTFOLIO_DESCRIPTION_PROMPT.format(
            user_profile=json.dumps(user_profile, indent=2),
            job_title=job_title,
            projects=json.dumps(projects, indent=2)
        )

        return await self.ai_client.complete_json(
            prompt=prompt,
            system=DOCUMENT_SYSTEM,
            temperature=0.5,
            max_tokens=4000
        )

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
        )

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
        )

    async def generate_tailored_cv(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
        resume_text: str = "",
    ) -> str:
        """Generate a strategically tailored CV with experience enhancement."""
        import json

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

        prompt = TAILORED_CV_PROMPT.format(
            job_title=job_title,
            company=company,
            jd_text=jd_text[:4000],  # Truncate long JDs
            user_profile=json.dumps(user_profile, indent=2)[:4000],
            resume_text=(resume_text or "No resume text provided")[:3000],
            compatibility=compatibility,
            key_gaps=key_gaps_str,
            strengths=strengths_str,
        )

        return await self.ai_client.complete(
            prompt=prompt,
            system=TAILORED_CV_SYSTEM,
            temperature=0.6,
            max_tokens=8000,
        )

    async def generate_tailored_cover_letter(
        self,
        user_profile: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str,
        gap_analysis: Dict[str, Any],
    ) -> str:
        """Generate a strategically tailored cover letter."""
        import json

        skill_gaps = gap_analysis.get("skill_gaps", [])
        strengths = gap_analysis.get("strengths", [])
        key_gaps_str = ", ".join(
            g.get("skill", "") for g in skill_gaps[:6] if isinstance(g, dict)
        ) or "None identified"
        strengths_str = ", ".join(
            s.get("area", "") for s in strengths[:6] if isinstance(s, dict)
        ) or "Strong overall profile"

        prompt = TAILORED_CL_PROMPT.format(
            job_title=job_title,
            company=company,
            jd_text=jd_text[:3000],
            user_profile=json.dumps(user_profile, indent=2)[:3000],
            key_gaps=key_gaps_str,
            strengths=strengths_str,
        )

        return await self.ai_client.complete(
            prompt=prompt,
            system=TAILORED_CL_SYSTEM,
            temperature=0.65,
            max_tokens=3000,
        )
