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


IDEAL_PROFILE_PROMPT = """Create a comprehensive IDEAL CANDIDATE PROFILE for this job:

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION:
{job_description}

Create a detailed, realistic profile of the perfect candidate. Return ONLY valid JSON:

```json
{{
  "ideal_profile": {{
    "name": "Alex Johnson",
    "title": "Senior [Role Title]",
    "years_experience": 7,
    "summary": "Compelling 3-4 sentence professional summary",
    "key_differentiators": ["What makes this candidate exceptional"],
    "career_trajectory": "Brief description of ideal career path"
  }},
  "ideal_skills": [
    {{
      "name": "Skill Name",
      "level": "expert|advanced",
      "years": 5,
      "category": "technical|soft|domain",
      "importance": "critical|important|preferred",
      "proficiency_details": "Specific examples of expertise"
    }}
  ],
  "ideal_experience": [
    {{
      "company": "Real Company Name (e.g., Google, Stripe, McKinsey)",
      "title": "Job Title",
      "duration": "3 years",
      "location": "City, Country",
      "description": "Role overview",
      "key_achievements": [
        "Quantified achievement with metrics",
        "Leadership or impact example"
      ],
      "technologies": ["Relevant tech/tools"],
      "relevance_to_role": "Why this experience matters"
    }}
  ],
  "ideal_education": [
    {{
      "institution": "Top university name",
      "degree": "Degree type",
      "field": "Field of study",
      "relevance": "Why this education matters"
    }}
  ],
  "ideal_certifications": [
    {{
      "name": "Certification name",
      "issuer": "Issuing body",
      "importance": "required|highly_recommended|nice_to_have",
      "relevance": "Why this cert matters"
    }}
  ],
  "soft_skills": [
    {{
      "skill": "Leadership",
      "evidence": "How this would be demonstrated",
      "importance": "critical|important"
    }}
  ],
  "industry_knowledge": [
    {{
      "area": "Domain knowledge area",
      "depth": "expert|proficient",
      "application": "How it applies to the role"
    }}
  ],
  "scoring_weights": {{
    "technical_skills": 0.30,
    "experience": 0.25,
    "education": 0.10,
    "certifications": 0.10,
    "soft_skills": 0.15,
    "industry_knowledge": 0.10
  }}
}}
```

Create a realistic, achievable benchmark that represents top 10% of candidates for this role."""


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
