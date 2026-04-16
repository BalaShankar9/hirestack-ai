"""
SkillGapFinder — deterministic Phase 1 agent.

Compares the user's listed skills against an in-demand skills database
for their role category, and reports missing high-value skills.
No LLM call — lookup tables.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

# Skills grouped by role-family — top in-demand skills for LinkedIn
_DEMAND_DB: dict[str, list[str]] = {
    "engineering": [
        "Python", "TypeScript", "React", "Node.js", "AWS", "Docker","Kubernetes",
        "CI/CD", "PostgreSQL", "System Design", "REST APIs", "GraphQL",
        "Terraform", "Microservices", "Git",
    ],
    "data": [
        "Python", "SQL", "Machine Learning", "TensorFlow", "PyTorch",
        "Pandas", "Spark", "Tableau", "Power BI", "Statistics",
        "Data Modeling", "ETL", "Airflow", "dbt", "Snowflake",
    ],
    "product": [
        "Product Strategy", "Agile", "User Research", "A/B Testing",
        "Roadmapping", "Stakeholder Management", "SQL", "Figma",
        "Jira", "OKRs", "Go-to-Market", "Data Analysis",
    ],
    "design": [
        "Figma", "User Research", "Prototyping", "Design Systems",
        "Accessibility", "Interaction Design", "Visual Design",
        "Wireframing", "Usability Testing", "Adobe XD",
    ],
    "leadership": [
        "Strategic Planning", "Team Building", "P&L Management",
        "Stakeholder Management", "Change Management", "Executive Communication",
        "OKRs", "Agile", "Coaching", "Cross-functional Leadership",
    ],
    "marketing": [
        "Digital Marketing", "SEO", "Content Strategy", "Google Analytics",
        "Social Media Marketing", "Email Marketing", "CRM", "HubSpot",
        "Copywriting", "Brand Strategy", "A/B Testing",
    ],
    "default": [
        "Communication", "Leadership", "Project Management", "Data Analysis",
        "Problem Solving", "Agile", "CRM", "Presentation Skills",
        "Stakeholder Management", "Process Improvement",
    ],
}

_ROLE_CATEGORY_MAP: dict[str, str] = {
    "engineer": "engineering", "developer": "engineering", "swe": "engineering",
    "backend": "engineering", "frontend": "engineering", "fullstack": "engineering",
    "devops": "engineering", "sre": "engineering", "platform": "engineering",
    "architect": "engineering",
    "data scientist": "data", "data engineer": "data", "ml engineer": "data",
    "analyst": "data", "machine learning": "data", "data analyst": "data",
    "product manager": "product", "product owner": "product", "pm": "product",
    "designer": "design", "ux": "design", "ui": "design",
    "cto": "leadership", "vp": "leadership", "director": "leadership",
    "head of": "leadership", "manager": "leadership", "lead": "leadership",
    "marketing": "marketing", "growth": "marketing", "content": "marketing",
}


class SkillGapFinder(SubAgent):
    """Finds in-demand skills the user is missing for their role category."""

    def __init__(self, ai_client=None):
        super().__init__(name="skill_gap_finder", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        profile: dict = context.get("profile_data", {})
        title: str = (profile.get("title") or "").lower()

        user_skills_raw: list[dict] = profile.get("skills") or []
        user_skill_names: set[str] = set()
        for s in user_skills_raw:
            if isinstance(s, dict):
                user_skill_names.add(s.get("name", "").lower().strip())

        # Determine category
        category = "default"
        for keyword, cat in _ROLE_CATEGORY_MAP.items():
            if keyword in title:
                category = cat
                break

        demand_skills: list[str] = _DEMAND_DB.get(category, _DEMAND_DB["default"])

        missing: list[str] = []
        present: list[str] = []
        for skill in demand_skills:
            if skill.lower() in user_skill_names:
                present.append(skill)
            else:
                missing.append(skill)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "role_category": category,
                "missing_high_demand_skills": missing[:12],
                "present_high_demand_skills": present,
                "gap_count": len(missing),
                "coverage_pct": round(len(present) / max(len(demand_skills), 1) * 100),
            },
            confidence=0.85,
        )
