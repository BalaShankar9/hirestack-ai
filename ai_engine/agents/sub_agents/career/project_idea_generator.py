"""
ProjectIdeaGenerator — suggests portfolio projects that close multiple skill gaps.

Maps skill gaps to project templates, finds multi-gap projects
(maximum ROI per time invested), and estimates timelines.

Uses a curated template library of common project archetypes
by technology area.

Pure deterministic — no LLM call.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

# ── Project template library ───────────────────────────────────────
# Each template: (title, description, skills_demonstrated, difficulty, timeline, portfolio_value)
_PROJECT_TEMPLATES: list[dict[str, Any]] = [
    # Web / Full-stack
    {
        "tags": {"react", "javascript", "typescript", "html", "css", "frontend"},
        "title": "Interactive Dashboard App",
        "description": "Build a real-time data dashboard with charts, filters, and responsive design",
        "skills_demonstrated": ["React", "TypeScript", "API Integration", "Data Visualization"],
        "difficulty": "intermediate",
        "timeline": "2 weeks",
        "portfolio_value": "Shows frontend mastery, data handling, and polished UI",
    },
    {
        "tags": {"node.js", "express", "api", "rest", "backend", "javascript"},
        "title": "RESTful API with Auth & Rate Limiting",
        "description": "Build a production-grade REST API with JWT auth, role-based access, rate limiting, and OpenAPI docs",
        "skills_demonstrated": ["Node.js", "API Design", "Authentication", "Security"],
        "difficulty": "intermediate",
        "timeline": "2 weeks",
        "portfolio_value": "Demonstrates backend engineering fundamentals and security awareness",
    },
    {
        "tags": {"python", "django", "flask", "fastapi", "backend"},
        "title": "Task Management API with Background Jobs",
        "description": "Full CRUD API with background task processing, caching, and comprehensive test suite",
        "skills_demonstrated": ["Python", "API Design", "Testing", "Background Processing"],
        "difficulty": "intermediate",
        "timeline": "2 weeks",
        "portfolio_value": "Shows ability to build production-ready Python services",
    },
    {
        "tags": {"next.js", "nextjs", "react", "full-stack", "fullstack"},
        "title": "Full-Stack SaaS Starter",
        "description": "Build a Next.js app with auth, database, payments, and deployment pipeline",
        "skills_demonstrated": ["Next.js", "Full-Stack Development", "Database Design", "Deployment"],
        "difficulty": "advanced",
        "timeline": "3 weeks",
        "portfolio_value": "End-to-end product engineering — impresses at startups and scale-ups",
    },
    # Data & ML
    {
        "tags": {"python", "machine learning", "ml", "data science", "pandas", "scikit-learn"},
        "title": "ML Model with Production Pipeline",
        "description": "Train, evaluate, and deploy an ML model with data pipeline, experiment tracking, and API endpoint",
        "skills_demonstrated": ["Machine Learning", "Python", "Data Pipelines", "Model Deployment"],
        "difficulty": "advanced",
        "timeline": "3 weeks",
        "portfolio_value": "Demonstrates end-to-end ML engineering, not just Jupyter notebooks",
    },
    {
        "tags": {"sql", "database", "postgresql", "mysql", "data"},
        "title": "Data Analytics Dashboard",
        "description": "Design a normalized schema, write complex queries, and build a reporting dashboard",
        "skills_demonstrated": ["SQL", "Database Design", "Data Analysis", "Visualization"],
        "difficulty": "intermediate",
        "timeline": "2 weeks",
        "portfolio_value": "Shows strong data fundamentals — valued in every engineering role",
    },
    # Cloud & DevOps
    {
        "tags": {"aws", "cloud", "terraform", "infrastructure", "devops"},
        "title": "Cloud-Native Microservice Deployment",
        "description": "Deploy a multi-service app on AWS with IaC, CI/CD pipeline, monitoring, and auto-scaling",
        "skills_demonstrated": ["AWS", "Terraform", "CI/CD", "Monitoring"],
        "difficulty": "advanced",
        "timeline": "3 weeks",
        "portfolio_value": "Proves cloud and DevOps proficiency with real infrastructure",
    },
    {
        "tags": {"docker", "kubernetes", "containers", "k8s", "devops"},
        "title": "Containerised App with Kubernetes",
        "description": "Containerise a multi-service app with Docker, orchestrate with Kubernetes, add health checks and logging",
        "skills_demonstrated": ["Docker", "Kubernetes", "Container Orchestration", "Observability"],
        "difficulty": "advanced",
        "timeline": "3 weeks",
        "portfolio_value": "Container expertise is a must-have for modern backend roles",
    },
    {
        "tags": {"ci/cd", "github actions", "devops", "testing", "automation"},
        "title": "Comprehensive CI/CD Pipeline",
        "description": "Build a full CI/CD pipeline with linting, testing, security scanning, and automated deployment",
        "skills_demonstrated": ["CI/CD", "Testing", "Automation", "DevOps"],
        "difficulty": "intermediate",
        "timeline": "1 week",
        "portfolio_value": "Shows engineering maturity and commitment to quality",
    },
    # Mobile
    {
        "tags": {"react native", "mobile", "ios", "android", "flutter"},
        "title": "Cross-Platform Mobile App",
        "description": "Build a polished mobile app with navigation, offline support, and push notifications",
        "skills_demonstrated": ["Mobile Development", "Cross-Platform", "UX Design"],
        "difficulty": "intermediate",
        "timeline": "3 weeks",
        "portfolio_value": "Mobile experience is a strong differentiator for many teams",
    },
    # Systems
    {
        "tags": {"go", "golang", "systems", "concurrency", "rust"},
        "title": "Concurrent CLI Tool or Service",
        "description": "Build a performant CLI tool or microservice leveraging concurrency patterns",
        "skills_demonstrated": ["Go/Rust", "Concurrency", "Systems Design", "Performance"],
        "difficulty": "intermediate",
        "timeline": "2 weeks",
        "portfolio_value": "Demonstrates systems thinking and low-level engineering skill",
    },
    # Catch-all
    {
        "tags": {"open-source", "contribution", "github"},
        "title": "Open Source Contribution Sprint",
        "description": "Find 2-3 popular open-source projects in your target stack and submit meaningful PRs",
        "skills_demonstrated": ["Collaboration", "Code Reading", "Git Workflow", "Community"],
        "difficulty": "intermediate",
        "timeline": "2 weeks",
        "portfolio_value": "Nothing impresses like merged PRs in well-known projects",
    },
]


class ProjectIdeaGenerator(SubAgent):
    """Matches skill gaps to project templates for maximum portfolio ROI."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="project_idea_generator", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        gap_analysis = context.get("gap_analysis", {})
        job_title = context.get("job_title", "Target Role")

        skill_gaps = gap_analysis.get("skill_gaps", [])
        gap_skills = set()
        for g in skill_gaps:
            skill = (g.get("skill") or "").lower().strip()
            if skill:
                gap_skills.add(skill)

        if not gap_skills:
            # No specific gaps — suggest general portfolio projects
            fallback_tmpl = _PROJECT_TEMPLATES[-1]
            return SubAgentResult(
                agent_name=self.name,
                data={
                    "projects": [{
                        "title": fallback_tmpl["title"],
                        "description": fallback_tmpl["description"],
                        "skills_demonstrated": fallback_tmpl["skills_demonstrated"],
                        "difficulty": fallback_tmpl["difficulty"],
                        "timeline": fallback_tmpl["timeline"],
                        "portfolio_value": fallback_tmpl["portfolio_value"],
                    }],
                    "gap_coverage": {},
                    "gaps_covered": 0,
                    "gaps_total": 0,
                },
                confidence=0.3,
            )

        # ── Score each template by how many gaps it covers ────────
        scored: list[tuple[int, int, dict]] = []
        for tmpl in _PROJECT_TEMPLATES:
            tags = tmpl["tags"]
            overlap = len(gap_skills & tags)
            if overlap > 0:
                # Also count partial matches (e.g. "react native" gap matches "react" tag)
                for gs in gap_skills:
                    for tag in tags:
                        if gs in tag or tag in gs:
                            overlap += 0.5

                # Prefer intermediate over advanced if time is limited
                diff_penalty = 0 if tmpl["difficulty"] == "intermediate" else 1
                scored.append((int(overlap * 10), diff_penalty, tmpl))

        scored.sort(key=lambda x: (-x[0], x[1]))

        # Deduplicate by title, take top 3
        seen_titles = set()
        projects: list[dict] = []
        gap_coverage: dict[str, list[str]] = {}

        for _, _, tmpl in scored:
            if tmpl["title"] in seen_titles:
                continue
            seen_titles.add(tmpl["title"])

            project = {
                "title": tmpl["title"],
                "description": tmpl["description"],
                "skills_demonstrated": tmpl["skills_demonstrated"],
                "difficulty": tmpl["difficulty"],
                "timeline": tmpl["timeline"],
                "portfolio_value": tmpl["portfolio_value"],
            }
            projects.append(project)

            # Track which gaps this project covers
            for gs in gap_skills:
                if gs in tmpl["tags"] or any(gs in t or t in gs for t in tmpl["tags"]):
                    gap_coverage.setdefault(gs, []).append(tmpl["title"])

            if len(projects) >= 3:
                break

        # Always suggest open-source contributions if not already included
        if not any(p["title"] == "Open Source Contribution Sprint" for p in projects) and len(projects) < 3:
            projects.append({
                "title": "Open Source Contribution Sprint",
                "description": f"Contribute to popular {job_title.split()[0] if job_title else 'tech'}-related open-source projects",
                "skills_demonstrated": ["Collaboration", "Code Reading", "Git Workflow"],
                "difficulty": "intermediate",
                "timeline": "2 weeks",
                "portfolio_value": "Nothing impresses like merged PRs in well-known projects",
            })

        confidence = min(0.8, 0.3 + 0.15 * len(projects))

        return SubAgentResult(
            agent_name=self.name,
            data={
                "projects": projects[:3],
                "gap_coverage": gap_coverage,
                "gaps_covered": len(gap_coverage),
                "gaps_total": len(gap_skills),
            },
            confidence=confidence,
        )
