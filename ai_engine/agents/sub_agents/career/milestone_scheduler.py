"""
MilestoneScheduler — builds a 12-week improvement milestone timeline.

Takes the prioritised skills, strengths, and quick wins from gap analysis
and produces a phased timeline:
  Phase 1 (Weeks 1–2):  Foundation & Quick Wins
  Phase 2 (Weeks 3–6):  Core Skill Development
  Phase 3 (Weeks 7–10): Projects & Portfolio Building
  Phase 4 (Weeks 11–12): Interview Prep & Polish

Pure deterministic — no LLM call.
"""
from __future__ import annotations

import logging
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)


class MilestoneScheduler(SubAgent):
    """Builds a 12-week milestone schedule from gap analysis data."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="milestone_scheduler", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        gap_analysis = context.get("gap_analysis", {})
        job_title = context.get("job_title", "Target Role")
        company = context.get("company", "Target Company")

        skill_gaps = gap_analysis.get("skill_gaps", [])
        strengths = gap_analysis.get("strengths", [])
        quick_wins = gap_analysis.get("quick_wins", [])
        recommendations = gap_analysis.get("recommendations", [])
        interview_readiness = gap_analysis.get("interview_readiness", {})
        compatibility_score = gap_analysis.get("compatibility_score", 50)

        # Categorise skill gaps by severity
        critical_gaps = [g for g in skill_gaps if g.get("gap_severity") == "critical"]
        major_gaps = [g for g in skill_gaps if g.get("gap_severity") == "major"]
        moderate_gaps = [g for g in skill_gaps if g.get("gap_severity") in ("moderate", "minor")]

        milestones = []

        # ── PHASE 1: Foundation & Quick Wins (Weeks 1–2) ──────────
        phase1_tasks = []
        phase1_skills = []

        # Quick wins first
        for qw in quick_wins[:4]:
            if isinstance(qw, str):
                phase1_tasks.append(qw)

        # Profile optimisation
        phase1_tasks.append(f"Update CV/resume targeting {job_title} at {company}")
        phase1_tasks.append("Audit LinkedIn profile and align with target role keywords")

        # Leverage existing strengths
        for s in strengths[:2]:
            area = s.get("area", "")
            if area:
                phase1_skills.append(area)
                phase1_tasks.append(f"Document {area} achievements with quantified metrics")

        milestones.append({
            "week": 1,
            "title": "Foundation & Quick Wins",
            "description": f"Set up your learning environment and capture immediate wins. Score baseline: {compatibility_score}/100.",
            "tasks": phase1_tasks[:6],
            "skills_gained": phase1_skills[:3] or ["Profile Optimisation", "Self-Assessment"],
        })

        # ── PHASE 2: Core Skill Development (Weeks 3–6) ──────────
        # Week 3–4: Critical gaps
        if critical_gaps:
            crit_names = [g.get("skill", "Unknown") for g in critical_gaps[:3]]
            milestones.append({
                "week": 3,
                "title": "Critical Skill Gaps",
                "description": f"Focus on the most impactful gaps: {', '.join(crit_names)}.",
                "tasks": [
                    f"Begin structured learning for {g.get('skill', 'Unknown')}: {g.get('recommendation', 'Study fundamentals')}"
                    for g in critical_gaps[:3]
                ] + ["Complete at least one hands-on exercise per skill"],
                "skills_gained": crit_names,
            })

        # Week 5–6: Major + moderate gaps
        secondary_gaps = (major_gaps + moderate_gaps)[:4]
        if secondary_gaps:
            sec_names = [g.get("skill", "Unknown") for g in secondary_gaps[:3]]
            milestones.append({
                "week": 5,
                "title": "Expanded Skill Building",
                "description": f"Broaden capabilities: {', '.join(sec_names)}.",
                "tasks": [
                    f"Study {g.get('skill', 'Unknown')}: aim for {g.get('required_level', 'intermediate')} level"
                    for g in secondary_gaps[:3]
                ] + ["Review progress against benchmark — adjust pace if needed"],
                "skills_gained": sec_names,
            })

        # If no gaps at all, add a generic skill-up milestone
        if not critical_gaps and not secondary_gaps:
            milestones.append({
                "week": 3,
                "title": "Skill Deepening",
                "description": "Strengthen existing skills to go from good to exceptional.",
                "tasks": [
                    "Pick 2 skills to advance from intermediate to advanced",
                    "Complete an advanced tutorial or certification prep course",
                    "Write a technical blog post demonstrating depth of knowledge",
                ],
                "skills_gained": ["Advanced Proficiency"],
            })

        # ── PHASE 3: Projects & Portfolio (Weeks 7–10) ────────────
        project_recs = [r for r in recommendations if isinstance(r, dict) and r.get("category") == "project"]
        project_tasks = []
        project_skills = set()

        for pr in project_recs[:2]:
            project_tasks.append(f"Build: {pr.get('title', 'Portfolio Project')} — {pr.get('description', '')[:80]}")
            for item in pr.get("action_items", [])[:2]:
                project_tasks.append(item)

        if not project_tasks:
            project_tasks = [
                "Build a portfolio project combining your top 2-3 target skills",
                "Deploy project publicly (GitHub + live demo if applicable)",
                "Write a project README with architecture decisions and results",
            ]

        # Track which skills the projects cover
        for g in (critical_gaps + major_gaps)[:3]:
            project_skills.add(g.get("skill", ""))

        milestones.append({
            "week": 7,
            "title": "Portfolio Project Sprint",
            "description": "Apply learned skills in real projects that demonstrate capability.",
            "tasks": project_tasks[:5],
            "skills_gained": list(project_skills)[:4] or ["Applied Skills", "Portfolio Development"],
        })

        # ── PHASE 4: Interview Prep & Polish (Weeks 11–12) ────────
        prep_tasks = []

        prep_needed = interview_readiness.get("preparation_needed", [])
        for p in prep_needed[:3]:
            if isinstance(p, str):
                prep_tasks.append(p)

        prep_tasks.extend([
            f"Practice answering: 'Why do you want to work at {company}?'",
            "Run through 3 mock technical interview sessions",
            "Prepare STAR-format answers for your top 5 achievements",
            "Final review: update CV with new projects and skills gained",
        ])

        talking_points = interview_readiness.get("talking_points", [])
        interview_skills = ["Interview Technique", "Technical Communication"]
        if talking_points:
            interview_skills.append("Storytelling")

        milestones.append({
            "week": 11,
            "title": "Interview Prep & Final Polish",
            "description": f"Get interview-ready for {job_title}. Final profile and portfolio polish.",
            "tasks": prep_tasks[:6],
            "skills_gained": interview_skills,
        })

        # ── Build final schedule ──────────────────────────────────
        # Ensure milestones are sorted by week
        milestones.sort(key=lambda m: m["week"])

        # Cap at 6 milestones (as per the original schema limit)
        milestones = milestones[:6]

        confidence = min(0.8, 0.3 + 0.1 * len(skill_gaps))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "milestones": milestones,
                "total_duration": "12 weeks",
                "phases": [
                    {"name": "Foundation & Quick Wins", "weeks": "1–2"},
                    {"name": "Core Skill Development", "weeks": "3–6"},
                    {"name": "Projects & Portfolio", "weeks": "7–10"},
                    {"name": "Interview Prep & Polish", "weeks": "11–12"},
                ],
                "compatibility_baseline": compatibility_score,
                "target_score": min(100, compatibility_score + 25),
            },
            confidence=confidence,
        )
