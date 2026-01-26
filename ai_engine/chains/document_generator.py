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


# Import List for type hints
from typing import List
