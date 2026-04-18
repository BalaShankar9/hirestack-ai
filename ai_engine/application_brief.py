"""
Application Brief — compute-once structured context for AI pipelines.

Instead of injecting raw JD text (5-15K tokens), full resume text (3-8K tokens),
and profile JSON (2-5K tokens) into EVERY LLM call, we compute a compact
structured brief ONCE per application and pass it to all downstream agents.

Cost savings: ~80% reduction in input tokens per pipeline call.
  - Raw context per call: ~10-25K tokens
  - Brief per call: ~1.5-3K tokens
  - With 30-50 calls per run: saves 250K-1M tokens per generation

The brief is a structured dictionary containing:
  - role_summary: 2-3 sentence role distillation
  - key_requirements: top 10 must-have requirements from JD
  - keywords: extracted ATS keywords (ranked by importance)
  - company_context: 2-3 sentence company + culture summary
  - candidate_strengths: top strengths matched to this role
  - candidate_gaps: prioritized gaps/weaknesses
  - tone_guidance: target tone for documents
  - match_score: quick compatibility percentage
  - experience_level: junior/mid/senior/lead/executive

The brief is cached by content hash so identical JD+profile combos
share the same brief across users (JD-hash) and across regenerations.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hirestack.application_brief")

# ═══════════════════════════════════════════════════════════════════════
#  Brief data structures
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ApplicationBrief:
    """Compact, pre-computed context for a specific job application."""

    # Role distillation
    role_summary: str = ""
    experience_level: str = "mid"  # junior/mid/senior/lead/executive
    key_requirements: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    nice_to_haves: List[str] = field(default_factory=list)

    # Company context
    company_name: str = ""
    company_context: str = ""
    tone_guidance: str = ""

    # Candidate analysis
    candidate_summary: str = ""
    candidate_strengths: List[str] = field(default_factory=list)
    candidate_gaps: List[str] = field(default_factory=list)
    match_score: int = 0
    years_experience: int = 0

    # Job metadata
    job_title: str = ""
    industry: str = ""
    location: str = ""

    # Content hash for caching
    brief_hash: str = ""
    computed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_prompt_context(self) -> str:
        """Render the brief as a compact prompt section (~1.5-3K tokens).

        This replaces the raw JD + resume + profile injection in every call.
        """
        sections = [
            f"## Application Brief",
            f"**Role:** {self.job_title} at {self.company_name}",
            f"**Level:** {self.experience_level} | **Match:** {self.match_score}%",
        ]

        if self.role_summary:
            sections.append(f"\n### Role Summary\n{self.role_summary}")

        if self.key_requirements:
            req_list = "\n".join(f"- {r}" for r in self.key_requirements[:10])
            sections.append(f"\n### Key Requirements\n{req_list}")

        if self.keywords:
            sections.append(f"\n### ATS Keywords\n{', '.join(self.keywords[:20])}")

        if self.company_context:
            sections.append(f"\n### Company Context\n{self.company_context}")

        if self.tone_guidance:
            sections.append(f"\n### Tone Guidance\n{self.tone_guidance}")

        if self.candidate_summary:
            sections.append(f"\n### Candidate Profile\n{self.candidate_summary}")

        if self.candidate_strengths:
            strengths = "\n".join(f"- {s}" for s in self.candidate_strengths[:8])
            sections.append(f"\n### Strengths (matched to role)\n{strengths}")

        if self.candidate_gaps:
            gaps = "\n".join(f"- {g}" for g in self.candidate_gaps[:6])
            sections.append(f"\n### Gaps to Address\n{gaps}")

        if self.nice_to_haves:
            nice = "\n".join(f"- {n}" for n in self.nice_to_haves[:5])
            sections.append(f"\n### Nice-to-Haves\n{nice}")

        return "\n".join(sections)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ApplicationBrief":
        """Reconstruct from a dictionary (e.g. from DB/cache)."""
        brief = ApplicationBrief()
        for k, v in d.items():
            if hasattr(brief, k):
                setattr(brief, k, v)
        return brief


# ═══════════════════════════════════════════════════════════════════════
#  Brief computation — single LLM call to distill raw inputs
# ═══════════════════════════════════════════════════════════════════════

_BRIEF_SYSTEM_PROMPT = """You are an expert recruitment analyst. Given a job description, candidate resume, and optional company intel, produce a structured application brief that distills the key information needed to generate tailored application documents.

Be concise and specific. Focus on actionable intelligence, not generic observations.
Return valid JSON matching the schema exactly."""

_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "role_summary": {"type": "string", "description": "2-3 sentence distillation of what this role requires and why it exists"},
        "experience_level": {"type": "string", "enum": ["junior", "mid", "senior", "lead", "executive"]},
        "key_requirements": {"type": "array", "items": {"type": "string"}, "description": "Top 10 must-have requirements from the JD, ranked by importance"},
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "Top 20 ATS keywords for this role, ranked by importance"},
        "nice_to_haves": {"type": "array", "items": {"type": "string"}, "description": "Up to 5 nice-to-have requirements"},
        "company_context": {"type": "string", "description": "2-3 sentence company + culture summary relevant to application tone"},
        "tone_guidance": {"type": "string", "description": "One sentence describing the ideal tone for application documents"},
        "candidate_summary": {"type": "string", "description": "2-3 sentence summary of the candidate's relevant background"},
        "candidate_strengths": {"type": "array", "items": {"type": "string"}, "description": "Top 8 strengths matched to this specific role"},
        "candidate_gaps": {"type": "array", "items": {"type": "string"}, "description": "Up to 6 gaps or weaknesses relative to requirements"},
        "match_score": {"type": "integer", "description": "Compatibility score 0-100"},
        "years_experience": {"type": "integer", "description": "Estimated years of relevant experience"},
        "industry": {"type": "string", "description": "Primary industry for this role"},
        "location": {"type": "string", "description": "Job location if mentioned"},
    },
    "required": ["role_summary", "key_requirements", "keywords", "candidate_strengths", "candidate_gaps", "match_score"],
}


def _compute_brief_hash(jd_text: str, resume_text: str, job_title: str, company: str) -> str:
    """Content-addressed hash for brief caching."""
    payload = json.dumps({
        "jd": jd_text.strip()[:8000],
        "resume": resume_text.strip()[:8000],
        "title": job_title.strip().lower(),
        "company": company.strip().lower(),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── In-memory brief cache (content-addressed) ──────────────────────────
_brief_cache: Dict[str, ApplicationBrief] = {}
_BRIEF_CACHE_MAX = 200


def _get_cached_brief(brief_hash: str) -> Optional[ApplicationBrief]:
    """Check in-memory cache for an existing brief."""
    brief = _brief_cache.get(brief_hash)
    if brief and (time.time() - brief.computed_at) < 7200:  # 2hr TTL
        logger.info("brief_cache_hit: hash=%s", brief_hash)
        return brief
    return None


def _cache_brief(brief: ApplicationBrief) -> None:
    """Store a computed brief in the in-memory cache."""
    _brief_cache[brief.brief_hash] = brief
    # Evict oldest if over capacity
    if len(_brief_cache) > _BRIEF_CACHE_MAX:
        oldest_key = min(_brief_cache, key=lambda k: _brief_cache[k].computed_at)
        _brief_cache.pop(oldest_key, None)


async def compute_application_brief(
    *,
    jd_text: str,
    resume_text: str,
    job_title: str,
    company: str,
    company_intel: Optional[Dict[str, Any]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    ai_client: Any = None,
    force_recompute: bool = False,
) -> ApplicationBrief:
    """Compute or retrieve a cached application brief.

    This is the primary entry point. Call once at the start of generation,
    then pass the brief to all downstream pipeline stages.

    Uses Flash model (cheapest) since this is structured extraction, not reasoning.
    """
    brief_hash = _compute_brief_hash(jd_text, resume_text, job_title, company)

    # Check cache first
    if not force_recompute:
        cached = _get_cached_brief(brief_hash)
        if cached:
            return cached

    # Build the extraction prompt
    prompt_parts = [
        f"# Job Title: {job_title}",
        f"# Company: {company}" if company.strip() else "",
        f"\n## Job Description:\n{jd_text[:6000]}",
    ]

    if resume_text.strip():
        prompt_parts.append(f"\n## Candidate Resume:\n{resume_text[:6000]}")

    if company_intel and isinstance(company_intel, dict):
        intel_summary = company_intel.get("application_strategy_digest", "")
        if not intel_summary:
            # Build a quick summary from available intel
            parts = []
            if company_intel.get("industry"):
                parts.append(f"Industry: {company_intel['industry']}")
            if company_intel.get("culture_signals"):
                parts.append(f"Culture: {', '.join(company_intel['culture_signals'][:3])}")
            if company_intel.get("tech_stack"):
                parts.append(f"Tech: {', '.join(company_intel['tech_stack'][:5])}")
            intel_summary = "; ".join(parts)
        if intel_summary:
            prompt_parts.append(f"\n## Company Intel:\n{intel_summary[:1000]}")

    if user_profile and isinstance(user_profile, dict):
        # Include key profile fields if not already in resume
        skills = user_profile.get("skills", [])
        if skills:
            skill_names = [s.get("name", s) if isinstance(s, dict) else str(s) for s in skills[:15]]
            prompt_parts.append(f"\n## Known Skills: {', '.join(skill_names)}")

    prompt = "\n".join(p for p in prompt_parts if p)
    prompt += "\n\nAnalyze the above and produce the application brief JSON."

    # Use the AI client to compute the brief
    if ai_client is None:
        from ai_engine.client import get_ai_client
        ai_client = get_ai_client()

    start = time.time()
    try:
        result = await ai_client.complete_json(
            prompt=prompt,
            system=_BRIEF_SYSTEM_PROMPT,
            temperature=0.2,
            schema=_BRIEF_SCHEMA,
            task_type="structured_output",
            model="gemini-2.5-flash",  # Always use Flash — this is extraction, not reasoning
        )
    except Exception as exc:
        logger.warning("brief_computation_failed: %s — building fallback", str(exc)[:200])
        result = _build_fallback_brief(jd_text, resume_text, job_title, company)

    # Construct the ApplicationBrief
    brief = ApplicationBrief(
        role_summary=result.get("role_summary", ""),
        experience_level=result.get("experience_level", "mid"),
        key_requirements=result.get("key_requirements", [])[:10],
        keywords=result.get("keywords", [])[:20],
        nice_to_haves=result.get("nice_to_haves", [])[:5],
        company_name=company,
        company_context=result.get("company_context", ""),
        tone_guidance=result.get("tone_guidance", ""),
        candidate_summary=result.get("candidate_summary", ""),
        candidate_strengths=result.get("candidate_strengths", [])[:8],
        candidate_gaps=result.get("candidate_gaps", [])[:6],
        match_score=min(100, max(0, int(result.get("match_score", 0)))),
        years_experience=max(0, int(result.get("years_experience", 0))),
        job_title=job_title,
        industry=result.get("industry", ""),
        location=result.get("location", ""),
        brief_hash=brief_hash,
        computed_at=time.time(),
    )

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info(
        "brief_computed: hash=%s match=%d%% keywords=%d strengths=%d gaps=%d elapsed=%dms",
        brief_hash, brief.match_score, len(brief.keywords),
        len(brief.candidate_strengths), len(brief.candidate_gaps), elapsed_ms,
    )

    _cache_brief(brief)
    return brief


def _build_fallback_brief(
    jd_text: str, resume_text: str, job_title: str, company: str,
) -> Dict[str, Any]:
    """Deterministic fallback if LLM brief computation fails.

    Extracts basic keywords and structure without an LLM call.
    """
    import re

    # Extract potential keywords from JD (simple heuristic)
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', jd_text)
    # Also grab common tech terms
    tech_terms = re.findall(
        r'\b(?:Python|Java|JavaScript|TypeScript|React|Node\.?js|AWS|Azure|GCP|Docker|'
        r'Kubernetes|SQL|NoSQL|MongoDB|PostgreSQL|Redis|GraphQL|REST|API|CI/CD|'
        r'Machine Learning|AI|ML|NLP|TensorFlow|PyTorch|Agile|Scrum)\b',
        jd_text, re.IGNORECASE,
    )
    keywords = list(dict.fromkeys(tech_terms + words[:20]))[:20]

    return {
        "role_summary": f"Role: {job_title} at {company or 'the company'}.",
        "experience_level": "mid",
        "key_requirements": [],
        "keywords": keywords,
        "nice_to_haves": [],
        "company_context": f"Company: {company}" if company else "",
        "tone_guidance": "Professional and confident",
        "candidate_summary": "",
        "candidate_strengths": [],
        "candidate_gaps": [],
        "match_score": 50,
        "years_experience": 0,
        "industry": "",
        "location": "",
    }


# ═══════════════════════════════════════════════════════════════════════
#  JD-only brief (cross-user shareable)
# ═══════════════════════════════════════════════════════════════════════

def _jd_hash(jd_text: str, job_title: str) -> str:
    """Hash just the JD + title for cross-user caching of JD analysis."""
    payload = json.dumps({
        "jd": jd_text.strip()[:8000],
        "title": job_title.strip().lower(),
    }, sort_keys=True)
    return "jd_" + hashlib.sha256(payload.encode()).hexdigest()[:16]


_jd_analysis_cache: Dict[str, Dict[str, Any]] = {}


async def get_jd_analysis(
    *,
    jd_text: str,
    job_title: str,
    ai_client: Any = None,
) -> Dict[str, Any]:
    """Extract JD-only analysis (shareable across all applicants for the same JD).

    Returns: {key_requirements, keywords, nice_to_haves, role_summary,
              experience_level, industry, location, tone_guidance}
    """
    cache_key = _jd_hash(jd_text, job_title)

    cached = _jd_analysis_cache.get(cache_key)
    if cached and (time.time() - cached.get("_ts", 0)) < 14400:  # 4hr TTL
        logger.info("jd_analysis_cache_hit: key=%s", cache_key)
        return cached

    if ai_client is None:
        from ai_engine.client import get_ai_client
        ai_client = get_ai_client()

    prompt = (
        f"# Job Title: {job_title}\n\n"
        f"## Job Description:\n{jd_text[:6000]}\n\n"
        "Extract the structured analysis from this job description."
    )

    jd_schema = {
        "type": "object",
        "properties": {
            "role_summary": {"type": "string"},
            "experience_level": {"type": "string", "enum": ["junior", "mid", "senior", "lead", "executive"]},
            "key_requirements": {"type": "array", "items": {"type": "string"}},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "nice_to_haves": {"type": "array", "items": {"type": "string"}},
            "industry": {"type": "string"},
            "location": {"type": "string"},
            "tone_guidance": {"type": "string"},
        },
        "required": ["key_requirements", "keywords"],
    }

    try:
        result = await ai_client.complete_json(
            prompt=prompt,
            system="Extract structured job analysis. Be precise and concise. Return valid JSON.",
            temperature=0.1,
            schema=jd_schema,
            task_type="structured_output",
            model="gemini-2.5-flash",
        )
    except Exception as exc:
        logger.warning("jd_analysis_failed: %s", str(exc)[:200])
        result = {"key_requirements": [], "keywords": [], "role_summary": job_title}

    result["_ts"] = time.time()
    _jd_analysis_cache[cache_key] = result

    # Evict old entries
    if len(_jd_analysis_cache) > 500:
        oldest = min(_jd_analysis_cache, key=lambda k: _jd_analysis_cache[k].get("_ts", 0))
        _jd_analysis_cache.pop(oldest, None)

    return result
