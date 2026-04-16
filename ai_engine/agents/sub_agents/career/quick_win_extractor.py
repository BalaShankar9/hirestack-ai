"""
QuickWinExtractor — identifies immediately actionable improvement items.

Scans gap analysis, strengths, and user profile for things
achievable in < 1 week with high ROI:
  • Profile/CV tweaks
  • Certification quick-starts
  • Networking actions
  • Low-hanging skill gaps
  • Portfolio improvements

Pure deterministic — no LLM call.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class QuickWinExtractor(SubAgent):
    """Extracts high-ROI immediate actions from gap analysis data."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="quick_win_extractor", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        gap_analysis = context.get("gap_analysis", {})
        user_profile = context.get("user_profile", {})
        job_title = context.get("job_title", "Target Role")
        company = context.get("company", "Target Company")

        quick_wins: list[dict] = []

        # ── 1. Pass through existing quick wins ────────────────────
        for qw in gap_analysis.get("quick_wins", []):
            if isinstance(qw, str) and qw.strip():
                quick_wins.append({
                    "action": qw,
                    "category": "general",
                    "effort": "low",
                    "impact": "medium",
                })

        # ── 2. Profile/CV quick wins ───────────────────────────────
        summary = user_profile.get("summary") or ""
        if len(summary) < 50:
            quick_wins.append({
                "action": f"Write a compelling 2-3 sentence professional summary targeting {job_title}",
                "category": "profile",
                "effort": "low",
                "impact": "high",
            })

        skills = user_profile.get("skills", [])
        if len(skills) < 5:
            quick_wins.append({
                "action": "Add all relevant technical skills to your profile — aim for 15-20 skills",
                "category": "profile",
                "effort": "low",
                "impact": "high",
            })

        # Check for missing quantified achievements
        exp_texts = " ".join(
            e.get("description", "") for e in user_profile.get("experience", [])
        )
        has_metrics = bool(re.search(r"\d+[%$KkMm]|\d+x\s|from\s+\d+\s+to\s+\d+", exp_texts))
        if not has_metrics:
            quick_wins.append({
                "action": "Add quantified metrics to your top 5 experience bullet points (%, $, users, time saved)",
                "category": "profile",
                "effort": "low",
                "impact": "high",
            })

        # ── 3. Certification quick wins ────────────────────────────
        skill_gaps = gap_analysis.get("skill_gaps", [])
        cert_skills = set()
        for gap in skill_gaps:
            skill = (gap.get("skill") or "").lower()
            severity = gap.get("gap_severity", "moderate")
            # Cloud certs are often achievable quickly and high-value
            if any(cloud in skill for cloud in ["aws", "azure", "gcp", "google cloud"]):
                if severity in ("critical", "major"):
                    cert_skills.add(gap.get("skill", skill))

        for cs in list(cert_skills)[:2]:
            quick_wins.append({
                "action": f"Start {cs} certification prep — foundational cert achievable in 2-4 weeks",
                "category": "certification",
                "effort": "medium",
                "impact": "high",
            })

        # ── 4. Networking quick wins ───────────────────────────────
        quick_wins.append({
            "action": f"Connect with 3-5 people at {company} on LinkedIn with a personalised message",
            "category": "networking",
            "effort": "low",
            "impact": "high",
        })
        quick_wins.append({
            "action": f"Research {company}'s recent news, blog posts, and open-source projects",
            "category": "research",
            "effort": "low",
            "impact": "medium",
        })

        # ── 5. Minor skill gaps that close quickly ─────────────────
        for gap in skill_gaps:
            if gap.get("gap_severity") == "minor" and gap.get("current_level") not in ("none",):
                quick_wins.append({
                    "action": f"Brush up on {gap.get('skill', 'Unknown')}: watch a 1-2 hour refresher tutorial",
                    "category": "skill",
                    "effort": "low",
                    "impact": "medium",
                })
                if len(quick_wins) >= 12:
                    break

        # ── 6. Portfolio quick wins ────────────────────────────────
        projects = user_profile.get("projects", [])
        if not projects:
            quick_wins.append({
                "action": "Create a GitHub/portfolio showcasing 2-3 projects relevant to the target role",
                "category": "portfolio",
                "effort": "medium",
                "impact": "high",
            })
        else:
            # Check if projects have links
            has_links = any(p.get("url") or p.get("link") or p.get("github") for p in projects)
            if not has_links:
                quick_wins.append({
                    "action": "Add live links / GitHub URLs to your existing projects",
                    "category": "portfolio",
                    "effort": "low",
                    "impact": "medium",
                })

        # ── Deduplicate and sort ───────────────────────────────────
        seen_actions = set()
        unique_wins: list[dict] = []
        for qw in quick_wins:
            key = qw["action"][:60].lower()
            if key not in seen_actions:
                seen_actions.add(key)
                unique_wins.append(qw)

        # Sort: high impact first, then low effort
        impact_order = {"high": 0, "medium": 1, "low": 2}
        effort_order = {"low": 0, "medium": 1, "high": 2}
        unique_wins.sort(key=lambda x: (impact_order.get(x["impact"], 1), effort_order.get(x["effort"], 1)))

        confidence = min(0.8, 0.3 + 0.05 * len(unique_wins))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "quick_wins": unique_wins[:10],
                "quick_win_strings": [qw["action"] for qw in unique_wins[:8]],
                "categories": list({qw["category"] for qw in unique_wins}),
                "high_impact_count": sum(1 for qw in unique_wins if qw["impact"] == "high"),
            },
            confidence=confidence,
        )
