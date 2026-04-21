"""
Agent Tool Registry — callable tools for agent-driven retrieval and analysis.

Each tool is an async callable with a name, description, and parameter schema.
Agents select tools based on their current state and call them in a loop
until their coverage/confidence threshold is met.

v2: Improved claim extraction, fuzzy keyword matching, better readability,
    n-gram keyword extraction, and expanded stopword list.
v3: External tools (web search, DB user history), LLM-driven tool selection,
    and ToolPlan dataclass for autonomous planning loop.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Awaitable, Optional


@dataclass
class AgentTool:
    """A callable tool that an agent can invoke."""

    name: str
    description: str
    parameters: dict  # JSON-schema-like description for the LLM
    fn: Callable[..., Awaitable[dict]]

    async def execute(self, **kwargs: Any) -> dict:
        return await self.fn(**kwargs)


@dataclass
class ToolCall:
    """A single tool invocation planned by the LLM."""
    tool_name: str
    arguments: dict[str, Any]
    reasoning: str = ""


@dataclass
class ToolPlan:
    """LLM-generated plan for which tools to call next."""
    calls: list[ToolCall] = field(default_factory=list)
    done: bool = False
    coverage_estimate: float = 0.0
    reasoning: str = ""


class ToolRegistry:
    """Registry of tools available to agents."""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[AgentTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[AgentTool]:
        return list(self._tools.values())

    def describe_for_llm(self) -> str:
        """Return a text description of all tools for inclusion in prompts."""
        lines: list[str] = []
        for tool in self._tools.values():
            params = ", ".join(
                f"{k}: {v.get('type', 'any')}"
                for k, v in tool.parameters.get("properties", {}).items()
            )
            lines.append(f"- **{tool.name}**({params}): {tool.description}")
        return "\n".join(lines)

    def describe_as_json(self) -> list[dict]:
        """Return tool descriptions as structured JSON for the LLM."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def select_and_execute(
        self,
        ai_client: Any,
        context: str,
        working_memory: dict,
        system_prompt: str = "",
    ) -> ToolPlan:
        """Ask the LLM which tools to call next, then execute them.

        Returns a ToolPlan with results. The LLM sees full tool schemas,
        current working memory, and decides what's still needed.
        """
        # Give LLM complete tool schemas (not just text descriptions)
        tool_schemas = self.describe_as_json()
        available_tool_names = [t.name for t in self._tools.values()]

        prompt = (
            "You are a research planner. Based on the context and what you already know, "
            "decide which tools (if any) to call next to fill knowledge gaps.\n\n"
            f"## Available Tools (with full parameter schemas)\n"
            f"{json.dumps(tool_schemas, indent=2)}\n\n"
            f"## Context\n{context[:2000]}\n\n"
            f"## Working Memory (already gathered)\n"
            f"{json.dumps({k: _summarize(v) for k, v in working_memory.items()}, indent=2)[:2000]}\n\n"
            "Respond with JSON:\n"
            '{"calls": [{"tool_name": "...", "arguments": {"param_name": "value"}, '
            '"reasoning": "why this tool is needed"}], '
            '"done": true/false, "coverage_estimate": 0.0-1.0, '
            '"reasoning": "overall reasoning"}\n\n'
            "IMPORTANT:\n"
            "- Each call MUST include an 'arguments' object with the required parameters from the tool schema.\n"
            "- Set done=true if working memory is sufficient for the task.\n"
            "- Do NOT call tools whose results are already in working memory.\n"
            f"- Only use tool names from: {available_tool_names}"
        )

        try:
            result = await ai_client.complete_json(
                prompt=prompt,
                system=system_prompt or "You are a tool-selection planner.",
                max_tokens=500,
                temperature=0.1,
                task_type="structured_output",
            )
        except Exception:
            return ToolPlan(done=True, coverage_estimate=0.5, reasoning="LLM planning failed, proceeding with available data")

        calls = []
        for call_spec in result.get("calls", []):
            name = call_spec.get("tool_name", "")
            if name in self._tools:
                calls.append(ToolCall(
                    tool_name=name,
                    arguments=call_spec.get("arguments", {}),
                    reasoning=call_spec.get("reasoning", ""),
                ))

        return ToolPlan(
            calls=calls,
            done=result.get("done", len(calls) == 0),
            coverage_estimate=float(result.get("coverage_estimate", 0.5)),
            reasoning=result.get("reasoning", ""),
        )


def _summarize(value: Any) -> Any:
    """Summarize a value for working memory display (truncate large dicts)."""
    if isinstance(value, dict):
        if "error" in value:
            return {"error": value["error"]}
        keys = list(value.keys())
        if len(keys) > 5:
            return {k: "..." for k in keys[:5]}
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "..."
    return value


# ═══════════════════════════════════════════════════════════════════════
#  Built-in tools
# ═══════════════════════════════════════════════════════════════════════


async def _parse_jd(jd_text: str, **_: Any) -> dict:
    """Extract structured fields from a job description (deterministic).

    v2: expanded stopwords, bigram extraction for multi-word skills,
    and requirement-level classification (must-have vs nice-to-have).
    """
    text = jd_text or ""
    # Extract single-word keywords by frequency
    words = re.findall(r"\b[A-Za-z][A-Za-z+#./\-]{1,30}\b", text)
    freq: dict[str, int] = {}
    stop_words = _STOP_WORDS
    for w in words:
        low = w.lower()
        if low not in stop_words and len(low) > 2:
            freq[low] = freq.get(low, 0) + 1

    # Extract multi-word technical terms (bigrams like "machine learning")
    bigrams = _extract_technical_bigrams(text)
    for bg, count in bigrams.items():
        freq[bg] = freq.get(bg, 0) + count

    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:30]

    # Classify keywords by requirement section
    must_have, nice_to_have = _classify_requirements(text, {k for k, _ in sorted_kw})

    return {
        "keyword_frequency": {k: v for k, v in sorted_kw},
        "total_words": len(words),
        "top_keywords": [k for k, _ in sorted_kw[:15]],
        "must_have_keywords": sorted(must_have)[:15],
        "nice_to_have_keywords": sorted(nice_to_have)[:10],
    }


# Expanded stopword set for career domain
_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "are", "you", "will",
    "our", "have", "from", "your", "can", "not", "but", "all", "been",
    "has", "their", "what", "who", "which", "into", "about", "more",
    "than", "its", "also", "should", "would", "could", "may", "must",
    "work", "working", "looking", "join", "team", "role", "company",
    "experience", "strong", "ability", "skills", "including", "such",
    "well", "etc", "other", "like", "using", "used", "use", "new",
    "based", "across", "within", "between", "both", "each", "every",
    "any", "some", "being", "how", "when", "where", "why", "make",
    "take", "get", "set", "help", "need", "want", "know", "come",
    "part", "time", "year", "years", "day", "way", "per", "via",
    "apply", "please", "asap", "competitive", "salary", "location",
    "fast-paced", "team player", "self-starter", "detail-oriented",
    "excellent", "communication", "opportunities", "opportunity",
    "preferred", "required", "requirements", "responsibilities",
})


def _extract_technical_bigrams(text: str) -> dict[str, int]:
    """Extract common multi-word technical terms."""
    known_bigrams = {
        "machine learning", "deep learning", "data science", "data engineering",
        "full stack", "full-stack", "front end", "front-end", "back end", "back-end",
        "natural language", "computer vision", "distributed systems",
        "event driven", "event-driven", "real time", "real-time",
        "cloud native", "cloud-native", "open source", "open-source",
        "product management", "project management", "cross functional",
        "cross-functional", "ci/cd", "a/b testing", "unit testing",
        "system design", "api design", "code review", "code reviews",
        "product led", "product-led", "data driven", "data-driven",
    }
    text_lower = text.lower()
    found: dict[str, int] = {}
    for bg in known_bigrams:
        count = text_lower.count(bg)
        if count > 0:
            # Normalize hyphens
            key = bg.replace("-", " ").replace("/", "/")
            found[key] = found.get(key, 0) + count
    return found


def _classify_requirements(text: str, keywords: set[str]) -> tuple[set[str], set[str]]:
    """Split keywords into must-have vs nice-to-have based on JD section headers."""
    must_have: set[str] = set()
    nice_to_have: set[str] = set()

    lines = text.split("\n")
    section = "must"  # Default section

    for line in lines:
        line_lower = line.lower().strip()
        # Detect section headers
        if any(h in line_lower for h in ("requirements", "must have", "required", "qualifications", "what you")):
            section = "must"
        elif any(h in line_lower for h in ("nice to have", "preferred", "bonus", "plus", "ideal")):
            section = "nice"

        for kw in keywords:
            if kw in line_lower:
                if section == "must":
                    must_have.add(kw)
                else:
                    nice_to_have.add(kw)

    # Keywords not in any section default to must-have
    unclassified = keywords - must_have - nice_to_have
    must_have.update(unclassified)

    return must_have, nice_to_have


async def _extract_profile_evidence(user_profile: dict, **_: Any) -> dict:
    """Extract structured evidence from user profile for fact-checking."""
    profile = user_profile or {}
    skills = [
        (s.get("name") if isinstance(s, dict) else str(s))
        for s in (profile.get("skills") or [])
    ]
    companies = []
    titles = []
    dates = []
    for exp in profile.get("experience") or []:
        if isinstance(exp, dict):
            if exp.get("company"):
                companies.append(exp["company"])
            if exp.get("title"):
                titles.append(exp["title"])
            dates.append(
                f"{exp.get('start_date', '?')} – {exp.get('end_date', 'present')}"
            )

    education = []
    for edu in profile.get("education") or []:
        if isinstance(edu, dict):
            education.append(
                f"{edu.get('degree', '')} {edu.get('institution', '')}".strip()
            )

    certs = [
        (c.get("name") if isinstance(c, dict) else str(c))
        for c in (profile.get("certifications") or [])
    ]

    return {
        "skills": skills,
        "companies": companies,
        "titles": titles,
        "experience_dates": dates,
        "education": education,
        "certifications": certs,
        "experience_count": len(profile.get("experience") or []),
        "education_count": len(profile.get("education") or []),
    }


async def _compute_keyword_overlap(
    document_text: str, jd_text: str, **_: Any,
) -> dict:
    """Deterministic ATS keyword overlap between document and JD.

    v2: fuzzy matching for synonyms/variants (e.g. C# ↔ C-sharp),
    plus bigram matching for multi-word skills.
    """
    doc_words = set(
        w.lower() for w in re.findall(r"\b[A-Za-z][A-Za-z+#./\-]{1,30}\b", document_text or "")
    )
    jd_words = set(
        w.lower() for w in re.findall(r"\b[A-Za-z][A-Za-z+#./\-]{1,30}\b", jd_text or "")
    )

    # Exact matches
    exact_common = doc_words & jd_words

    # Fuzzy matches for remaining JD keywords (SequenceMatcher ratio >= 0.8)
    jd_remaining = jd_words - exact_common
    doc_remaining = doc_words - exact_common
    fuzzy_matches: list[dict] = []
    fuzzy_matched_jd: set[str] = set()

    for jd_w in jd_remaining:
        if len(jd_w) < 3:
            continue
        best_ratio = 0.0
        best_doc = ""
        for doc_w in doc_remaining:
            if len(doc_w) < 3:
                continue
            ratio = SequenceMatcher(None, jd_w, doc_w).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_doc = doc_w
        if best_ratio >= 0.8:
            fuzzy_matches.append({
                "jd_keyword": jd_w,
                "doc_keyword": best_doc,
                "similarity": round(best_ratio, 2),
            })
            fuzzy_matched_jd.add(jd_w)

    all_matched = exact_common | fuzzy_matched_jd
    still_missing = jd_words - all_matched - _STOP_WORDS

    # Effective match ratio includes fuzzy matches at weighted rate
    effective_matches = len(exact_common) + len(fuzzy_matches) * 0.8
    total_jd = max(len(jd_words - _STOP_WORDS), 1)

    return {
        "matched_keywords": sorted(exact_common)[:50],
        "fuzzy_matches": fuzzy_matches[:20],
        "missing_from_document": sorted(still_missing)[:30],
        "match_ratio": round(effective_matches / total_jd, 3),
        "exact_match_ratio": round(len(exact_common) / max(len(jd_words), 1), 3),
        "jd_unique_keywords": len(jd_words),
        "doc_unique_keywords": len(doc_words),
    }


async def _compute_readability(text: str, **_: Any) -> dict:
    """Deterministic readability metrics (Flesch-Kincaid approximation).

    v2: improved syllable counting using common English suffix rules,
    plus passive-voice detection and sentence-length distribution.
    """
    sentences = re.split(r"[.!?]+", text or "")
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r"\b\w+\b", text or "")
    syllable_count = sum(_count_syllables(w) for w in words)

    num_sentences = max(len(sentences), 1)
    num_words = max(len(words), 1)

    # Flesch Reading Ease
    flesch = 206.835 - 1.015 * (num_words / num_sentences) - 84.6 * (syllable_count / num_words)
    # Flesch-Kincaid Grade Level
    grade = 0.39 * (num_words / num_sentences) + 11.8 * (syllable_count / num_words) - 15.59
    avg_sentence_len = num_words / num_sentences

    # Sentence length distribution (for identifying outlier-long sentences)
    sentence_lengths = [len(re.findall(r"\b\w+\b", s)) for s in sentences]
    long_sentences = sum(1 for sl in sentence_lengths if sl > 25)

    # Simple passive voice detection
    passive_count = len(re.findall(
        r"\b(?:was|were|is|are|been|being|be)\s+\w+(?:ed|en|t)\b",
        text or "", re.IGNORECASE,
    ))

    return {
        "flesch_reading_ease": round(max(0, min(100, flesch)), 1),
        "grade_level": round(max(0, grade), 1),
        "avg_sentence_length": round(avg_sentence_len, 1),
        "total_words": num_words,
        "total_sentences": num_sentences,
        "long_sentences": long_sentences,
        "passive_voice_count": passive_count,
        "quality_band": _readability_band(flesch),
    }


def _count_syllables(word: str) -> int:
    """Count syllables using English pronunciation heuristics.

    Rules:
    - Count vowel groups (a, e, i, o, u, y)
    - Subtract silent-e at end
    - Handle common suffixes (-le, -ed, -es)
    - Minimum 1 syllable per word
    """
    word = word.lower().strip()
    if len(word) <= 2:
        return 1

    # Remove trailing silent-e (but not if preceded by l → "le" is a syllable)
    if word.endswith("e") and not word.endswith("le") and len(word) > 3:
        word = word[:-1]

    # Count vowel groups
    count = len(re.findall(r"[aeiouy]+", word))

    # Handle -ed suffix (usually not a separate syllable except after t/d)
    if word.endswith("ed") and len(word) > 3:
        if word[-3] not in "td":
            count = max(1, count - 1)

    return max(1, count)


def _readability_band(flesch: float) -> str:
    """Classify Flesch score into quality bands for career documents."""
    if flesch >= 80:
        return "too_simple"
    if flesch >= 60:
        return "ideal"   # Sweet spot for professional documents
    if flesch >= 40:
        return "acceptable"
    return "too_complex"


async def _extract_claims(document_text: str, **_: Any) -> dict:
    """Extract factual claims from document text (deterministic heuristic).

    v2: expanded patterns to catch implicit claims (leadership, scope),
    role-title claims, and technology claims. Each claim tagged with
    extraction_method for downstream confidence calibration.
    """
    text = document_text or ""
    claims: list[dict] = []

    # Quantified claims (numbers, percentages, dollar amounts)
    quant_patterns = [
        (r"(\d+[\+%]?\s*(?:years?|months?)\s+(?:of\s+)?experience)", "years_experience"),
        (r"((?:led|managed|built|designed|developed|created|launched|grew|reduced|improved|increased|decreased|saved|generated|delivered|architected|scaled|deployed|migrated|automated|optimized|mentored|trained|coached)\s+[^.]{10,80})", "action_claim"),
        (r"(\d[\d,]*\+?\s*(?:users?|customers?|clients?|team\s+members?|engineers?|projects?|applications?|transactions?|requests?|events?))", "scale_claim"),
        (r"(\$[\d,.]+[KMB]?\s+[^.]{5,50})", "revenue_claim"),
        (r"(\d+%\s+[^.]{5,60})", "percentage_claim"),
        (r"((?:top|first|only)\s+\d+[%]?\s+[^.]{5,50})", "ranking_claim"),
    ]
    for pattern, claim_type in quant_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claims.append({
                "text": match.group(0).strip(),
                "type": "quantified",
                "subtype": claim_type,
                "position": match.start(),
                "extraction_method": "regex_quantified",
            })

    # Credential claims (degrees, certifications)
    cred_patterns = [
        (r"((?:B\.?S\.?|M\.?S\.?|Ph\.?D\.?|MBA|Bachelor|Master|Doctor|Associate)[^.]{5,80})", "degree"),
        (r"((?:certified|certification|certificate|licensed|license)\s+[^.]{5,60})", "certification"),
    ]
    for pattern, claim_type in cred_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claims.append({
                "text": match.group(0).strip(),
                "type": "credential",
                "subtype": claim_type,
                "position": match.start(),
                "extraction_method": "regex_credential",
            })

    # Implicit leadership/scope claims
    leadership_patterns = [
        (r"((?:team|department|organization|company)[\s-]?wide\s+[^.]{5,60})", "scope_claim"),
        (r"((?:cross[\s-]?functional|end[\s-]?to[\s-]?end|full[\s-]?stack)\s+[^.]{5,60})", "scope_claim"),
        (r"((?:promoted|selected|chosen|appointed)\s+[^.]{5,60})", "advancement_claim"),
    ]
    for pattern, claim_type in leadership_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claims.append({
                "text": match.group(0).strip(),
                "type": "implicit",
                "subtype": claim_type,
                "position": match.start(),
                "extraction_method": "regex_implicit",
            })

    # Company name claims (extract standalone company references)
    company_pattern = r"(?:at|for|with|@)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})"
    for match in re.finditer(company_pattern, text):
        company_name = match.group(1).strip()
        if len(company_name) > 2 and company_name.lower() not in _STOP_WORDS:
            claims.append({
                "text": f"worked at {company_name}",
                "type": "employment",
                "subtype": "company_claim",
                "position": match.start(),
                "extraction_method": "regex_company",
            })

    # Deduplicate by position (allow 5-char overlap window)
    claims.sort(key=lambda x: x["position"])
    unique_claims: list[dict] = []
    last_pos = -10
    for c in claims:
        if c["position"] - last_pos > 5:
            unique_claims.append(c)
            last_pos = c["position"]

    return {
        "claims": unique_claims[:50],
        "total_claims_found": len(unique_claims),
        "claim_types": _count_claim_types(unique_claims),
    }


def _count_claim_types(claims: list[dict]) -> dict[str, int]:
    """Count claims by type for summary."""
    counts: dict[str, int] = {}
    for c in claims:
        t = c.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


async def _match_claims_to_evidence(
    claims: list[dict], evidence: dict, **_: Any,
) -> dict:
    """Match extracted claims against profile evidence (deterministic).

    v2: fuzzy matching for skill/company variants, multi-pool scoring,
    and match confidence per claim.
    """
    # Build evidence pools with normalized variants
    pools: dict[str, set[str]] = {
        "skill": {s.lower() for s in (evidence.get("skills") or [])},
        "company": {c.lower() for c in (evidence.get("companies") or [])},
        "title": {t.lower() for t in (evidence.get("titles") or [])},
        "cert": {c.lower() for c in (evidence.get("certifications") or [])},
        "education": {e.lower() for e in (evidence.get("education") or [])},
    }

    # Flatten all evidence into a single text for broad matching
    all_evidence_text = " ".join(
        " ".join(items) for items in pools.values()
    ).lower()

    matched: list[dict] = []
    unmatched: list[dict] = []

    for claim in claims:
        text_lower = claim.get("text", "").lower()
        sources: list[str] = []
        match_confidence = 0.0

        # Exact substring matching against each pool
        for pool_name, pool_items in pools.items():
            for item in pool_items:
                if item in text_lower or text_lower in item:
                    sources.append(f"{pool_name}:{item}")
                    match_confidence = max(match_confidence, 0.9)

        # Fuzzy matching if no exact match found
        if not sources:
            for pool_name, pool_items in pools.items():
                for item in pool_items:
                    if len(item) < 3:
                        continue
                    # Check word-level overlap
                    claim_words = set(text_lower.split())
                    item_words = set(item.split())
                    overlap = claim_words & item_words
                    if overlap and len(overlap) / max(len(item_words), 1) >= 0.5:
                        sources.append(f"{pool_name}:{item}(fuzzy)")
                        match_confidence = max(match_confidence, 0.6)

        # Broad evidence text check for low-confidence matches
        if not sources and len(text_lower) > 10:
            claim_significant_words = {
                w for w in text_lower.split()
                if len(w) > 3 and w not in _STOP_WORDS
            }
            evidence_words = set(all_evidence_text.split())
            overlap = claim_significant_words & evidence_words
            if overlap and len(overlap) >= 2:
                sources.append(f"broad_match:{','.join(sorted(overlap)[:3])}")
                match_confidence = max(match_confidence, 0.4)

        if sources:
            matched.append({
                **claim,
                "sources": sources,
                "match_confidence": round(match_confidence, 2),
            })
        else:
            unmatched.append({**claim, "match_confidence": 0.0})

    return {
        "matched_claims": matched,
        "unmatched_claims": unmatched,
        "match_rate": round(len(matched) / max(len(claims), 1), 3),
        "high_confidence_matches": sum(
            1 for m in matched if m.get("match_confidence", 0) >= 0.8
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
#  External tools — web search, DB queries, company intel
# ═══════════════════════════════════════════════════════════════════════

import os
import logging as _logging

_ext_logger = _logging.getLogger("hirestack.agents.tools.external")


# ─────────────────────────────────────────────────────────────
#  Multi-provider web search with free fallbacks + TTL cache
#
#  Provider priority (first one with a key wins, else free fallback):
#    1. Tavily        (TAVILY_API_KEY)        — best snippets
#    2. Serper.dev    (SERPER_API_KEY)        — cheap Google SERP
#    3. SerpAPI       (SERPAPI_KEY / GOOGLE_SEARCH_API_KEY)
#    4. Brave Search  (BRAVE_API_KEY)
#    5. DuckDuckGo HTML (no key, best-effort)
#    6. Wikipedia     (no key, last-resort noun lookup)
#
#  Results are cached in-process for 24h keyed by (provider, query, n).
# ─────────────────────────────────────────────────────────────

import time as _time
import urllib.parse as _urlparse

_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}
_SEARCH_CACHE_TTL = 60 * 60 * 24  # 24 hours
_SEARCH_CACHE_MAX = 512
_SEARCH_CACHE_PREFIX = "aisearch:"


def _redis_client_opt():
    """Return the shared Redis client if available, else None. Never raises."""
    try:
        from backend.app.core.database import get_redis  # type: ignore
        return get_redis()
    except Exception:
        try:
            # Alternate import path when backend/ is added to sys.path
            from app.core.database import get_redis  # type: ignore
            return get_redis()
        except Exception:
            return None


def _search_cache_get(key: str) -> Optional[dict]:
    # Try Redis first (survives restart, shared across workers)
    r = _redis_client_opt()
    if r is not None:
        try:
            val = r.get(_SEARCH_CACHE_PREFIX + key)
            if val is not None:
                return json.loads(val)
        except Exception:
            pass
    # In-process fallback
    hit = _SEARCH_CACHE.get(key)
    if not hit:
        return None
    ts, payload = hit
    if _time.time() - ts > _SEARCH_CACHE_TTL:
        _SEARCH_CACHE.pop(key, None)
        return None
    return payload


def _search_cache_put(key: str, payload: dict) -> None:
    # Redis write (best-effort)
    r = _redis_client_opt()
    if r is not None:
        try:
            r.setex(_SEARCH_CACHE_PREFIX + key, _SEARCH_CACHE_TTL, json.dumps(payload, default=str))
        except Exception:
            pass
    # Always also write the in-process copy so a Redis outage mid-request
    # doesn't cause a cache miss seconds later.
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX:
        oldest_key = min(_SEARCH_CACHE, key=lambda k: _SEARCH_CACHE[k][0])
        _SEARCH_CACHE.pop(oldest_key, None)
    _SEARCH_CACHE[key] = (_time.time(), payload)


async def _provider_tavily(query: str, max_results: int) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": min(max_results, 10),
                    "search_depth": "basic",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {"title": r.get("title", ""), "snippet": r.get("content", "")[:500], "link": r.get("url", "")}
            for r in data.get("results", [])[:max_results]
        ]
    except Exception as e:
        _ext_logger.debug("tavily_failed: %s", str(e))
        return []


async def _provider_serper(query: str, max_results: int) -> list[dict]:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": min(max_results, 10)},
            )
            resp.raise_for_status()
            data = resp.json()
        organic = data.get("organic", [])
        return [
            {"title": r.get("title", ""), "snippet": r.get("snippet", ""), "link": r.get("link", "")}
            for r in organic[:max_results]
        ]
    except Exception as e:
        _ext_logger.debug("serper_failed: %s", str(e))
        return []


async def _provider_serpapi(query: str, max_results: int) -> list[dict]:
    api_key = os.getenv("SERPAPI_KEY") or os.getenv("GOOGLE_SEARCH_API_KEY")
    if not api_key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": api_key,
                    "num": min(max_results, 10),
                    "engine": "google",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        organic = data.get("organic_results", [])
        return [
            {"title": r.get("title", ""), "snippet": r.get("snippet", ""), "link": r.get("link", "")}
            for r in organic[:max_results]
        ]
    except Exception as e:
        _ext_logger.debug("serpapi_failed: %s", str(e))
        return []


async def _provider_brave(query: str, max_results: int) -> list[dict]:
    api_key = os.getenv("BRAVE_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                params={"q": query, "count": min(max_results, 10)},
            )
            resp.raise_for_status()
            data = resp.json()
        web_results = (data.get("web") or {}).get("results", [])
        return [
            {"title": r.get("title", ""), "snippet": r.get("description", ""), "link": r.get("url", "")}
            for r in web_results[:max_results]
        ]
    except Exception as e:
        _ext_logger.debug("brave_failed: %s", str(e))
        return []


async def _provider_duckduckgo(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo HTML scrape — no key required. Best-effort fallback."""
    try:
        import httpx
        import re as _re
        async with httpx.AsyncClient(
            timeout=8.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; HireStack-AI/2.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        ) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
            )
            if resp.status_code != 200:
                return []
            html = resp.text
        # Each result block: <a class="result__a" href="...">Title</a> … <a class="result__snippet">Snippet</a>
        pattern = _re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            _re.DOTALL | _re.IGNORECASE,
        )
        out: list[dict] = []
        for m in pattern.finditer(html):
            raw_link, raw_title, raw_snippet = m.group(1), m.group(2), m.group(3)
            # DDG wraps links as /l/?uddg=<encoded-target>
            link = raw_link
            if "uddg=" in link:
                try:
                    link = _urlparse.unquote(link.split("uddg=", 1)[1].split("&", 1)[0])
                except Exception:
                    pass
            title = _re.sub(r"<[^>]+>", "", raw_title).strip()
            snippet = _re.sub(r"<[^>]+>", "", raw_snippet).strip()
            if title and link.startswith("http"):
                out.append({"title": title, "snippet": snippet[:500], "link": link})
            if len(out) >= max_results:
                break
        return out
    except Exception as e:
        _ext_logger.debug("ddg_failed: %s", str(e))
        return []


async def _provider_wikipedia(query: str, max_results: int) -> list[dict]:
    """Wikipedia summary lookup — last-resort company identity fallback."""
    try:
        import httpx
        async with httpx.AsyncClient(
            timeout=6.0,
            follow_redirects=True,
            headers={
                # Wikipedia requires a descriptive UA or 403s
                "User-Agent": "HireStack-AI/2.0 (career-intel; contact: hirestack.tech)",
                "Accept": "application/json",
            },
        ) as client:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": min(max_results, 5),
                    "format": "json",
                },
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        hits = ((data.get("query") or {}).get("search") or [])
        out: list[dict] = []
        for h in hits[:max_results]:
            title = h.get("title", "")
            snippet = re.sub(r"<[^>]+>", "", h.get("snippet", "") or "")
            if title:
                out.append({
                    "title": f"Wikipedia — {title}",
                    "snippet": snippet[:400],
                    "link": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                })
        return out
    except Exception as e:
        _ext_logger.debug("wiki_failed: %s", str(e))
        return []


async def _web_search(query: str, max_results: int = 5, **_: Any) -> dict:
    """
    Multi-provider web search with graceful fallback + 24h cache.

    Tries paid providers first (if keys present), then free DDG/Wikipedia.
    Returns {"results": [...], "query": query, "provider": "...", "count": n}.
    """
    if not query or not query.strip():
        return {"results": [], "query": query, "error": "empty query"}

    cache_key = f"{query}|{max_results}"
    cached = _search_cache_get(cache_key)
    if cached is not None:
        return {**cached, "cache": True}

    providers = [
        ("tavily", _provider_tavily),
        ("serper", _provider_serper),
        ("serpapi", _provider_serpapi),
        ("brave", _provider_brave),
        ("duckduckgo", _provider_duckduckgo),
        ("wikipedia", _provider_wikipedia),
    ]

    for name, fn in providers:
        try:
            results = await fn(query, max_results)
        except Exception as e:
            _ext_logger.warning("provider_%s_unhandled: %s", name, str(e))
            results = []
        if results:
            payload = {
                "results": results,
                "query": query,
                "provider": name,
                "count": len(results),
            }
            _search_cache_put(cache_key, payload)
            return payload

    # No provider returned anything
    empty = {"results": [], "query": query, "provider": "none", "count": 0,
             "error": "all search providers returned 0 results"}
    _search_cache_put(cache_key, empty)
    return empty


async def _search_company_info(company_name: str, **_: Any) -> dict:
    """Search for company culture, values, and recent news."""
    if not company_name or len(company_name.strip()) < 2:
        return {"company": company_name, "info": {}, "error": "Company name too short"}

    culture = await _web_search(f"{company_name} company culture values mission glassdoor", max_results=5)
    news = await _web_search(f"{company_name} company news recent", max_results=3)

    return {
        "company": company_name,
        "culture_results": culture.get("results", []),
        "news_results": news.get("results", []),
        "has_data": bool(culture.get("results")),
    }


async def _search_salary_data(job_title: str, location: str = "", **_: Any) -> dict:
    """Search for salary ranges for a given role and location."""
    query = f"{job_title} salary range"
    if location:
        query += f" {location}"
    query += " glassdoor levels.fyi"
    result = await _web_search(query, max_results=5)
    return {
        "job_title": job_title,
        "location": location or "unspecified",
        "results": result.get("results", []),
        "has_data": bool(result.get("results")),
    }


async def _search_industry_trends(industry: str = "", job_title: str = "", **_: Any) -> dict:
    """Search for industry trends and in-demand skills."""
    if not industry and not job_title:
        return {"results": [], "error": "Need industry or job_title"}
    query = f"{industry or job_title} industry trends skills demand 2025"
    result = await _web_search(query, max_results=5)
    return {"industry": industry, "job_title": job_title, "results": result.get("results", []), "has_data": bool(result.get("results"))}


async def _query_user_history(user_id: str = "", db: Any = None, **_: Any) -> dict:
    """Query user's past application history and quality score patterns from DB."""
    if not db or not user_id:
        return {"user_id": user_id, "history": [], "error": "No DB or user_id"}

    try:
        import asyncio

        resp = await asyncio.to_thread(
            lambda: db.table("applications")
            .select("id,title,status,created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        apps = resp.data or []

        trace_resp = await asyncio.to_thread(
            lambda: db.table("agent_traces")
            .select("pipeline_name,quality_scores")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        traces = trace_resp.data or []

        score_sums: dict[str, float] = {}
        score_counts: dict[str, int] = {}
        for t in traces:
            qs = t.get("quality_scores") or {}
            for dim, score in qs.items():
                if isinstance(score, (int, float)):
                    score_sums[dim] = score_sums.get(dim, 0) + score
                    score_counts[dim] = score_counts.get(dim, 0) + 1
        avg_scores = {dim: round(score_sums[dim] / score_counts[dim], 1) for dim in score_sums if score_counts.get(dim, 0) > 0}

        return {
            "user_id": user_id,
            "total_applications": len(apps),
            "recent_titles": [a.get("title", "") for a in apps[:5]],
            "avg_quality_scores": avg_scores,
            "has_history": len(apps) > 0,
        }
    except Exception as e:
        _ext_logger.warning("user_history_query_failed: %s", str(e))
        return {"user_id": user_id, "history": [], "error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════════
#  v3 Deep-research tools — glassdoor, linkedin, news, competitors,
#  tech blogs, JD sentiment, cross-reference postings
# ═══════════════════════════════════════════════════════════════════════


async def _search_glassdoor_reviews(company_name: str, **_: Any) -> dict:
    """Search for Glassdoor-style reviews: interview process, culture, pros/cons."""
    if not company_name or len(company_name.strip()) < 2:
        return {"company": company_name, "error": "Company name too short"}

    interview_data = await _web_search(
        f"{company_name} glassdoor interview process questions experience",
        max_results=5,
    )
    review_data = await _web_search(
        f"{company_name} glassdoor employee reviews pros cons",
        max_results=5,
    )
    return {
        "company": company_name,
        "interview_results": interview_data.get("results", []),
        "review_results": review_data.get("results", []),
        "has_data": bool(interview_data.get("results") or review_data.get("results")),
    }


async def _search_linkedin_insights(company_name: str, job_title: str = "", **_: Any) -> dict:
    """Search for LinkedIn-style career insights: career paths, hiring patterns."""
    if not company_name:
        return {"error": "No company name"}

    query_parts = [company_name]
    if job_title:
        query_parts.append(job_title)
    query_parts.append("linkedin hiring career path team size")

    result = await _web_search(" ".join(query_parts), max_results=5)
    return {
        "company": company_name,
        "job_title": job_title,
        "results": result.get("results", []),
        "has_data": bool(result.get("results")),
    }


async def _search_company_news(company_name: str, **_: Any) -> dict:
    """Search for recent company news: funding, acquisitions, launches, leadership."""
    if not company_name:
        return {"error": "No company name"}

    funding = await _web_search(
        f"{company_name} funding round acquisition launch 2025 2026",
        max_results=5,
    )
    leadership = await _web_search(
        f"{company_name} CEO CTO leadership team announcement",
        max_results=3,
    )
    return {
        "company": company_name,
        "funding_news": funding.get("results", []),
        "leadership_news": leadership.get("results", []),
        "has_data": bool(funding.get("results") or leadership.get("results")),
    }


async def _search_competitor_landscape(company_name: str, industry: str = "", **_: Any) -> dict:
    """Search for competitor landscape and market positioning."""
    if not company_name:
        return {"error": "No company name"}

    query = f"{company_name} competitors alternatives"
    if industry:
        query += f" {industry}"
    query += " market comparison"

    result = await _web_search(query, max_results=5)
    return {
        "company": company_name,
        "industry": industry,
        "results": result.get("results", []),
        "has_data": bool(result.get("results")),
    }


async def _search_tech_blog(company_name: str, **_: Any) -> dict:
    """Search for company engineering blog, open source contributions, tech culture."""
    if not company_name:
        return {"error": "No company name"}

    blog = await _web_search(
        f"{company_name} engineering blog tech stack architecture",
        max_results=5,
    )
    oss = await _web_search(
        f"{company_name} open source github contributions",
        max_results=3,
    )
    return {
        "company": company_name,
        "blog_results": blog.get("results", []),
        "oss_results": oss.get("results", []),
        "has_data": bool(blog.get("results") or oss.get("results")),
    }


async def _analyze_jd_sentiment(jd_text: str, **_: Any) -> dict:
    """Deterministic JD sentiment analysis: urgency, red flags, seniority signals."""
    text = (jd_text or "").lower()
    if not text:
        return {"error": "Empty JD text"}

    # Urgency signals
    urgency_patterns = [
        "immediately", "asap", "urgent", "fast-paced", "rapidly growing",
        "high-growth", "startup", "we need", "looking for someone who can start",
    ]
    urgency_hits = [p for p in urgency_patterns if p in text]

    # Red flags
    red_flag_patterns = [
        "wear many hats", "self-starter", "must be able to work independently",
        "fast-paced environment", "unlimited pto", "like a family",
        "rockstar", "ninja", "guru", "other duties as assigned",
        "competitive salary", "salary commensurate",
    ]
    red_flag_hits = [p for p in red_flag_patterns if p in text]

    # Seniority signals
    senior_signals = ["senior", "lead", "principal", "staff", "architect", "director", "head of", "vp "]
    junior_signals = ["entry", "junior", "associate", "intern", "graduate", "0-2 years", "1-3 years"]
    seniority = "mid"
    if any(s in text for s in senior_signals):
        seniority = "senior"
    if any(s in text for s in junior_signals):
        seniority = "junior"

    # Compensation signals
    salary_match = re.findall(r"\$[\d,]+(?:k|K)?(?:\s*[-–]\s*\$[\d,]+(?:k|K)?)?", jd_text or "")
    equity_mentioned = any(w in text for w in ["equity", "stock", "options", "rsu", "shares"])

    # Team size hints
    team_size_match = re.findall(r"team of (\d+)", text)
    team_size = int(team_size_match[0]) if team_size_match else None

    # Remote/hybrid/onsite
    work_mode = "unknown"
    if "remote" in text:
        work_mode = "remote"
    if "hybrid" in text:
        work_mode = "hybrid"
    if "on-site" in text or "onsite" in text or "in-office" in text:
        work_mode = "onsite"

    return {
        "urgency_level": "high" if len(urgency_hits) >= 2 else ("medium" if urgency_hits else "low"),
        "urgency_signals": urgency_hits,
        "red_flags": red_flag_hits,
        "red_flag_count": len(red_flag_hits),
        "seniority_level": seniority,
        "salary_mentioned": salary_match[:3] if salary_match else [],
        "equity_mentioned": equity_mentioned,
        "team_size": team_size,
        "work_mode": work_mode,
    }


async def _cross_reference_job_postings(company_name: str, job_title: str = "", **_: Any) -> dict:
    """Find other active listings from the same company to infer hiring patterns."""
    if not company_name:
        return {"error": "No company name"}

    query = f"{company_name} jobs careers current openings"
    if job_title:
        query += f" {job_title}"

    result = await _web_search(query, max_results=7)
    postings = result.get("results", [])

    return {
        "company": company_name,
        "job_title": job_title,
        "other_postings": postings,
        "hiring_volume": (
            "aggressive" if len(postings) >= 5
            else "moderate" if len(postings) >= 2
            else "selective" if postings
            else "unknown"
        ),
        "has_data": bool(postings),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Pre-built registries
# ═══════════════════════════════════════════════════════════════════════


def build_researcher_tools(db: Any = None, user_id: str = "") -> ToolRegistry:
    """Tools available to the ResearcherAgent.

    v3: includes external tools (web search, company intel, user history)
    alongside deterministic local tools.
    """
    reg = ToolRegistry()

    # ── Core deterministic tools ──
    reg.register(AgentTool(
        name="parse_jd",
        description="Extract keywords, frequency counts, and structure from a job description.",
        parameters={
            "type": "object",
            "properties": {
                "jd_text": {"type": "string", "description": "Raw job description text"},
            },
            "required": ["jd_text"],
        },
        fn=_parse_jd,
    ))

    reg.register(AgentTool(
        name="extract_profile_evidence",
        description="Extract structured evidence (skills, companies, titles, education, certs) from user profile.",
        parameters={
            "type": "object",
            "properties": {
                "user_profile": {"type": "object", "description": "User profile dict"},
            },
            "required": ["user_profile"],
        },
        fn=_extract_profile_evidence,
    ))

    reg.register(AgentTool(
        name="compute_keyword_overlap",
        description="Compute deterministic keyword overlap between document text and JD.",
        parameters={
            "type": "object",
            "properties": {
                "document_text": {"type": "string"},
                "jd_text": {"type": "string"},
            },
            "required": ["document_text", "jd_text"],
        },
        fn=_compute_keyword_overlap,
    ))

    # ── External tools (v3) ──
    reg.register(AgentTool(
        name="search_company_info",
        description="Search the web for company culture, values, mission, and recent news. Use when company context is needed for tone matching.",
        parameters={
            "type": "object",
            "properties": {"company_name": {"type": "string", "description": "Company name to research"}},
            "required": ["company_name"],
        },
        fn=_search_company_info,
    ))

    reg.register(AgentTool(
        name="search_salary_data",
        description="Search for salary ranges and compensation data for a specific role and location.",
        parameters={
            "type": "object",
            "properties": {
                "job_title": {"type": "string", "description": "The job title"},
                "location": {"type": "string", "description": "Location (city/country)"},
            },
            "required": ["job_title"],
        },
        fn=_search_salary_data,
    ))

    reg.register(AgentTool(
        name="search_industry_trends",
        description="Search for current industry trends and in-demand skills.",
        parameters={
            "type": "object",
            "properties": {
                "industry": {"type": "string", "description": "Industry sector"},
                "job_title": {"type": "string", "description": "Job title to research"},
            },
        },
        fn=_search_industry_trends,
    ))

    # ── Deep-research tools (v3.1) ──
    reg.register(AgentTool(
        name="search_glassdoor_reviews",
        description="Search for Glassdoor-style reviews: interview process, culture, pros/cons.",
        parameters={
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to research"},
            },
            "required": ["company_name"],
        },
        fn=_search_glassdoor_reviews,
    ))

    reg.register(AgentTool(
        name="search_linkedin_insights",
        description="Search for LinkedIn career insights: hiring patterns, career paths, team composition.",
        parameters={
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "job_title": {"type": "string", "description": "Target job title"},
            },
            "required": ["company_name"],
        },
        fn=_search_linkedin_insights,
    ))

    reg.register(AgentTool(
        name="search_company_news",
        description="Search for recent company news: funding, acquisitions, product launches, leadership changes.",
        parameters={
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
            },
            "required": ["company_name"],
        },
        fn=_search_company_news,
    ))

    reg.register(AgentTool(
        name="search_competitor_landscape",
        description="Search for competitor landscape and market positioning for the company.",
        parameters={
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "industry": {"type": "string", "description": "Industry sector"},
            },
            "required": ["company_name"],
        },
        fn=_search_competitor_landscape,
    ))

    reg.register(AgentTool(
        name="search_tech_blog",
        description="Search for company engineering blog, tech stack, and open source contributions.",
        parameters={
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
            },
            "required": ["company_name"],
        },
        fn=_search_tech_blog,
    ))

    reg.register(AgentTool(
        name="analyze_jd_sentiment",
        description="Perform deterministic analysis of a job description for urgency, red flags, seniority signals, and compensation hints.",
        parameters={
            "type": "object",
            "properties": {
                "jd_text": {"type": "string", "description": "Raw job description text"},
            },
            "required": ["jd_text"],
        },
        fn=_analyze_jd_sentiment,
    ))

    reg.register(AgentTool(
        name="cross_reference_job_postings",
        description="Find other active job listings from the same company to infer hiring patterns and team growth.",
        parameters={
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "job_title": {"type": "string", "description": "Job title to cross-reference"},
            },
            "required": ["company_name"],
        },
        fn=_cross_reference_job_postings,
    ))

    # ── DB-backed tools (only when db is available) ──
    if db and user_id:
        async def _query_history(**kwargs: Any) -> dict:
            return await _query_user_history(user_id=user_id, db=db, **kwargs)

        reg.register(AgentTool(
            name="query_user_history",
            description="Query this user's past application history and quality score patterns from the database.",
            parameters={"type": "object", "properties": {}},
            fn=_query_history,
        ))

    return reg


def build_fact_checker_tools() -> ToolRegistry:
    """Tools available to the FactCheckerAgent."""
    reg = ToolRegistry()

    reg.register(AgentTool(
        name="extract_profile_evidence",
        description="Extract structured evidence from user profile for cross-referencing.",
        parameters={
            "type": "object",
            "properties": {
                "user_profile": {"type": "object", "description": "User profile dict"},
            },
            "required": ["user_profile"],
        },
        fn=_extract_profile_evidence,
    ))

    reg.register(AgentTool(
        name="extract_claims",
        description="Extract factual claims (quantified achievements, credentials) from document text.",
        parameters={
            "type": "object",
            "properties": {
                "document_text": {"type": "string", "description": "Raw document text to analyze"},
            },
            "required": ["document_text"],
        },
        fn=_extract_claims,
    ))

    reg.register(AgentTool(
        name="match_claims_to_evidence",
        description="Cross-reference extracted claims against profile evidence. Returns matched and unmatched claims.",
        parameters={
            "type": "object",
            "properties": {
                "claims": {"type": "array", "description": "List of claim dicts from extract_claims"},
                "evidence": {"type": "object", "description": "Evidence dict from extract_profile_evidence"},
            },
            "required": ["claims", "evidence"],
        },
        fn=_match_claims_to_evidence,
    ))

    return reg


def build_optimizer_tools() -> ToolRegistry:
    """Tools available to the OptimizerAgent."""
    reg = ToolRegistry()

    reg.register(AgentTool(
        name="compute_keyword_overlap",
        description="Compute ATS keyword match ratio between document and job description.",
        parameters={
            "type": "object",
            "properties": {
                "document_text": {"type": "string"},
                "jd_text": {"type": "string"},
            },
            "required": ["document_text", "jd_text"],
        },
        fn=_compute_keyword_overlap,
    ))

    reg.register(AgentTool(
        name="compute_readability",
        description="Compute Flesch reading ease, grade level, and sentence stats.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Document text to analyze"},
            },
            "required": ["text"],
        },
        fn=_compute_readability,
    ))

    return reg
