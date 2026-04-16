"""
TrendMapper — deterministic Phase 1 agent.

Maps skill categories to emerging industry trends and their relevance
to the user's profile.  No LLM call — curated trend database.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


_TREND_DB: list[dict[str, str]] = [
    {
        "trend": "Generative AI & LLM Engineering",
        "keywords": "llm,nlp,machine learning,deep learning,python,ai",
        "relevance_if_match": "high",
        "description": "Companies are rapidly hiring for LLM fine-tuning, RAG pipelines, and AI agent development.",
        "timeframe": "0-12 months",
    },
    {
        "trend": "Platform Engineering & Developer Experience",
        "keywords": "kubernetes,docker,terraform,ci/cd,devops,go",
        "relevance_if_match": "high",
        "description": "Internal developer platforms and golden paths are a top priority for engineering orgs.",
        "timeframe": "6-18 months",
    },
    {
        "trend": "Rust in Production Systems",
        "keywords": "rust,c++,systems,performance",
        "relevance_if_match": "medium",
        "description": "Rust adoption is growing for performance-critical services, Wasm, and security-sensitive code.",
        "timeframe": "12-24 months",
    },
    {
        "trend": "Edge Computing & IoT",
        "keywords": "embedded,iot,edge,aws,gcp,azure",
        "relevance_if_match": "medium",
        "description": "Processing at the edge is expanding for low-latency and data-sovereignty use cases.",
        "timeframe": "6-18 months",
    },
    {
        "trend": "Data Engineering Modernization",
        "keywords": "spark,sql,data science,postgresql,analytics,python",
        "relevance_if_match": "high",
        "description": "Modern data stacks (dbt, Snowflake, real-time streaming) are replacing legacy ETL.",
        "timeframe": "0-12 months",
    },
    {
        "trend": "Full-Stack TypeScript",
        "keywords": "typescript,react,node,next.js,javascript",
        "relevance_if_match": "medium",
        "description": "TypeScript across the stack (Next.js, tRPC, Prisma) is the new default for startups.",
        "timeframe": "0-12 months",
    },
    {
        "trend": "Zero Trust Security Architecture",
        "keywords": "security,cloud,aws,azure,gcp,kubernetes",
        "relevance_if_match": "medium",
        "description": "Zero trust models are being mandated across enterprise and government sectors.",
        "timeframe": "6-18 months",
    },
    {
        "trend": "Green Software & Sustainability",
        "keywords": "cloud,aws,gcp,azure,devops",
        "relevance_if_match": "low",
        "description": "Carbon-aware computing and sustainable engineering practices are emerging as hiring differentiators.",
        "timeframe": "12-24 months",
    },
]


class TrendMapper(SubAgent):
    """Maps user skills to relevant emerging industry trends."""

    def __init__(self, ai_client=None):
        super().__init__(name="trend_mapper", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        skills: list[str] = context.get("skills", [])
        skill_set = {s.lower().strip() for s in skills}

        trends: list[dict[str, str]] = []

        for entry in _TREND_DB:
            keywords = {k.strip() for k in entry["keywords"].split(",")}
            overlap = skill_set & keywords
            if overlap:
                relevance = entry["relevance_if_match"]
            else:
                relevance = "low"

            trends.append({
                "trend": entry["trend"],
                "relevance": relevance,
                "description": entry["description"],
                "timeframe": entry["timeframe"],
                "matching_skills": sorted(overlap) if overlap else [],
            })

        # Sort by relevance (high > medium > low)
        relevance_order = {"high": 0, "medium": 1, "low": 2}
        trends.sort(key=lambda t: relevance_order.get(t["relevance"], 9))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "emerging_trends": trends[:5],
                "high_relevance_count": sum(1 for t in trends if t["relevance"] == "high"),
                "total_trends_analyzed": len(trends),
            },
            confidence=0.85,
        )
