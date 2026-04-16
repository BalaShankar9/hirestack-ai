"""
JDIntelAgent — deep job description intelligence extraction.

Goes far beyond keyword matching: extracts hidden requirements, team dynamics,
seniority signals, compensation clues, red flags, culture markers, and
interview preparation topics from the raw job description text.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import structlog

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.jd")

# Tech keywords by category
_TECH_CATEGORIES = {
    "languages": [
        "python", "javascript", "typescript", "java", "go", "golang", "rust",
        "c#", "c++", "ruby", "php", "scala", "kotlin", "swift", "dart",
        "elixir", "clojure", "haskell", "r", "julia", "lua", "perl",
    ],
    "frontend": [
        "react", "angular", "vue", "svelte", "next.js", "nuxt", "remix",
        "tailwind", "bootstrap", "material ui", "chakra", "shadcn",
    ],
    "backend": [
        "node.js", "express", "fastapi", "django", "flask", "spring boot",
        "rails", "laravel", ".net", "asp.net", "nestjs", "gin", "fiber",
    ],
    "data": [
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "kafka",
        "rabbitmq", "dynamodb", "cassandra", "neo4j", "clickhouse", "snowflake",
        "bigquery", "redshift", "databricks", "spark", "airflow", "dbt",
    ],
    "cloud": [
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "cloudflare", "vercel", "netlify", "heroku", "digitalocean",
    ],
    "ai_ml": [
        "machine learning", "deep learning", "nlp", "llm", "computer vision",
        "pytorch", "tensorflow", "hugging face", "langchain", "openai",
        "transformers", "rag", "fine-tuning", "embedding",
    ],
    "devops": [
        "ci/cd", "jenkins", "github actions", "circleci", "gitlab ci",
        "argocd", "datadog", "grafana", "prometheus", "new relic",
        "pagerduty", "sentry", "observability",
    ],
}

_SENIORITY_MARKERS = {
    "junior": ["junior", "entry-level", "entry level", "graduate", "associate", "0-2 years", "1-2 years", "new grad"],
    "mid": ["mid-level", "mid level", "3-5 years", "2-4 years", "3+ years"],
    "senior": ["senior", "5+ years", "5-7 years", "7+ years", "8+ years", "lead", "staff", "principal"],
    "leadership": ["manager", "director", "vp", "head of", "chief", "cto", "cio"],
}


class JDIntelAgent(SubAgent):
    """Deep JD analysis — hidden requirements, culture signals, interview prep topics."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="jd_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        jd_text = context.get("jd_text", "")
        job_title = context.get("job_title", "")
        on_event = context.get("on_event")

        if not jd_text:
            return SubAgentResult(agent_name=self.name, error="No jd_text provided")

        if on_event:
            await _emit(on_event, "Analyzing job description for deep signals…", "running", "job_description")

        lower = jd_text.lower()

        # 1. Tech stack extraction (categorized)
        tech_stack: dict[str, list[str]] = {}
        all_tech: list[str] = []
        for category, keywords in _TECH_CATEGORIES.items():
            found = [k for k in keywords if k in lower]
            if found:
                tech_stack[category] = found
                all_tech.extend(found)

        # 2. Seniority analysis
        seniority = "mid"  # default
        seniority_signals: list[str] = []
        for level, markers in _SENIORITY_MARKERS.items():
            for marker in markers:
                if marker in lower:
                    seniority = level
                    seniority_signals.append(marker)

        # 3. Experience requirements
        exp_match = re.search(r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience', lower)
        years_required = int(exp_match.group(1)) if exp_match else None

        # 4. Salary/comp signals
        salary_match = re.search(
            r'[\$£€]\s*(\d{2,3})[,.]?\d{0,3}\s*[-–to]+\s*[\$£€]?\s*(\d{2,3})[,.]?\d{0,3}',
            jd_text,
        )
        salary_range = salary_match.group(0) if salary_match else None
        has_equity = any(w in lower for w in ["equity", "stock options", "rsu", "shares", "vesting"])
        has_bonus = "bonus" in lower

        # 5. Work model
        work_model = "unknown"
        if "remote" in lower:
            work_model = "fully remote" if ("fully remote" in lower or "100% remote" in lower) else "remote-friendly"
        elif "hybrid" in lower:
            work_model = "hybrid"
        elif "on-site" in lower or "onsite" in lower or "in-office" in lower:
            work_model = "on-site"

        # 6. Culture signals
        culture_signals: list[str] = []
        culture_map = {
            "fast-paced": ["fast-paced", "fast paced", "move fast", "rapidly growing", "high-growth"],
            "collaborative": ["collaborative", "cross-functional", "teamwork", "pair programming"],
            "autonomous": ["autonomous", "self-directed", "self-starter", "independent"],
            "innovative": ["innovative", "cutting-edge", "cutting edge", "state-of-the-art"],
            "mission-driven": ["mission-driven", "mission driven", "impact", "making a difference"],
            "quality-focused": ["quality", "excellence", "best practices", "high standards"],
            "learning-culture": ["learning", "growth mindset", "continuous improvement", "mentorship"],
            "diverse-inclusive": ["diversity", "inclusion", "belonging", "equitable"],
        }
        for signal, markers in culture_map.items():
            if any(m in lower for m in markers):
                culture_signals.append(signal)

        # 7. Red flags
        red_flags: list[str] = []
        red_flag_checks = {
            "Vague responsibilities": not any(w in lower for w in ["responsible for", "you will", "responsibilities"]),
            "No benefits mentioned": not any(w in lower for w in ["benefits", "health", "insurance", "pto", "vacation"]),
            "Unrealistic requirements": years_required is not None and years_required > 10,
            "Wear many hats signal": any(w in lower for w in ["wear many hats", "jack of all trades", "do-it-all"]),
            "High turnover language": any(w in lower for w in ["replacements", "immediate start", "urgently"]),
            "Unpaid overtime hints": any(w in lower for w in ["above and beyond", "whatever it takes", "hustle"]),
        }
        for flag, detected in red_flag_checks.items():
            if detected:
                red_flags.append(flag)

        # 8. Team/org structure clues
        team_clues: list[str] = []
        if "squad" in lower or "tribe" in lower:
            team_clues.append("Spotify-model (squads/tribes)")
        if "pod" in lower:
            team_clues.append("Pod-based teams")
        if "agile" in lower or "scrum" in lower:
            team_clues.append("Agile/Scrum")
        if "kanban" in lower:
            team_clues.append("Kanban")
        if "product team" in lower or "cross-functional" in lower:
            team_clues.append("Product-oriented teams")

        # 9. Must-have vs nice-to-have classification
        must_haves: list[str] = []
        nice_to_haves: list[str] = []
        # Simple heuristic: text after "required"/"must have" vs "preferred"/"nice to have"
        required_section = re.search(r'(?:required|must have|requirements|qualifications)[:\s]*(.*?)(?:preferred|nice to have|bonus|plus|$)', lower, re.DOTALL)
        preferred_section = re.search(r'(?:preferred|nice to have|bonus|plus|desired)[:\s]*(.*?)(?:$)', lower, re.DOTALL)

        if required_section:
            req_text = required_section.group(1)
            for tech in all_tech:
                if tech in req_text:
                    must_haves.append(tech)
        if preferred_section:
            pref_text = preferred_section.group(1)
            for tech in all_tech:
                if tech in pref_text and tech not in must_haves:
                    nice_to_haves.append(tech)

        # Anything not classified goes to must_haves by default
        for tech in all_tech:
            if tech not in must_haves and tech not in nice_to_haves:
                must_haves.append(tech)

        # 10. Interview prep topics
        interview_topics: list[str] = []
        if tech_stack.get("ai_ml"):
            interview_topics.append("ML system design and model evaluation")
        if tech_stack.get("cloud"):
            interview_topics.append("Cloud architecture and scalability")
        if "system design" in lower:
            interview_topics.append("System design interviews")
        if tech_stack.get("data"):
            interview_topics.append("Database design and optimization")
        if "leadership" in lower or "mentoring" in lower:
            interview_topics.append("Leadership and mentoring examples")
        if culture_signals:
            interview_topics.append(f"Culture fit: {', '.join(culture_signals[:3])}")

        if on_event:
            await _emit(
                on_event,
                f"JD analysis complete: {len(all_tech)} tech signals, {seniority} level, {len(culture_signals)} culture markers.",
                "completed", "job_description",
                metadata={"tech_count": len(all_tech), "seniority": seniority, "red_flags": len(red_flags)},
            )

        # Build evidence
        evidence_items: list[dict] = []
        for tech in must_haves[:10]:
            evidence_items.append({
                "fact": f"JD requires: {tech}",
                "source": "jd:must_have",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })
        for signal in culture_signals:
            evidence_items.append({
                "fact": f"Culture signal: {signal}",
                "source": "jd:culture",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })
        for flag in red_flags:
            evidence_items.append({
                "fact": f"Red flag: {flag}",
                "source": "jd:red_flags",
                "tier": "INFERRED",
                "sub_agent": self.name,
            })

        confidence = min(0.95, 0.5 + len(all_tech) * 0.02 + len(culture_signals) * 0.05)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "tech_stack": tech_stack,
                "all_technologies": all_tech,
                "must_have_skills": must_haves,
                "nice_to_have_skills": nice_to_haves,
                "seniority": seniority,
                "seniority_signals": seniority_signals,
                "years_required": years_required,
                "salary_range": salary_range,
                "has_equity": has_equity,
                "has_bonus": has_bonus,
                "work_model": work_model,
                "culture_signals": culture_signals,
                "red_flags": red_flags,
                "team_structure": team_clues,
                "interview_topics": interview_topics,
                "jd_length": len(jd_text),
            },
            evidence_items=evidence_items,
            confidence=confidence,
        )


async def _emit(callback, message, status, source, url=None, metadata=None):
    payload: dict[str, Any] = {"stage": "recon", "status": status, "message": message, "source": source}
    if url:
        payload["url"] = url
    if metadata:
        payload["metadata"] = metadata
    try:
        maybe = callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass
