"""
SkillDemandMapper — deterministic Phase 1 agent.

Maps user skills to demand levels, trend directions, and salary premiums
using a built-in knowledge base.  No LLM call.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


# (demand_level, trend, salary_premium_pct, note)
_SKILL_DB: dict[str, tuple[str, str, int, str]] = {
    # Languages
    "python":       ("high", "rising", 10, "Most in-demand language for AI/ML and automation"),
    "javascript":   ("high", "stable", 5, "Ubiquitous in web development"),
    "typescript":   ("high", "rising", 12, "Growing adoption for type-safe frontend/backend"),
    "java":         ("high", "stable", 5, "Enterprise backbone, strong in fintech"),
    "go":           ("high", "rising", 15, "Cloud-native and infrastructure demand"),
    "rust":         ("medium", "rising", 18, "Growing in systems programming and Wasm"),
    "c++":          ("medium", "stable", 8, "Embedded, gaming, HFT"),
    "c#":           ("medium", "stable", 5, "Enterprise, game dev (Unity)"),
    "ruby":         ("low", "declining", 0, "Niche — legacy Rails ecosystems"),
    "php":          ("low", "declining", -2, "Legacy web, WordPress ecosystem"),
    "swift":        ("medium", "stable", 8, "iOS ecosystem"),
    "kotlin":       ("medium", "rising", 10, "Android + server-side growing"),
    # Frameworks
    "react":        ("high", "stable", 8, "Dominant frontend framework"),
    "node":         ("high", "stable", 5, "Server-side JS standard"),
    "angular":      ("medium", "stable", 3, "Enterprise frontend"),
    "vue":          ("medium", "stable", 3, "Growing in startups"),
    "django":       ("medium", "stable", 5, "Python web framework"),
    "flask":        ("medium", "stable", 3, "Lightweight Python web"),
    "spring":       ("high", "stable", 5, "Java enterprise standard"),
    "next.js":      ("high", "rising", 12, "Full-stack React framework"),
    # Cloud & DevOps
    "aws":          ("high", "stable", 12, "Market-leading cloud platform"),
    "gcp":          ("medium", "rising", 10, "Strong in ML workloads"),
    "azure":        ("high", "rising", 10, "Enterprise cloud, fast growth"),
    "docker":       ("high", "stable", 5, "Container standard"),
    "kubernetes":   ("high", "rising", 15, "Orchestration demand growing"),
    "terraform":    ("high", "rising", 12, "IaC standard"),
    "ci/cd":        ("high", "stable", 5, "DevOps baseline expectation"),
    # Data & AI
    "machine learning": ("high", "rising", 20, "AI transformation across industries"),
    "deep learning":    ("high", "rising", 22, "Neural networks, generative AI"),
    "llm":              ("high", "rising", 25, "Generative AI — hottest market segment"),
    "nlp":              ("high", "rising", 18, "Language processing in high demand"),
    "data science":     ("high", "stable", 12, "Established high-value discipline"),
    "sql":              ("high", "stable", 3, "Universal data skill"),
    "postgresql":       ("high", "rising", 5, "Preferred OSS relational DB"),
    "mongodb":          ("medium", "stable", 3, "Document DB standard"),
    "redis":            ("medium", "stable", 5, "Caching/realtime"),
    "elasticsearch":    ("medium", "stable", 5, "Search infrastructure"),
    "spark":            ("medium", "stable", 8, "Big data processing"),
    # Practices
    "agile":        ("high", "stable", 0, "Expected methodology"),
    "scrum":        ("medium", "stable", 0, "Common agile framework"),
    "tdd":          ("medium", "rising", 3, "Quality-focused practices valued"),
    "microservices": ("high", "stable", 8, "Distributed systems architecture"),
    "graphql":      ("medium", "rising", 8, "API paradigm gaining traction"),
    "rest":         ("high", "stable", 0, "API baseline expectation"),
}


class SkillDemandMapper(SubAgent):
    """Maps user skills to demand/trend data from built-in knowledge base."""

    def __init__(self, ai_client=None):
        super().__init__(name="skill_demand_mapper", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        skills: list[str] = context.get("skills", [])

        mapped: list[dict[str, str]] = []
        unmapped: list[str] = []

        for skill in skills[:20]:
            key = skill.lower().strip()
            if key in _SKILL_DB:
                demand, trend, premium, note = _SKILL_DB[key]
                mapped.append({
                    "skill": skill,
                    "demand_level": demand,
                    "trend": trend,
                    "salary_premium": f"+{premium}%" if premium >= 0 else f"{premium}%",
                    "note": note,
                })
            else:
                unmapped.append(skill)

        # Sort by demand (high first) then by trend (rising first)
        demand_order = {"high": 0, "medium": 1, "low": 2}
        trend_order = {"rising": 0, "stable": 1, "declining": 2}
        mapped.sort(key=lambda s: (demand_order.get(s["demand_level"], 9), trend_order.get(s["trend"], 9)))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "skills_demand": mapped,
                "unmapped_skills": unmapped,
                "high_demand_count": sum(1 for s in mapped if s["demand_level"] == "high"),
                "rising_count": sum(1 for s in mapped if s["trend"] == "rising"),
            },
            confidence=0.85 if mapped else 0.40,
        )
