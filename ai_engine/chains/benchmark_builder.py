"""
Benchmark Builder Chain
Creates ideal candidate profiles and benchmark application packages
"""
from typing import Dict, Any, List

from ai_engine.client import AIClient


BENCHMARK_SYSTEM = """You are an elite career strategist and talent acquisition expert with deep knowledge of:
- Industry hiring standards and expectations
- What makes candidates stand out to recruiters
- Realistic career progressions and achievements
- Current market demands and skill requirements

Your task is to create a comprehensive benchmark profile representing the IDEAL candidate for a specific role.
This benchmark should be realistic, achievable, and represent what a top-tier candidate would look like.

The benchmark serves as a reference point for candidates to understand what excellence looks like and where they need to improve.

Be specific, realistic, and thorough. Use real company names, realistic achievements, and authentic career progressions."""


IDEAL_PROFILE_PROMPT = """Create an IDEAL CANDIDATE PROFILE benchmark for this job.

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON (no markdown, no code fences). Keep it compact and strictly parseable.

Hard limits (do not exceed):
- ideal_skills: max 10 items
- ideal_experience: max 3 items (max 2 achievements each)
- ideal_education: max 2 items
- ideal_certifications: max 5 items
- soft_skills: max 6 items
- industry_knowledge: max 4 items

Rules:
- All string values must be single-line (no newline characters).
- Keep each string under ~180 characters.
- Use realistic company names, but do not invent personal contact details.
- Use numbers for weights; weights should sum to 1.0.

JSON schema:
{{
  "ideal_profile": {{
    "name": "Alex Johnson",
    "title": "Senior {job_title}",
    "years_experience": 7,
    "summary": "3-4 sentence summary (single line).",
    "key_differentiators": ["..."],
    "career_trajectory": "Single line."
  }},
  "ideal_skills": [{{"name":"...","level":"expert|advanced","years":5,"category":"technical|soft|domain","importance":"critical|important|preferred","proficiency_details":"Single line."}}],
  "ideal_experience": [{{"company":"...","title":"...","duration":"...","location":"...","description":"Single line.","key_achievements":["...","..."],"technologies":["..."],"relevance_to_role":"Single line."}}],
  "ideal_education": [{{"institution":"...","degree":"...","field":"...","relevance":"Single line."}}],
  "ideal_certifications": [{{"name":"...","issuer":"...","importance":"required|highly_recommended|nice_to_have","relevance":"Single line."}}],
  "soft_skills": [{{"skill":"...","evidence":"Single line.","importance":"critical|important"}}],
  "industry_knowledge": [{{"area":"...","depth":"expert|proficient","application":"Single line."}}],
  "scoring_weights": {{"technical_skills":0.30,"experience":0.25,"education":0.10,"certifications":0.10,"soft_skills":0.15,"industry_knowledge":0.10}}
}}"""


IDEAL_CV_PROMPT = """Create a professional CV for this ideal candidate profile:

IDEAL PROFILE:
{ideal_profile}

TARGET JOB:
{job_title} at {company}

Write a complete, professional CV in markdown format. Include:

1. **Header** - Name, title, contact info
2. **Professional Summary** - Compelling 3-4 sentences
3. **Core Competencies** - Key skills in a grid format
4. **Professional Experience** - 3-4 positions with achievements
5. **Education** - Degrees and relevant coursework
6. **Certifications** - Professional credentials
7. **Projects** - 2-3 notable projects if applicable
8. **Languages** - If relevant

Use specific metrics, real company names, and quantified achievements.
Format professionally using markdown headings, bullet points, and bold text.

Return ONLY the CV content in markdown format."""


IDEAL_COVER_LETTER_PROMPT = """Write a compelling cover letter for this ideal candidate:

IDEAL PROFILE:
{ideal_profile}

TARGET POSITION: {job_title}
TARGET COMPANY: {company}
COMPANY INFO: {company_info}

Write a professional, personalized cover letter that:
1. Opens with a compelling hook showing genuine interest
2. Demonstrates deep knowledge of the company
3. Connects experience to the specific role requirements
4. Shows cultural fit and alignment with company values
5. Includes specific examples of relevant achievements
6. Closes with a clear call to action

The letter should be 3-4 paragraphs, professional yet personable.

Return ONLY the cover letter text in markdown format."""


IDEAL_PORTFOLIO_PROMPT = """Create a portfolio of projects for this ideal candidate:

IDEAL PROFILE:
{ideal_profile}

TARGET ROLE: {job_title}

Create 3-4 realistic portfolio projects that demonstrate the skills needed for this role.

Return ONLY valid JSON:
```json
{{
  "projects": [
    {{
      "name": "Project Name",
      "type": "personal|professional|open_source",
      "description": "What the project does",
      "role": "Your contribution/role",
      "problem_solved": "Business/technical problem addressed",
      "technologies": ["Tech stack used"],
      "key_features": ["Notable features"],
      "outcomes": ["Measurable results or impact"],
      "challenges": ["Technical challenges overcome"],
      "learnings": ["Key takeaways"],
      "url": "GitHub or demo URL placeholder"
    }}
  ]
}}
```

Projects should be realistic, relevant, and demonstrate expertise."""


IDEAL_CASE_STUDIES_PROMPT = """Create professional case studies for this ideal candidate:

IDEAL PROFILE:
{ideal_profile}

TARGET ROLE: {job_title}
TARGET COMPANY: {company}

Create 2 detailed case studies showcasing problem-solving abilities.

Return ONLY valid JSON:
```json
{{
  "case_studies": [
    {{
      "title": "Case Study Title",
      "company": "Where this happened",
      "role": "Your role",
      "duration": "Project duration",
      "context": {{
        "situation": "Business context and challenges",
        "stakeholders": ["Who was involved"],
        "constraints": ["Time, budget, technical constraints"]
      }},
      "problem": {{
        "description": "Detailed problem statement",
        "impact": "Business impact of the problem",
        "root_causes": ["Underlying causes identified"]
      }},
      "approach": {{
        "methodology": "How you approached solving it",
        "steps": ["Step-by-step approach"],
        "tools_used": ["Technologies and tools"]
      }},
      "solution": {{
        "description": "What you built/implemented",
        "innovations": ["Novel approaches taken"],
        "implementation": "How it was rolled out"
      }},
      "results": {{
        "metrics": ["Quantified outcomes"],
        "business_impact": "Overall business value",
        "recognition": "Awards or acknowledgments"
      }},
      "learnings": ["Key lessons learned"]
    }}
  ]
}}
```"""


IDEAL_ACTION_PLAN_PROMPT = """Create a 3-month action plan/presentation for this ideal candidate:

IDEAL PROFILE:
{ideal_profile}

TARGET ROLE: {job_title}
TARGET COMPANY: {company}
COMPANY INFO: {company_info}

Create a comprehensive 90-day plan the candidate would present to show:
1. How they would ramp up in the role
2. Quick wins they would achieve
3. Strategic initiatives they would launch
4. How they would add value immediately

Return ONLY valid JSON:
```json
{{
  "action_plan": {{
    "title": "90-Day Success Plan for [Role]",
    "executive_summary": "Overview of the plan",
    "objectives": ["Top 3-5 objectives"],
    "month_1": {{
      "theme": "Learning & Quick Wins",
      "goals": ["Specific goals"],
      "activities": [
        {{
          "activity": "What to do",
          "purpose": "Why it matters",
          "deliverable": "Expected output"
        }}
      ],
      "success_metrics": ["How to measure success"]
    }},
    "month_2": {{
      "theme": "Building & Contributing",
      "goals": ["Specific goals"],
      "activities": [
        {{
          "activity": "What to do",
          "purpose": "Why it matters",
          "deliverable": "Expected output"
        }}
      ],
      "success_metrics": ["How to measure success"]
    }},
    "month_3": {{
      "theme": "Leading & Scaling",
      "goals": ["Specific goals"],
      "activities": [
        {{
          "activity": "What to do",
          "purpose": "Why it matters",
          "deliverable": "Expected output"
        }}
      ],
      "success_metrics": ["How to measure success"]
    }},
    "key_stakeholders": ["People to build relationships with"],
    "risks_and_mitigations": [
      {{
        "risk": "Potential challenge",
        "mitigation": "How to address it"
      }}
    ],
    "long_term_vision": "Where this leads in 6-12 months"
  }}
}}
```"""


BENCHMARK_CV_HTML_SYSTEM = """You are an elite career strategist and professional CV writer with 20+ years of experience.

YOUR MISSION: Create a COMPLETE, realistic CV for the ideal benchmark candidate — a "north star" reference document that shows what a perfect applicant's CV would look like for this role.

CRITICAL RULES:
1. **Use the REAL person's identity** — name, email, phone, address, LinkedIn — exactly as provided
2. **Create FICTIONAL but highly realistic experience** — use real, well-known companies in the industry with plausible job titles, aligned dates, and quantified achievements
3. **Dates must be realistic** — work backward from today, no overlapping dates, natural career progression (3-5 years per role, not jumping from intern to VP)
4. **Certifications must be real** — use actual certification names from recognized bodies (e.g., AWS Solutions Architect, PMP, CFA, Google Cloud Professional)
5. **Skills must match market demand** — include the exact technologies and methodologies from the job description
6. **Projects must be plausible** — real-sounding project names with concrete outcomes
7. **Education should be aspirational but realistic** — top universities in the relevant region

FORMAT: Return as clean, professional, ATS-friendly HTML. Use semantic HTML:
- <h1> for the candidate's name
- <p> directly under <h1> for contact: email | phone | location | LinkedIn
- <h2> for section headers: Professional Summary, Core Competencies, Professional Experience, Education, Certifications, Key Projects
- <h3> for company/role headers with dates
- <ul><li> for achievement bullets — EVERY bullet must have a metric (%, $, time saved, team size, etc.)
- <strong> for emphasis on key skills and metrics
- <em> for dates and locations

NO markdown. NO code fences. NO explanation. ONLY the HTML CV starting with <h1>."""


BENCHMARK_CV_HTML_PROMPT = """Create a COMPLETE ideal benchmark CV for this role, using the real candidate's identity.

═══════════════════════════════════════
TARGET ROLE: {job_title} at {company}
═══════════════════════════════════════

JOB DESCRIPTION:
{jd_text}

═══════════════════════════════════════
REAL CANDIDATE IDENTITY (use these details):
═══════════════════════════════════════
Name: {candidate_name}
Email: {candidate_email}
Phone: {candidate_phone}
Location: {candidate_location}
LinkedIn: {candidate_linkedin}

═══════════════════════════════════════
IDEAL BENCHMARK DATA (use this as the blueprint):
═══════════════════════════════════════
{benchmark_json}

═══════════════════════════════════════

Generate a FULL ideal CV that:
1. Uses the real candidate's name and contact info exactly as shown above
2. Has a powerful Professional Summary (3-4 sentences) perfectly aligned to the job
3. Lists Core Competencies as a comma-separated list matching JD keywords
4. Has 3-4 Professional Experience entries at REAL companies (e.g. Google, Microsoft, Stripe, McKinsey, Deloitte — pick companies relevant to this industry) with:
   - Realistic job titles showing clear career progression
   - Dates that work backward from the current year with no gaps or overlaps
   - 4-5 achievement bullets per role, EVERY bullet with a concrete metric
5. Education from a reputable university relevant to this field
6. 3-5 real certifications from recognized bodies
7. 2-3 Key Projects with technologies and measurable outcomes

Return ONLY the HTML content starting with <h1>. No explanation."""


class BenchmarkBuilderChain:
    """Chain for building ideal candidate benchmarks."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def build_complete_benchmark(
        self,
        job_title: str,
        company: str,
        job_description: str,
        company_info: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Build a complete benchmark package for a job."""
        # Step 1: Create ideal profile
        ideal_profile = await self.create_ideal_profile(
            job_title, company, job_description
        )

        # Step 2: Generate all benchmark documents
        ideal_cv = await self.create_ideal_cv(
            ideal_profile, job_title, company
        )

        ideal_cover_letter = await self.create_ideal_cover_letter(
            ideal_profile, job_title, company, company_info
        )

        ideal_portfolio = await self.create_ideal_portfolio(
            ideal_profile, job_title
        )

        ideal_case_studies = await self.create_ideal_case_studies(
            ideal_profile, job_title, company
        )

        ideal_action_plan = await self.create_ideal_action_plan(
            ideal_profile, job_title, company, company_info
        )

        return {
            "ideal_profile": ideal_profile.get("ideal_profile"),
            "ideal_skills": ideal_profile.get("ideal_skills", []),
            "ideal_experience": ideal_profile.get("ideal_experience", []),
            "ideal_education": ideal_profile.get("ideal_education", []),
            "ideal_certifications": ideal_profile.get("ideal_certifications", []),
            "soft_skills": ideal_profile.get("soft_skills", []),
            "industry_knowledge": ideal_profile.get("industry_knowledge", []),
            "scoring_weights": ideal_profile.get("scoring_weights", {}),
            "ideal_cv": ideal_cv,
            "ideal_cover_letter": ideal_cover_letter,
            "ideal_portfolio": ideal_portfolio.get("projects", []),
            "ideal_case_studies": ideal_case_studies.get("case_studies", []),
            "ideal_action_plan": ideal_action_plan.get("action_plan", {})
        }

    async def create_ideal_profile(
        self,
        job_title: str,
        company: str,
        job_description: str
    ) -> Dict[str, Any]:
        """Create the ideal candidate profile."""
        prompt = IDEAL_PROFILE_PROMPT.format(
            job_title=job_title,
            company=company,
            job_description=job_description
        )

        return await self.ai_client.complete_json(
            prompt=prompt,
            system=BENCHMARK_SYSTEM,
            temperature=0.4,
            max_tokens=4000
        )

    async def create_ideal_cv(
        self,
        ideal_profile: Dict[str, Any],
        job_title: str,
        company: str
    ) -> str:
        """Generate the ideal CV."""
        import json
        prompt = IDEAL_CV_PROMPT.format(
            ideal_profile=json.dumps(ideal_profile, indent=2),
            job_title=job_title,
            company=company
        )

        return await self.ai_client.complete(
            prompt=prompt,
            system=BENCHMARK_SYSTEM,
            temperature=0.5,
            max_tokens=3000
        )

    async def create_ideal_cover_letter(
        self,
        ideal_profile: Dict[str, Any],
        job_title: str,
        company: str,
        company_info: Dict[str, Any] = None
    ) -> str:
        """Generate the ideal cover letter."""
        import json
        prompt = IDEAL_COVER_LETTER_PROMPT.format(
            ideal_profile=json.dumps(ideal_profile, indent=2),
            job_title=job_title,
            company=company,
            company_info=json.dumps(company_info or {}, indent=2)
        )

        return await self.ai_client.complete(
            prompt=prompt,
            system=BENCHMARK_SYSTEM,
            temperature=0.6,
            max_tokens=2000
        )

    async def create_ideal_portfolio(
        self,
        ideal_profile: Dict[str, Any],
        job_title: str
    ) -> Dict[str, Any]:
        """Generate ideal portfolio projects."""
        import json
        prompt = IDEAL_PORTFOLIO_PROMPT.format(
            ideal_profile=json.dumps(ideal_profile, indent=2),
            job_title=job_title
        )

        return await self.ai_client.complete_json(
            prompt=prompt,
            system=BENCHMARK_SYSTEM,
            temperature=0.5,
            max_tokens=3000
        )

    async def create_ideal_case_studies(
        self,
        ideal_profile: Dict[str, Any],
        job_title: str,
        company: str
    ) -> Dict[str, Any]:
        """Generate ideal case studies."""
        import json
        prompt = IDEAL_CASE_STUDIES_PROMPT.format(
            ideal_profile=json.dumps(ideal_profile, indent=2),
            job_title=job_title,
            company=company
        )

        return await self.ai_client.complete_json(
            prompt=prompt,
            system=BENCHMARK_SYSTEM,
            temperature=0.5,
            max_tokens=4000
        )

    async def create_ideal_action_plan(
        self,
        ideal_profile: Dict[str, Any],
        job_title: str,
        company: str,
        company_info: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate ideal 90-day action plan."""
        import json
        prompt = IDEAL_ACTION_PLAN_PROMPT.format(
            ideal_profile=json.dumps(ideal_profile, indent=2),
            job_title=job_title,
            company=company,
            company_info=json.dumps(company_info or {}, indent=2)
        )

        return await self.ai_client.complete_json(
            prompt=prompt,
            system=BENCHMARK_SYSTEM,
            temperature=0.5,
            max_tokens=4000
        )

    async def create_benchmark_cv_html(
        self,
        user_profile: Dict[str, Any],
        benchmark_data: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str = "",
    ) -> str:
        """Generate a full ideal-candidate CV in HTML using the user's real identity
        but with benchmark-level experience, certifications, and skills."""
        import json

        contact = user_profile.get("contact_info", {}) or {}
        candidate_name = user_profile.get("name", "Ideal Candidate")
        candidate_email = contact.get("email", "candidate@email.com")
        candidate_phone = contact.get("phone", "")
        candidate_location = contact.get("location", "")
        candidate_linkedin = contact.get("linkedin", "")

        prompt = BENCHMARK_CV_HTML_PROMPT.format(
            job_title=job_title,
            company=company,
            jd_text=jd_text[:3000],
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_phone=candidate_phone,
            candidate_location=candidate_location,
            candidate_linkedin=candidate_linkedin,
            benchmark_json=json.dumps(benchmark_data, indent=2)[:4000],
        )

        html = await self.ai_client.complete(
            prompt=prompt,
            system=BENCHMARK_CV_HTML_SYSTEM,
            temperature=0.5,
            max_tokens=4000,
        )

        # Strip any markdown code fences the model might add
        html = html.strip()
        if html.startswith("```"):
            lines = html.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            html = "\n".join(lines).strip()

        return html
