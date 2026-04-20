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


# ── Resume (US-style, 1–2 page, achievement-focused) ─────────────────────────
# Distinct from CV: shorter, sharper, scannable, metric-led, no academic
# overload. Resume is the canonical Benchmark/Tailored doc for US-style hiring.

BENCHMARK_RESUME_HTML_SYSTEM = """You are an elite resume writer with 20+ years of experience writing ATS-optimised, recruiter-friendly US-style résumés.

YOUR MISSION: Create a COMPLETE, realistic 1–2 PAGE résumé for the ideal benchmark candidate — the "north-star" reference document showing what a top applicant's résumé would look like for this role.

CRITICAL DIFFERENCE FROM A CV:
- A résumé is SHORT, SCANNABLE, and ACHIEVEMENT-LED. Aim for ~1 page (max ~2).
- No academic publications, no thesis, no full coursework lists, no exhaustive history.
- 3 roles maximum (most recent + most relevant). 3–5 bullets each, EVERY bullet a measurable result.
- 1 short Summary (2–3 lines).
- Tight Core Skills row (8–14 keywords matching the JD).
- Education: 1–2 entries, just degree/institution/year.
- Certifications: only those directly relevant.
- No Projects section unless they materially differentiate the candidate (then 1–2 only).

CRITICAL RULES:
1. Use the REAL person's identity — name, email, phone, location, LinkedIn — exactly as provided.
2. Create FICTIONAL but highly realistic experience — real, well-known companies in the relevant industry, plausible job titles, aligned dates, quantified achievements.
3. Dates must be realistic — work backward from today, no overlaps or gaps, natural progression.
4. Certifications must be real (AWS, Google Cloud, PMP, CFA, Scrum, etc.) — only include highly relevant ones.
5. Skills must mirror exact JD keywords for ATS.
6. Every bullet must lead with a strong action verb and end with a measurable outcome.

FORMAT: Return as clean, professional, ATS-friendly HTML. Use semantic HTML:
- <h1> for the candidate's name
- <p> directly under <h1> for contact: email | phone | location | LinkedIn
- <h2> for sections: Summary, Core Skills, Experience, Education, Certifications
- <h3> for company/role headers with dates
- <ul><li> for achievement bullets — EVERY bullet with a metric
- <strong> for emphasis on metrics; <em> for dates/locations

NO markdown. NO code fences. NO explanation. ONLY the HTML résumé starting with <h1>."""


BENCHMARK_RESUME_HTML_PROMPT = """Create a COMPLETE ideal benchmark RÉSUMÉ for this role, using the real candidate's identity. Keep it 1–2 pages.

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

Generate a FULL ideal résumé that:
1. Uses the real candidate's name and contact info exactly as shown.
2. Opens with a 2–3 line Summary perfectly aligned to the role.
3. Lists 8–14 Core Skills as a comma-separated row matching JD keywords.
4. Has 3 Experience entries at REAL companies (Google, Microsoft, Stripe, McKinsey, Deloitte, etc. — pick industry-relevant). Each:
   - Realistic title showing progression
   - Dates backward from current year, no gaps/overlaps
   - 3–5 bullets, EVERY bullet led by an action verb and ending with a metric
5. Education: 1–2 entries (degree, institution, year).
6. Certifications: 2–4, all directly relevant.

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

        raw = await self.ai_client.complete_json(
            prompt=prompt,
            system=BENCHMARK_SYSTEM,
            temperature=0.4,
            max_tokens=4000,
            task_type="reasoning",
        )
        return self._validate_ideal_profile(raw)

    def _validate_ideal_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize benchmark profile for downstream Atlas stability."""
        if not isinstance(profile, dict):
            profile = {}

        profile.setdefault("ideal_profile", {})
        profile.setdefault("ideal_skills", [])
        profile.setdefault("ideal_experience", [])
        profile.setdefault("ideal_education", [])
        profile.setdefault("ideal_certifications", [])
        profile.setdefault("soft_skills", [])
        profile.setdefault("industry_knowledge", [])
        profile.setdefault("scoring_weights", {})

        # Enforce prompt caps to keep payload bounded and deterministic.
        profile["ideal_skills"] = list(profile.get("ideal_skills") or [])[:10]
        profile["ideal_experience"] = list(profile.get("ideal_experience") or [])[:3]
        profile["ideal_education"] = list(profile.get("ideal_education") or [])[:2]
        profile["ideal_certifications"] = list(profile.get("ideal_certifications") or [])[:5]
        profile["soft_skills"] = list(profile.get("soft_skills") or [])[:6]
        profile["industry_knowledge"] = list(profile.get("industry_knowledge") or [])[:4]

        quality_flags: List[str] = []
        if not profile.get("ideal_skills"):
            quality_flags.append("missing_skills")
        if not profile.get("ideal_experience"):
            quality_flags.append("missing_experience")
        if not isinstance(profile.get("ideal_profile"), dict) or not profile["ideal_profile"].get("title"):
            quality_flags.append("missing_profile_title")

        weights = profile.get("scoring_weights")
        if not isinstance(weights, dict):
            weights = {}
        weight_sum = 0.0
        for value in weights.values():
            if isinstance(value, (int, float)):
                weight_sum += float(value)
        if weights and abs(weight_sum - 1.0) > 0.05:
            quality_flags.append("weight_sum_not_1")

        profile["benchmark_quality_flags"] = quality_flags
        profile["benchmark_quality_score"] = round(max(0.0, 1.0 - 0.2 * len(quality_flags)), 2)
        return profile

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

    async def generate_perfect_application(
        self,
        jd_text: str,
        job_title: str,
        company: str,
        user_profile: Dict[str, Any],
        required_documents: List[Dict[str, Any]],
        discovery_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Generate a COMPLETE 100% match application with ALL required documents.

        Uses the user's real data as the base, fabricates any missing details
        to create the perfect benchmark application.
        """
        from ai_engine.chains.adaptive_document import AdaptiveDocumentChain

        # Step 1: Create perfect profile (existing method)
        ideal_data = await self.create_ideal_profile(job_title, company, jd_text)

        # Step 2: Merge user's real data with ideal profile for benchmark context
        merged_profile = dict(user_profile)
        ideal = ideal_data.get("ideal_profile") or {}
        # Keep user's real identity but enhance with ideal qualifications
        merged_profile["name"] = user_profile.get("name") or ideal.get("name", "Ideal Candidate")
        merged_profile["title"] = ideal.get("title") or user_profile.get("title", "")
        merged_profile["summary"] = ideal.get("summary") or user_profile.get("summary", "")

        # Merge skills: user's real + ideal additions
        user_skills = user_profile.get("skills") or []
        ideal_skills = ideal_data.get("ideal_skills") or []
        merged_skills = list(user_skills)
        existing_names = {s.get("name", "").lower() for s in user_skills if isinstance(s, dict)}
        for s in ideal_skills:
            if isinstance(s, dict) and s.get("name", "").lower() not in existing_names:
                merged_skills.append({"name": s["name"], "level": s.get("level", "advanced"), "category": s.get("category", "technical"), "source": "benchmark"})
        merged_profile["skills"] = merged_skills

        # Merge experience: user's real + ideal additions
        user_exp = user_profile.get("experience") or []
        ideal_exp = ideal_data.get("ideal_experience") or []
        merged_profile["experience"] = user_exp + [
            {**e, "source": "benchmark"} for e in ideal_exp
            if isinstance(e, dict) and not any(
                ue.get("company", "").lower() == e.get("company", "").lower()
                for ue in user_exp if isinstance(ue, dict)
            )
        ]

        # Build context for document generation
        context = {
            "profile": merged_profile,
            "jd_text": jd_text,
            "job_title": job_title,
            "company": company,
            "industry": (discovery_context or {}).get("industry", "professional"),
            "tone": (discovery_context or {}).get("tone", "professional"),
            "key_themes": (discovery_context or {}).get("key_themes", []),
            "benchmark_keywords": ", ".join(
                s.get("name", "") for s in ideal_skills[:15] if isinstance(s, dict)
            ),
        }

        # Step 3: Generate every required document using AdaptiveDocumentChain
        doc_chain = AdaptiveDocumentChain(self.ai_client)
        benchmark_documents: Dict[str, str] = {}

        for doc in required_documents:
            doc_key = doc.get("key", "")
            doc_label = doc.get("label", doc_key)
            if doc_key in ("learning_plan", "scorecard"):
                continue  # Skip internal modules for benchmark

            try:
                html = await doc_chain.generate(
                    doc_type=doc_key,
                    doc_label=doc_label,
                    context=context,
                    mode="benchmark",
                )
                benchmark_documents[doc_key] = html
            except Exception as e:
                benchmark_documents[doc_key] = f"<p>Generation failed: {str(e)[:100]}</p>"

        # Track what was fabricated vs real
        enhancements = []
        for s in merged_skills:
            if isinstance(s, dict) and s.get("source") == "benchmark":
                enhancements.append(f"Added skill: {s.get('name')}")
        for e in merged_profile.get("experience", []):
            if isinstance(e, dict) and e.get("source") == "benchmark":
                enhancements.append(f"Added experience: {e.get('title')} at {e.get('company')}")

        return {
            "ideal_profile": ideal,
            "ideal_skills": ideal_data.get("ideal_skills", []),
            "ideal_experience": ideal_data.get("ideal_experience", []),
            "ideal_education": ideal_data.get("ideal_education", []),
            "ideal_certifications": ideal_data.get("ideal_certifications", []),
            "scoring_weights": ideal_data.get("scoring_weights", {}),
            "benchmark_documents": benchmark_documents,
            "enhancements_made": enhancements,
            "score": 100,
        }

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
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            html = "\n".join(lines).strip()

        return html

    async def create_resume_html(
        self,
        user_profile: Dict[str, Any],
        benchmark_data: Dict[str, Any],
        job_title: str,
        company: str,
        jd_text: str = "",
    ) -> str:
        """Generate an ideal-candidate RÉSUMÉ in HTML — the US-style 1–2 page,
        achievement-focused counterpart to the long-form CV.

        Same identity, same benchmark blueprint, but distinct prompt that enforces
        brevity, scannability, metric-led bullets, and ATS-friendly structure.
        """
        import json

        contact = user_profile.get("contact_info", {}) or {}
        candidate_name = user_profile.get("name", "Ideal Candidate")
        candidate_email = contact.get("email", "candidate@email.com")
        candidate_phone = contact.get("phone", "")
        candidate_location = contact.get("location", "")
        candidate_linkedin = contact.get("linkedin", "")

        prompt = BENCHMARK_RESUME_HTML_PROMPT.format(
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
            system=BENCHMARK_RESUME_HTML_SYSTEM,
            temperature=0.5,
            max_tokens=3000,  # tighter than CV — it should be shorter
        )

        # Strip any markdown code fences the model might add
        html = html.strip()
        if html.startswith("```"):
            lines = html.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            html = "\n".join(lines).strip()

        return html
