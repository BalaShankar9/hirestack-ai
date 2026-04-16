"""
RoleContextExtractor — deterministic Phase 1 agent.

Parses JD summary and profile summary to extract structured context:
key skills, domain terms, seniority indicators, and candidate strengths.
No LLM call — keyword matching and heuristics.
"""
from __future__ import annotations


from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


_SENIORITY_SIGNALS: dict[str, list[str]] = {
    "junior":  ["junior", "entry", "graduate", "intern", "trainee", "associate", "0-2 years"],
    "mid":     ["mid", "intermediate", "3-5 years", "ii", "level 2"],
    "senior":  ["senior", "lead", "principal", "5-10 years", "iii", "level 3", "sr.", "sr "],
    "staff":   ["staff", "architect", "distinguished", "fellow", "10+ years", "director"],
}

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "backend":    ["api", "rest", "graphql", "microservices", "database", "sql", "nosql", "server"],
    "frontend":   ["react", "vue", "angular", "css", "html", "ui", "ux", "javascript", "typescript"],
    "devops":     ["ci/cd", "docker", "kubernetes", "terraform", "aws", "gcp", "azure", "pipeline"],
    "data":       ["machine learning", "ml", "data science", "pandas", "spark", "analytics", "ai"],
    "mobile":     ["ios", "android", "swift", "kotlin", "react native", "flutter"],
    "security":   ["security", "penetration", "soc", "compliance", "encryption", "audit"],
    "management": ["manage", "leadership", "roadmap", "stakeholder", "agile", "scrum"],
}

_COMMON_TECH_SKILLS = [
    "python", "java", "javascript", "typescript", "go", "rust", "c++", "c#",
    "react", "node", "angular", "vue", "django", "flask", "spring",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "git", "ci/cd", "jenkins", "github actions",
    "machine learning", "deep learning", "llm", "nlp", "computer vision",
    "agile", "scrum", "kanban", "tdd", "microservices", "graphql", "rest",
]


class RoleContextExtractor(SubAgent):
    """Extracts structured role context from JD and profile text."""

    def __init__(self, ai_client=None):
        super().__init__(name="role_context_extractor", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        jd_summary: str = (context.get("jd_summary") or "").lower()
        profile_summary: str = (context.get("profile_summary") or "").lower()
        job_title: str = context.get("job_title", "")

        # ── Extract skills from JD ─────────────────────────────
        jd_skills = [s for s in _COMMON_TECH_SKILLS if s in jd_summary]
        profile_skills = [s for s in _COMMON_TECH_SKILLS if s in profile_summary]

        # ── Detect seniority ───────────────────────────────────
        seniority = "mid"  # default
        title_lower = job_title.lower()
        combined = f"{title_lower} {jd_summary}"
        for level, signals in _SENIORITY_SIGNALS.items():
            if any(sig in combined for sig in signals):
                seniority = level

        # ── Detect domains ─────────────────────────────────────
        domains: list[str] = []
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if any(kw in jd_summary for kw in keywords):
                domains.append(domain)
        if not domains:
            domains = ["general"]

        # ── Candidate strengths (profile skills that appear in JD)
        strengths = [s for s in profile_skills if s in jd_skills]

        # ── Company culture keywords ───────────────────────────
        culture_keywords: list[str] = []
        culture_terms = [
            "collaborative", "fast-paced", "innovative", "diverse",
            "remote", "hybrid", "startup", "enterprise", "mission-driven",
            "customer-focused", "data-driven", "growth", "inclusive",
        ]
        for term in culture_terms:
            if term in jd_summary:
                culture_keywords.append(term)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "job_title": job_title,
                "seniority": seniority,
                "domains": domains,
                "jd_skills": jd_skills,
                "profile_skills": profile_skills,
                "candidate_strengths": strengths,
                "culture_keywords": culture_keywords,
            },
            confidence=0.85,
        )
