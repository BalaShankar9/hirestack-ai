"""Shared helpers, constants, and conditional imports for the generation API."""
import json
import math
import re
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import HTTPException

from app.core.sanitize import sanitize_html
from app.core.circuit_breaker import CircuitBreakerOpen  # noqa: F401 – re-exported

from .schemas import PipelineRequest

logger = structlog.get_logger()

# ── Constants ──
MAX_JD_SIZE = 50_000       # 50KB — no JD is this long
MAX_RESUME_SIZE = 100_000  # 100KB — generous for parsed text
PIPELINE_TIMEOUT = 300     # 5 minutes — hard ceiling for the sync pipeline

# ── Conditional imports: PipelineRuntime ──
try:
    from app.services.pipeline_runtime import (
        PipelineRuntime as _PipelineRuntime,
        RuntimeConfig as _RuntimeConfig,
        ExecutionMode as _ExecutionMode,
        CollectorSink as _CollectorSink,
        SSESink as _SSESink,
        DatabaseSink as _DatabaseSink,
    )
    _RUNTIME_AVAILABLE = True
except ImportError:
    _PipelineRuntime = None  # type: ignore[assignment,misc]
    _RuntimeConfig = None  # type: ignore[assignment,misc]
    _ExecutionMode = None  # type: ignore[assignment,misc]
    _CollectorSink = None  # type: ignore[assignment,misc]
    _SSESink = None  # type: ignore[assignment,misc]
    _DatabaseSink = None  # type: ignore[assignment,misc]
    _RUNTIME_AVAILABLE = False

# ── Conditional imports: Agent Pipelines ──
try:
    from ai_engine.agents.pipelines import (  # noqa: F401
        resume_parse_pipeline,
        benchmark_pipeline,
        gap_analysis_pipeline,
        cv_generation_pipeline,
        cover_letter_pipeline,
        personal_statement_pipeline,
        portfolio_pipeline,
    )
    from ai_engine.agents.orchestrator import PipelineResult  # noqa: F401
    from ai_engine.agents.workflow_runtime import (  # noqa: F401
        WorkflowEventStore as _WorkflowEventStore,
        reconstruct_state as _reconstruct_state,
        get_completed_stages as _get_completed_stages,
        is_safely_resumable as _is_safely_resumable,
    )
    _AGENT_PIPELINES_AVAILABLE = True
except ImportError:
    _AGENT_PIPELINES_AVAILABLE = False

_PIPELINE_NAMES = ["cv_generation", "cover_letter", "personal_statement", "portfolio"]
_STAGE_ORDER = ["researcher", "drafter", "critic", "optimizer", "fact_checker", "validator"]


# ── Utility functions ──

def _sanitize_output_html(html: str) -> str:
    """Sanitize AI-generated HTML before sending to frontend (XSS prevention)."""
    if not html:
        return ""
    return sanitize_html(html)


def _extract_pipeline_html(payload: Any) -> str:
    """Return HTML from either raw pipeline content or a validator envelope."""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""

    html = payload.get("html")
    if isinstance(html, str):
        return html

    nested = payload.get("content")
    if isinstance(nested, str):
        return nested
    if isinstance(nested, dict):
        nested_html = nested.get("html")
        if isinstance(nested_html, str):
            return nested_html

    return ""


def _quality_score_from_scores(scores: Any) -> float:
    """Collapse per-dimension critic scores into a single user-facing score."""
    if not isinstance(scores, dict) or not scores:
        return 0.0

    overall = scores.get("overall")
    if isinstance(overall, (int, float)):
        return float(overall)

    numeric_scores = [float(value) for value in scores.values() if isinstance(value, (int, float))]
    if not numeric_scores:
        return 0.0
    return round(sum(numeric_scores) / len(numeric_scores), 1)


def _validation_issue_count(report: Any) -> int:
    if not isinstance(report, dict):
        return 0
    issues = report.get("issues")
    return len(issues) if isinstance(issues, list) else 0


def _build_evidence_summary(pipeline_result) -> Optional[Dict[str, Any]]:
    """Build a compact evidence summary from a PipelineResult for the frontend."""
    if not pipeline_result:
        return None
    ledger = getattr(pipeline_result, "evidence_ledger", None)
    citations = getattr(pipeline_result, "citations", None) or []
    if not ledger and not citations:
        return None

    tier_dist: Dict[str, int] = {}
    total_items = 0
    if isinstance(ledger, dict):
        items = ledger.get("items", [])
        total_items = len(items) if isinstance(items, list) else ledger.get("count", 0)
        for item in (items if isinstance(items, list) else []):
            tier = item.get("tier", "unknown") if isinstance(item, dict) else "unknown"
            tier_dist[tier] = tier_dist.get(tier, 0) + 1

    fabricated = sum(
        1 for c in citations
        if isinstance(c, dict) and c.get("classification") in ("fabricated", "unsupported")
    )
    unlinked = sum(
        1 for c in citations
        if isinstance(c, dict) and not c.get("evidence_ids")
    )

    return {
        "evidence_count": total_items,
        "tier_distribution": tier_dist,
        "citation_count": len(citations),
        "fabricated_count": fabricated,
        "unlinked_count": unlinked,
    }


def _build_company_intel_summary(company_intel: Dict[str, Any]) -> str:
    """Build a rich text summary from company intel for downstream document prompts.

    v2: Passes MUCH more data to doc generators — tech stack, hiring intel,
    interview prep, differentiators — so documents can be deeply tailored.
    """
    if not isinstance(company_intel, dict) or not company_intel:
        return ""

    strategy = company_intel.get("application_strategy", {})
    culture = company_intel.get("culture_and_values", {})
    tech = company_intel.get("tech_and_engineering", {})
    overview = company_intel.get("company_overview", {})
    hiring = company_intel.get("hiring_intelligence", {})
    products = company_intel.get("products_and_services", {})

    parts: List[str] = []

    # Company overview
    desc = overview.get("description") or overview.get("elevator_pitch")
    if isinstance(desc, str) and desc.strip():
        parts.append(f"Company: {desc.strip()}")
    industry = overview.get("industry")
    if isinstance(industry, str) and industry.strip() and industry.lower() != "unknown":
        sub = overview.get("sub_industry", "")
        parts.append(f"Industry: {industry}" + (f" ({sub})" if sub else ""))
    size = overview.get("size")
    stage = overview.get("stage")
    if size or stage:
        parts.append(f"Size/stage: {size or 'Unknown'} / {stage or 'Unknown'}")
    hq = overview.get("headquarters")
    if isinstance(hq, str) and hq.strip() and hq.lower() != "unknown":
        parts.append(f"HQ: {hq}")

    # Core values and mission
    core_values = culture.get("core_values")
    if isinstance(core_values, list) and core_values:
        parts.append(f"Company values: {', '.join(str(v) for v in core_values[:8])}")
    mission = culture.get("mission_statement")
    if isinstance(mission, str) and mission.strip():
        parts.append(f"Mission: {mission.strip()}")

    # Work style
    work_style = culture.get("work_style")
    if isinstance(work_style, str) and work_style.strip() and work_style.lower() != "unknown":
        parts.append(f"Work style: {work_style}")
    thrives = culture.get("what_kind_of_person_thrives")
    if isinstance(thrives, str) and thrives.strip():
        parts.append(f"Ideal candidate profile: {thrives}")

    # Tech stack (critical for tailored CVs/cover letters)
    tech_stack = tech.get("tech_stack") or tech.get("jd_tech_stack", {})
    if isinstance(tech_stack, list) and tech_stack:
        parts.append(f"Tech stack: {', '.join(str(t) for t in tech_stack[:20])}")
    elif isinstance(tech_stack, dict):
        all_tech = []
        for category_items in tech_stack.values():
            if isinstance(category_items, list):
                all_tech.extend(str(t) for t in category_items)
        if all_tech:
            parts.append(f"Tech stack: {', '.join(all_tech[:20])}")
    methodologies = tech.get("methodologies")
    if isinstance(methodologies, list) and methodologies:
        parts.append(f"Methodologies: {', '.join(str(m) for m in methodologies[:6])}")

    # GitHub presence
    gh = tech.get("github_stats", {})
    if isinstance(gh, dict) and gh.get("top_languages"):
        parts.append(f"GitHub languages: {', '.join(str(lang) for lang in gh['top_languages'][:8])}")
        if gh.get("notable_repos"):
            parts.append(f"Notable repos: {', '.join(str(r) for r in gh['notable_repos'][:5])}")

    # Products
    main_prods = products.get("main_products")
    if isinstance(main_prods, list) and main_prods:
        parts.append(f"Products: {', '.join(str(p) for p in main_prods[:5])}")
    target = products.get("target_market")
    if isinstance(target, str) and target.strip():
        parts.append(f"Target market: {target}")
    comp_adv = products.get("competitive_advantage")
    if isinstance(comp_adv, str) and comp_adv.strip():
        parts.append(f"Competitive advantage: {comp_adv}")

    # Hiring intelligence
    must_have = hiring.get("must_have_skills")
    if isinstance(must_have, list) and must_have:
        parts.append(f"Must-have skills: {', '.join(str(s) for s in must_have[:10])}")
    nice_have = hiring.get("nice_to_have_skills")
    if isinstance(nice_have, list) and nice_have:
        parts.append(f"Nice-to-have skills: {', '.join(str(s) for s in nice_have[:8])}")
    seniority = hiring.get("seniority_signals")
    if isinstance(seniority, dict):
        level = seniority.get("detected_level", "")
        if level:
            parts.append(f"Seniority target: {level}")
    elif isinstance(seniority, str) and seniority:
        parts.append(f"Seniority signals: {seniority}")
    impresses = hiring.get("what_impresses_interviewers")
    if isinstance(impresses, str) and impresses.strip():
        parts.append(f"What impresses interviewers: {impresses}")
    hidden = hiring.get("hidden_requirements")
    if isinstance(hidden, list) and hidden:
        parts.append(f"Hidden requirements: {'; '.join(str(h) for h in hidden[:4])}")

    # Recent developments & leadership
    recent = company_intel.get("recent_developments", {})
    if isinstance(recent, dict):
        news = recent.get("news_highlights", [])
        if isinstance(news, list) and news:
            parts.append(f"Recent news: {'; '.join(str(n) for n in news[:4])}")
        leaders = recent.get("leadership", [])
        if isinstance(leaders, list) and leaders:
            parts.append(f"Leadership: {'; '.join(str(ldr) for ldr in leaders[:5])}")
        direction = recent.get("strategic_direction")
        if isinstance(direction, str) and direction.strip():
            parts.append(f"Strategic direction: {direction}")

    # Market position
    market = company_intel.get("market_position", {})
    if isinstance(market, dict):
        comps = market.get("competitors", [])
        if isinstance(comps, list) and comps:
            parts.append(f"Competitors: {', '.join(str(c) for c in comps[:6])}")
        growth = market.get("growth_trajectory")
        if isinstance(growth, str) and growth.strip():
            parts.append(f"Growth trajectory: {growth}")

    # Application strategy
    keywords = strategy.get("keywords_to_use")
    if isinstance(keywords, list) and keywords:
        parts.append(f"Keywords to use: {', '.join(str(k) for k in keywords[:15])}")
    mentions = strategy.get("things_to_mention")
    if isinstance(mentions, list) and mentions:
        parts.append(f"Reference these: {'; '.join(str(m) for m in mentions[:5])}")
    avoid = strategy.get("things_to_avoid")
    if isinstance(avoid, list) and avoid:
        parts.append(f"Avoid: {'; '.join(str(a) for a in avoid[:5])}")
    hooks = strategy.get("cover_letter_hooks")
    if isinstance(hooks, list) and hooks:
        hook_texts = []
        for h in hooks[:3]:
            if isinstance(h, dict):
                hook_texts.append(h.get("hook", str(h)))
            else:
                hook_texts.append(str(h))
        parts.append(f"Cover letter hooks: {'; '.join(hook_texts)}")
    tone = strategy.get("tone")
    if isinstance(tone, str) and tone.strip():
        parts.append(f"Recommended tone: {tone}")
    differentiators = strategy.get("differentiator_opportunities") or strategy.get("differentiators")
    if isinstance(differentiators, list) and differentiators:
        parts.append(f"Differentiators: {'; '.join(str(d) for d in differentiators[:4])}")
    interview_topics = strategy.get("interview_prep_topics")
    if isinstance(interview_topics, list) and interview_topics:
        topic_texts = []
        for t in interview_topics[:6]:
            if isinstance(t, dict):
                topic_texts.append(t.get("topic", str(t)))
            else:
                topic_texts.append(str(t))
        parts.append(f"Interview prep: {', '.join(topic_texts)}")

    # Culture red flags (useful to avoid missteps)
    red_flags = culture.get("red_flags")
    if isinstance(red_flags, list) and red_flags:
        parts.append(f"Caution: {'; '.join(str(r) for r in red_flags[:3])}")

    return "\n".join(parts)


# ── Resilience: fallback builders ─────────────────────────────────────
#
# When external chains (Recon, Career Consultant) timeout, error out, or
# return empty payloads, we still have to give the user *something*
# meaningful in the workspace.  A blank "Intel" tab and a blank
# "Learning" tab are the second most demoralizing thing after a hard
# error — the user spent 90 seconds waiting for a generation that
# delivered nothing they can act on.  These builders synthesize a
# minimum-viable, JD-and-gap-derived payload so the workspace always
# renders structured content.  The `confidence` field stays "low" so
# the user can clearly see the difference vs a fully-researched run.


def _ensure_company_intel(
    company_intel: Optional[Dict[str, Any]],
    *,
    company_name: str,
    job_title: str,
    jd_text: str,
    keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Guarantee a renderable companyIntel object.

    If recon already produced a `company_overview`, return as-is. Otherwise
    derive a low-confidence intel summary from the JD + keywords so the
    Intel tab on the workspace renders something useful instead of an
    empty state.
    """
    intel = dict(company_intel) if isinstance(company_intel, dict) else {}

    has_overview = isinstance(intel.get("company_overview"), dict) and bool(intel["company_overview"])
    has_strategy = isinstance(intel.get("application_strategy"), dict) and bool(intel["application_strategy"])
    has_tech = (
        isinstance(intel.get("tech_and_engineering"), dict)
        and bool(intel["tech_and_engineering"])
    ) or (
        isinstance(intel.get("tech_and_tools"), dict)
        and bool(intel["tech_and_tools"])
    )

    if has_overview and has_strategy and has_tech:
        return intel

    jd_text = jd_text or ""
    keywords = list(keywords or [])

    # ── Derive overview from JD keywords + heuristics ──
    jd_lower = jd_text.lower()
    industry_hints = {
        "fintech": ["bank", "financ", "payment", "fintech", "trading", "lending"],
        "healthtech": ["health", "medical", "patient", "clinic", "pharma"],
        "edtech": ["learn", "student", "education", "course", "tutor"],
        "saas": ["saas", "subscription", "platform", "b2b"],
        "e-commerce": ["e-commerce", "ecommerce", "retail", "shopping", "marketplace"],
        "media": ["media", "content", "video", "stream", "publishing"],
        "developer tools": ["developer", "api", "sdk", "devtools", "infrastructure"],
    }
    industry = None
    for label, needles in industry_hints.items():
        if any(n in jd_lower for n in needles):
            industry = label
            break

    size_hints = {
        "Enterprise (1000+)": ["enterprise", "global team", "thousand", "fortune"],
        "Mid-market (200-1000)": ["scale-up", "scaling", "series c", "series d"],
        "Startup (10-200)": ["startup", "early-stage", "series a", "series b", "founding"],
    }
    size = None
    for label, needles in size_hints.items():
        if any(n in jd_lower for n in needles):
            size = label
            break

    # ── Tech stack derived from JD keywords ──
    tech_keywords = {kw for kw in keywords[:25] if kw and len(kw) <= 32}
    # heuristic: also extract obvious tech words from JD
    common_tech = [
        "python", "typescript", "javascript", "react", "node", "go", "rust",
        "kubernetes", "docker", "aws", "gcp", "azure", "postgres", "mongo",
        "kafka", "airflow", "spark", "tensorflow", "pytorch", "graphql",
    ]
    for tech in common_tech:
        if tech in jd_lower:
            tech_keywords.add(tech)

    # ── Application strategy derived from keywords ──
    strategy_keywords = list(tech_keywords)[:12] or keywords[:12]

    fallback: Dict[str, Any] = {
        "company_overview": intel.get("company_overview") or {
            "name": company_name or "Company",
            "industry": industry or "Not yet researched",
            "size": size or "Unknown",
            "description": (
                f"Intel was derived from the job description for the {job_title} role. "
                "Connect a company name and re-run for a richer profile."
            ),
        },
        "application_strategy": intel.get("application_strategy") or {
            "keywords_to_use": strategy_keywords,
            "things_to_mention": [
                f"Specific experience with {kw}" for kw in strategy_keywords[:4]
            ],
            "tone": "Professional, technically credible, outcomes-led",
            "interview_prep_topics": [
                f"Walk through a project where you used {kw}" for kw in strategy_keywords[:4]
            ],
        },
        "tech_and_engineering": intel.get("tech_and_engineering") or intel.get("tech_and_tools") or {
            "tech_stack": sorted(tech_keywords)[:18],
            "products": [],
        },
        "culture_and_values": intel.get("culture_and_values") or {},
        "recent_developments": intel.get("recent_developments") or intel.get("recent_news") or {},
        "market_position": intel.get("market_position") or intel.get("competitive_position") or {},
        "data_sources": intel.get("data_sources") or ["Job description analysis"],
        "confidence": intel.get("confidence") or "low",
        "data_completeness": intel.get("data_completeness") or {
            "website_data": False,
            "jd_analysis": True,
            "github_data": False,
            "careers_page": False,
        },
        "_synthesized_from_jd": not has_overview,
    }
    # Preserve any other top-level keys recon already produced
    for key, value in intel.items():
        fallback.setdefault(key, value)
    return fallback


def _ensure_learning_plan(
    learning_plan: Optional[Dict[str, Any]],
    *,
    gap_analysis: Optional[Dict[str, Any]],
    job_title: str,
    company: str,
) -> Dict[str, Any]:
    """Guarantee a renderable learningPlan object.

    If the consultant chain produced weekly milestones, return as-is.
    Otherwise synthesize a 4-week sprint plan from the user's skill gaps
    so the Learning tab on the workspace always has actionable content.
    """
    lp = dict(learning_plan) if isinstance(learning_plan, dict) else {}

    has_plan_items = isinstance(lp.get("plan"), list) and len(lp["plan"]) > 0
    has_focus = isinstance(lp.get("focus"), list) and len(lp["focus"]) > 0
    has_resources = isinstance(lp.get("resources"), list) and len(lp["resources"]) > 0

    if has_plan_items and has_focus and has_resources:
        return lp

    gap_analysis = gap_analysis or {}
    skill_gaps = gap_analysis.get("skill_gaps") or gap_analysis.get("gaps") or []
    quick_wins = gap_analysis.get("quick_wins") or []
    recommendations = gap_analysis.get("recommendations") or []

    # Extract gap skill names
    gap_skills: List[str] = []
    for g in skill_gaps:
        if isinstance(g, dict):
            name = g.get("skill") or g.get("dimension") or g.get("name")
            if name and name not in gap_skills:
                gap_skills.append(str(name))
        elif isinstance(g, str) and g not in gap_skills:
            gap_skills.append(g)

    if not gap_skills:
        # Last-resort generic plan keyed off the role
        gap_skills = [
            f"{job_title} fundamentals",
            f"{company} domain knowledge",
            "Interview storytelling",
            "Portfolio polish",
        ]

    focus = lp.get("focus") if has_focus else gap_skills[:6]

    plan_items: List[Dict[str, Any]] = []
    if has_plan_items:
        plan_items = lp["plan"]
    else:
        # Build a 4-week sprint, one focus area per week.
        for i, skill in enumerate(gap_skills[:4]):
            week_quick_wins = []
            if i == 0:
                # Pull quick_wins into week 1
                for qw in quick_wins[:3]:
                    if isinstance(qw, dict):
                        title = qw.get("title") or qw.get("description") or ""
                        if title:
                            week_quick_wins.append(str(title))
                    elif isinstance(qw, str):
                        week_quick_wins.append(qw)

            tasks = week_quick_wins or [
                f"Read 2-3 in-depth articles on {skill}",
                f"Build a small proof-of-concept that demonstrates {skill}",
                f"Document what you learned about {skill} in a public note or repo",
            ]
            outcomes = [
                f"Confident articulating {skill} in interviews",
                f"At least one shippable artefact that uses {skill}",
            ]
            plan_items.append({
                "week": i + 1,
                "theme": f"Week {i + 1}: {skill}",
                "outcomes": outcomes,
                "tasks": tasks,
                "goals": [f"Close the {skill} gap to interview-ready level"],
            })

    resources: List[Dict[str, Any]] = []
    if has_resources:
        resources = lp["resources"]
    else:
        # Synthesize generic but accurate resource pointers per gap.
        for skill in gap_skills[:6]:
            resources.append({
                "skill": skill,
                "title": f"Self-study path: {skill}",
                "provider": "Curated search",
                "timebox": "3-5 hours",
                "url": None,
            })

    project_recs = lp.get("projectRecommendations") or []
    if not project_recs and gap_skills:
        for skill in gap_skills[:3]:
            project_recs.append({
                "title": f"Mini-project: applied {skill}",
                "description": (
                    f"Build something small but real that exercises {skill} "
                    f"end-to-end. Aim for something you can demo in 2 minutes."
                ),
                "skills": [skill],
                "timeline": "1 week",
            })

    fallback_quick_wins = lp.get("quickWins") or []
    if not fallback_quick_wins and recommendations:
        fallback_quick_wins = [
            r.get("title") or r.get("description") or ""
            for r in recommendations[:5]
            if isinstance(r, dict)
        ]
        fallback_quick_wins = [t for t in fallback_quick_wins if t]

    return {
        "focus": focus,
        "plan": plan_items,
        "resources": resources,
        "projectRecommendations": project_recs,
        "quickWins": fallback_quick_wins,
        "_synthesized": not (has_plan_items and has_focus and has_resources),
    }


def _build_atlas_diagnostics(user_profile: Dict[str, Any], benchmark_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build normalized Atlas diagnostics for cross-route parity."""
    parse_confidence = 0.0
    parse_warnings: List[str] = []
    if isinstance(user_profile, dict):
        parse_confidence = float(user_profile.get("parse_confidence", 0.0) or 0.0)
        raw_warnings = user_profile.get("parse_warnings", [])
        if isinstance(raw_warnings, list):
            parse_warnings = [str(w) for w in raw_warnings[:10]]

    benchmark_quality_score = 0.0
    benchmark_quality_flags: List[str] = []
    if isinstance(benchmark_data, dict):
        benchmark_quality_score = float(benchmark_data.get("benchmark_quality_score", 0.0) or 0.0)
        raw_flags = benchmark_data.get("benchmark_quality_flags", [])
        if isinstance(raw_flags, list):
            benchmark_quality_flags = [str(f) for f in raw_flags[:10]]

    safe_mode = (
        parse_confidence < 0.5
        or bool(parse_warnings)
        or benchmark_quality_score < 0.5
        or bool(benchmark_quality_flags)
    )

    return {
        "parseConfidence": round(parse_confidence, 2),
        "parseWarnings": parse_warnings,
        "benchmarkQualityScore": round(benchmark_quality_score, 2),
        "benchmarkQualityFlags": benchmark_quality_flags,
        "safeMode": safe_mode,
    }


def _extract_retry_after_seconds(err: str) -> Optional[int]:
    """Best-effort parse of provider retry hints into whole seconds."""
    m = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", err, flags=re.IGNORECASE)
    if m:
        try:
            return max(1, int(math.ceil(float(m.group(1)))))
        except Exception:
            pass

    m = re.search(r"retryDelay'\s*:\s*'(\d+)s'", err)
    if m:
        try:
            return max(1, int(m.group(1)))
        except Exception:
            pass

    return None


def _classify_ai_error(exc: Exception) -> Optional[Dict[str, Any]]:
    """Classify an AI provider exception into a structured response for HTTP/SSE."""
    err = str(exc).lower()
    if (
        "api key not valid" in err
        or "api_key_invalid" in err
        or "api keys are not supported" in err
        or "expected oauth2 access token" in err
        or "credentials_missing" in err
    ):
        return {
            "code": 401,
            "message": (
                "Your Gemini credential isn't a valid API key for the Gemini API. "
                "Create a Google AI Studio API key (usually starts with 'AIza…') and set GEMINI_API_KEY, "
                "or configure Vertex AI by setting GEMINI_USE_VERTEXAI=true with OAuth credentials."
            ),
        }
    if "permission denied" in err or "permission_denied" in err:
        return {"code": 403, "message": "Gemini API permission denied. Check your API key and project settings."}
    if "not found" in err and ("model" in err or "404" in err):
        from app.core.config import settings as _s
        return {"code": 404, "message": f"The AI model '{_s.gemini_model}' was not found. Check your GEMINI_MODEL setting."}
    if "resource exhausted" in err or "rate limit" in err or "429" in err:
        return {
            "code": 429,
            "message": "AI rate limit reached. Please wait a moment and try again.",
            "retry_after_seconds": _extract_retry_after_seconds(str(exc)),
        }

    return None


def _validate_pipeline_input(req: PipelineRequest) -> None:
    """Reject oversized or empty inputs."""
    if not req.job_title.strip():
        raise HTTPException(status_code=400, detail="Job title is required")
    if not req.jd_text.strip():
        raise HTTPException(status_code=400, detail="Job description is required")
    if len(req.jd_text) > MAX_JD_SIZE:
        raise HTTPException(status_code=413, detail="Job description too large (max 50KB)")
    if len(req.resume_text) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=413, detail="Resume text too large (max 100KB)")


# ── SSE helpers ──

def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _agent_sse(pipeline_name: str, stage: str, status: str, latency_ms: int = 0, message: str = "", quality_scores: dict | None = None) -> str:
    """Emit an agent_status SSE event."""
    data = {
        "pipeline_name": pipeline_name,
        "stage": stage,
        "status": status,
        "latency_ms": latency_ms,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if quality_scores:
        data["quality_scores"] = quality_scores
    return f"event: agent_status\ndata: {json.dumps(data)}\n\n"


def _detail_sse(
    agent: str,
    message: str,
    status: str = "info",
    source: str | None = None,
    url: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Emit a structured detail event for terminal-like live logs."""
    data: Dict[str, Any] = {
        "agent": agent,
        "message": message,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if source:
        data["source"] = source
    if url:
        data["url"] = url
    if metadata:
        data["metadata"] = metadata
    return f"event: detail\ndata: {json.dumps(data)}\n\n"


# ── Response formatter ──

def _format_response(
    benchmark_data: Dict[str, Any],
    gap_analysis: Dict[str, Any],
    roadmap: Dict[str, Any],
    cv_html: str,
    cl_html: str,
    ps_html: str,
    portfolio_html: str,
    validation: Dict[str, Any],
    keywords: List[str],
    job_title: str,
    benchmark_cv_html: str = "",
    atlas_diagnostics: Optional[Dict[str, Any]] = None,
    company_intel: Optional[Dict[str, Any]] = None,
    company_name: str = "",
    jd_text: str = "",
) -> Dict[str, Any]:
    """Transform chain outputs into the frontend's expected data shapes."""

    # ── Benchmark ─────────────────────────────
    ideal_profile = benchmark_data.get("ideal_profile", {})
    ideal_skills = benchmark_data.get("ideal_skills", [])
    ideal_experience = benchmark_data.get("ideal_experience", [])

    summary_text = ""
    if isinstance(ideal_profile, dict):
        summary_text = ideal_profile.get("summary", "")
    if not summary_text:
        summary_text = f"AI-generated benchmark for {job_title}"

    rubric: List[str] = []
    for skill in ideal_skills[:10]:
        if isinstance(skill, dict):
            name = skill.get("name", "Unknown")
            level = skill.get("level", "required")
            importance = skill.get("importance", "important")
            rubric.append(f"{name} — {level} level ({importance})")

    benchmark = {
        "summary": summary_text,
        "keywords": keywords,
        "rubric": rubric,
        "idealProfile": ideal_profile if isinstance(ideal_profile, dict) else {},
        "idealSkills": ideal_skills,
        "idealExperience": ideal_experience,
        "scoringWeights": benchmark_data.get("scoring_weights", {}),
        "benchmarkCvHtml": _sanitize_output_html(benchmark_cv_html),
        "createdAt": None,
    }

    # ── Gaps ──────────────────────────────────
    compatibility = gap_analysis.get("compatibility_score", 50)
    skill_gaps = gap_analysis.get("skill_gaps", [])
    strengths_raw = gap_analysis.get("strengths", [])
    recommendations_raw = gap_analysis.get("recommendations", [])
    category_scores = gap_analysis.get("category_scores", {})
    quick_wins = gap_analysis.get("quick_wins", [])

    missing_kw = [
        g.get("skill", "") for g in skill_gaps if isinstance(g, dict) and g.get("skill")
    ]
    strength_labels = [
        s.get("area", s.get("description", ""))
        for s in strengths_raw
        if isinstance(s, dict)
    ]
    rec_labels = [
        r.get("title", r.get("description", ""))
        for r in recommendations_raw
        if isinstance(r, dict)
    ]

    gaps = {
        "missingKeywords": missing_kw,
        "strengths": strength_labels,
        "recommendations": rec_labels,
        "gaps": [
            {
                "dimension": g.get("skill", ""),
                "gap": f"{g.get('current_level', '?')} → {g.get('required_level', 'required')}",
                "severity": _map_severity(g.get("gap_severity", "moderate")),
                "suggestion": g.get("recommendation", ""),
            }
            for g in skill_gaps
            if isinstance(g, dict)
        ],
        "summary": gap_analysis.get("executive_summary", ""),
        "compatibility": compatibility,
        "categoryScores": category_scores,
        "quickWins": quick_wins,
        "interviewReadiness": gap_analysis.get("interview_readiness", {}),
    }

    # ── Learning Plan ─────────────────────────
    roadmap_data = roadmap.get("roadmap", {}) if isinstance(roadmap, dict) else {}
    milestones = roadmap_data.get("milestones", [])
    weekly_plans = roadmap_data.get("weekly_plans", [])
    skill_dev = roadmap_data.get("skill_development", [])
    project_recs = roadmap_data.get("project_recommendations", [])
    lr_resources = roadmap.get("learning_resources", []) if isinstance(roadmap, dict) else []
    quick_wins_roadmap = roadmap.get("quick_wins", []) if isinstance(roadmap, dict) else []

    plan_items = []
    if milestones:
        for i, ms in enumerate(milestones[:12]):
            if isinstance(ms, dict):
                plan_items.append({
                    "week": ms.get("week", i + 1),
                    "theme": ms.get("title", f"Week {i + 1}"),
                    "outcomes": ms.get("skills_gained", []),
                    "tasks": ms.get("tasks", []),
                    "goals": [ms.get("description", "")] if ms.get("description") else [],
                })
    elif weekly_plans:
        for i, wp in enumerate(weekly_plans[:12]):
            if isinstance(wp, dict):
                plan_items.append({
                    "week": wp.get("week", i + 1),
                    "theme": wp.get("theme", f"Week {i + 1}"),
                    "outcomes": wp.get("goals", []),
                    "tasks": [
                        a.get("activity", "")
                        for a in wp.get("activities", [])
                        if isinstance(a, dict)
                    ],
                    "goals": wp.get("goals", []),
                })

    learning_plan = {
        "focus": [
            s.get("skill", "")
            for s in skill_dev[:6]
            if isinstance(s, dict) and s.get("skill")
        ],
        "plan": plan_items,
        "resources": [
            {
                "skill": r.get("skill_covered", r.get("skill", "")),
                "title": r.get("title", ""),
                "provider": r.get("provider", ""),
                "timebox": r.get("duration", "Self-paced"),
                "url": r.get("url"),
            }
            for r in lr_resources[:12]
            if isinstance(r, dict)
        ],
        "projectRecommendations": [
            {
                "title": p.get("title", ""),
                "description": p.get("description", ""),
                "skills": p.get("skills_demonstrated", []),
                "timeline": p.get("timeline", ""),
            }
            for p in project_recs[:6]
            if isinstance(p, dict)
        ],
        "quickWins": quick_wins_roadmap,
    }

    # ── Scores ────────────────────────────────
    match_score = min(100, max(0, compatibility))
    ats_score = min(100, match_score + 15)
    scan_score = min(100, match_score + 10)

    scores = {
        "match": match_score,
        "atsReadiness": ats_score,
        "recruiterScan": scan_score,
        "evidenceStrength": 0,
        "topFix": _derive_top_fix(missing_kw),
        "benchmark": match_score,
        "gaps": max(0, 100 - len(missing_kw) * 8),
        "cv": min(100, match_score + 20),
        "coverLetter": min(100, match_score + 15),
        "overall": match_score,
    }

    scorecard = {
        "overall": scores["overall"],
        "dimensions": [
            {"name": "Match", "score": scores["match"], "feedback": f"{scores['match']}% keyword alignment"},
            {"name": "ATS Readiness", "score": scores["atsReadiness"], "feedback": f"{scores['atsReadiness']}% ATS-optimized"},
            {"name": "Recruiter Scan", "score": scores["recruiterScan"], "feedback": f"{scores['recruiterScan']}% scan-friendly"},
            {"name": "Evidence Strength", "score": scores["evidenceStrength"], "feedback": "Add evidence to boost this score"},
        ],
        "match": scores["match"],
        "atsReadiness": scores["atsReadiness"],
        "recruiterScan": scores["recruiterScan"],
        "evidenceStrength": scores["evidenceStrength"],
        "topFix": scores["topFix"],
        "updatedAt": None,
    }

    # ── Resilience: never let Learning or Intel render as empty ──
    learning_plan = _ensure_learning_plan(
        learning_plan,
        gap_analysis=gap_analysis,
        job_title=job_title,
        company=company_name,
    )
    company_intel_out = _ensure_company_intel(
        company_intel,
        company_name=company_name,
        job_title=job_title,
        jd_text=jd_text,
        keywords=keywords,
    )

    return {
        "benchmark": benchmark,
        "gaps": gaps,
        "learningPlan": learning_plan,
        "companyIntel": company_intel_out,
        "atlas": atlas_diagnostics or {},
        "cvHtml": _sanitize_output_html(cv_html),
        "coverLetterHtml": _sanitize_output_html(cl_html),
        "personalStatementHtml": _sanitize_output_html(ps_html),
        "portfolioHtml": _sanitize_output_html(portfolio_html),
        "validation": validation,
        "scorecard": scorecard,
        "scores": scores,
    }


def _map_severity(severity: str) -> str:
    return {"critical": "high", "major": "high", "moderate": "medium", "minor": "low"}.get(
        severity, "medium"
    )


def _derive_top_fix(missing: List[str]) -> str:
    if missing:
        return f'Add proof for "{missing[0]}" — include a concrete project or measurable result.'
    return "Your profile is strong! Polish your summary and lead with your best proof point."


def _extract_keywords_from_jd(jd_text: str) -> List[str]:
    """Simple keyword extraction fallback."""
    KNOWN = {
        "javascript", "typescript", "python", "java", "go", "rust", "ruby", "php",
        "swift", "kotlin", "react", "angular", "vue", "svelte", "next", "nuxt",
        "node", "express", "django", "flask", "fastapi", "spring",
        "sql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
        "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
        "git", "github", "gitlab", "jenkins", "ci", "cd",
        "graphql", "rest", "grpc", "microservices",
        "tailwind", "css", "html", "sass",
        "jest", "playwright", "cypress", "selenium",
        "figma", "agile", "scrum", "kanban",
        "machine", "learning", "ai", "ml", "nlp",
        "linux", "bash", "shell",
    }
    words = jd_text.lower().split()
    found, seen = [], set()
    for w in words:
        clean = w.strip(".,;:!?()[]{}\"'").lower()
        if clean in KNOWN and clean not in seen:
            seen.add(clean)
            found.append(clean)
    return found[:25]


# ── Critic-gate-aware job finalisation ──
# Single source of truth for translating the v4 ValidationCritic output
# into a persisted generation_jobs row update. All completion paths
# (durable job runner, agent pipeline path, future shared finaliser)
# MUST go through this helper. Hand-rolling the {status, message,
# finished_at, validation block, etc.} dict in multiple places is the
# drift-prone pattern this helper exists to retire.
def finalize_job_status_payload(
    result: Dict[str, Any] | None,
    *,
    total_steps: int,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the canonical generation_jobs UPDATE payload for a successful
    pipeline run, honouring the critic gate stamped onto ``result``.

    - When ``result["validation"]["passed"]`` is False the persisted
      status is ``"succeeded_with_warnings"`` and the human-readable
      message surfaces the error / warning counts.
    - When validation is missing or passed the status is ``"succeeded"``.
    - Caller may pass ``extra_fields`` to merge in path-specific keys
      (e.g. ``generation_plan``); these never override the critical
      status / message / finished_at fields produced by this helper.

    The helper is pure: no I/O, no logging, no raising. It exists so
    every finalisation site has the same lying-state-prevention logic.
    """
    validation_meta = (result or {}).get("validation") or {}
    validation_passed = validation_meta.get("passed", True)
    error_count = int(validation_meta.get("error_count", 0) or 0)
    warning_count = int(validation_meta.get("warning_count", 0) or 0)

    final_status = "succeeded" if validation_passed else "succeeded_with_warnings"
    final_message = (
        "Generation complete."
        if validation_passed
        else (
            f"Generation complete with validation warnings "
            f"({error_count} errors, {warning_count} warnings)."
        )
    )

    payload: Dict[str, Any] = {
        "status": final_status,
        "progress": 100,
        "phase": "complete",
        "message": final_message,
        "current_agent": "nova",
        "completed_steps": total_steps,
        "total_steps": total_steps,
        "active_sources_count": 0,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    # Merge in caller-provided extras WITHOUT letting them override the
    # critical status / message / finished_at semantics.
    if extra_fields:
        for key, value in extra_fields.items():
            if key in {"status", "message", "finished_at", "progress"}:
                continue
            payload[key] = value
    return payload


# Set of statuses that mean "the job has reached a terminal state".
# Used for guards that prevent late-arriving stage completions from
# overwriting an already-finalised job (race protection).
TERMINAL_JOB_STATUSES: frozenset[str] = frozenset(
    {"succeeded", "succeeded_with_warnings", "failed", "cancelled"}
)
