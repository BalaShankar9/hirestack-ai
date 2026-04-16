"""
SkillPrioritizer — ranks skill gaps and builds a learning sequence.

Takes the skill_gaps from gap analysis (and optionally the full benchmark),
produces:
  • Prioritised skill list sorted by (severity × importance)
  • Prerequisite-aware learning order (foundational → advanced)
  • Per-skill time estimates
  • Skill clusters for parallel learning

Pure deterministic — no LLM call.
"""
from __future__ import annotations

import logging
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

_SEVERITY_SCORE = {"critical": 4, "major": 3, "moderate": 2, "minor": 1}
_IMPORTANCE_SCORE = {"critical": 3, "important": 2, "preferred": 1}
_LEVEL_INDEX = {"none": 0, "beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}

# Skills that are typically prerequisites for others
_PREREQUISITES: dict[str, list[str]] = {
    "react": ["javascript", "html", "css"],
    "next.js": ["react", "javascript"],
    "nextjs": ["react", "javascript"],
    "angular": ["typescript", "javascript", "html"],
    "vue": ["javascript", "html", "css"],
    "django": ["python"],
    "flask": ["python"],
    "fastapi": ["python"],
    "spring boot": ["java"],
    "spring": ["java"],
    "express": ["javascript", "node.js"],
    "nestjs": ["typescript", "node.js"],
    "graphql": ["javascript"],
    "redux": ["react", "javascript"],
    "terraform": ["cloud computing"],
    "kubernetes": ["docker", "containers"],
    "docker compose": ["docker"],
    "aws lambda": ["aws"],
    "aws cdk": ["aws", "typescript"],
    "machine learning": ["python", "statistics"],
    "deep learning": ["machine learning", "python"],
    "pytorch": ["python", "deep learning"],
    "tensorflow": ["python", "deep learning"],
    "pandas": ["python"],
    "pyspark": ["python", "spark"],
}

# Time estimates (weeks) to go from one level to the next
_LEVEL_UP_WEEKS = {
    (0, 1): 1,   # none → beginner
    (0, 2): 3,   # none → intermediate
    (0, 3): 8,   # none → advanced
    (0, 4): 16,  # none → expert
    (1, 2): 2,   # beginner → intermediate
    (1, 3): 6,   # beginner → advanced
    (1, 4): 14,  # beginner → expert
    (2, 3): 4,   # intermediate → advanced
    (2, 4): 10,  # intermediate → expert
    (3, 4): 6,   # advanced → expert
}


class SkillPrioritizer(SubAgent):
    """Ranks skill gaps and builds an optimal learning sequence."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="skill_prioritizer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        gap_analysis = context.get("gap_analysis", {})
        skill_gaps = gap_analysis.get("skill_gaps", [])
        benchmark = context.get("benchmark", {})

        if not skill_gaps:
            return SubAgentResult(
                agent_name=self.name,
                data={"prioritized_skills": [], "learning_order": [], "total_weeks": 0, "clusters": []},
                confidence=0.3,
            )

        # ── 1. Score and rank each gap ─────────────────────────────
        scored: list[dict] = []
        for gap in skill_gaps:
            skill = gap.get("skill", "")
            severity = _SEVERITY_SCORE.get(gap.get("gap_severity", "moderate"), 2)
            importance = _IMPORTANCE_SCORE.get(gap.get("importance_for_role", "important"), 2)
            priority_score = severity * importance

            cur = _LEVEL_INDEX.get(gap.get("current_level", "none"), 0)
            tgt = _LEVEL_INDEX.get(gap.get("required_level", "intermediate"), 2)
            weeks = _LEVEL_UP_WEEKS.get((cur, tgt), 4)

            scored.append({
                "skill": skill,
                "current_level": gap.get("current_level", "none"),
                "target_level": gap.get("required_level", "intermediate"),
                "gap_severity": gap.get("gap_severity", "moderate"),
                "importance": gap.get("importance_for_role", "important"),
                "priority_score": priority_score,
                "estimated_weeks": weeks,
                "recommendation": gap.get("recommendation", ""),
            })

        scored.sort(key=lambda x: x["priority_score"], reverse=True)

        # ── 2. Build prerequisite-aware learning order ──────────────
        learning_order = self._build_learning_order(scored)

        # ── 3. Cluster skills that can be learned in parallel ───────
        clusters = self._build_clusters(learning_order)

        total_weeks = sum(s["estimated_weeks"] for s in scored[:8])

        return SubAgentResult(
            agent_name=self.name,
            data={
                "prioritized_skills": scored[:12],
                "learning_order": learning_order,
                "clusters": clusters,
                "total_weeks": total_weeks,
                "top_3_focus": [s["skill"] for s in scored[:3]],
            },
            confidence=min(0.85, 0.4 + 0.05 * len(scored)),
        )

    def _build_learning_order(self, scored: list[dict]) -> list[dict]:
        """Topological sort of skills respecting prerequisites."""
        skill_names = {s["skill"].lower() for s in scored}
        ordered: list[dict] = []
        placed = set()

        for item in scored:
            skill_lower = item["skill"].lower()
            # Check if any prerequisite is also a gap (learn prereq first)
            prereqs = _PREREQUISITES.get(skill_lower, [])
            for prereq in prereqs:
                if prereq in skill_names and prereq not in placed:
                    # Find the prereq in scored list
                    for s in scored:
                        if s["skill"].lower() == prereq:
                            ordered.append({**s, "is_prerequisite": True})
                            placed.add(prereq)
                            break

            if skill_lower not in placed:
                ordered.append({**item, "is_prerequisite": False})
                placed.add(skill_lower)

        return ordered

    def _build_clusters(self, ordered: list[dict]) -> list[dict]:
        """Group skills into learning clusters (parallel batches)."""
        if not ordered:
            return []

        clusters = []
        current_cluster: list[str] = []
        current_weeks = 0

        for item in ordered:
            if item.get("is_prerequisite"):
                # Prerequisites start new clusters
                if current_cluster:
                    clusters.append({"skills": current_cluster, "estimated_weeks": current_weeks})
                current_cluster = [item["skill"]]
                current_weeks = item["estimated_weeks"]
            else:
                current_cluster.append(item["skill"])
                current_weeks = max(current_weeks, item["estimated_weeks"])

        if current_cluster:
            clusters.append({"skills": current_cluster, "estimated_weeks": current_weeks})

        return clusters
