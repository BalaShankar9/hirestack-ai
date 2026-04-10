"""
Agent Tool Registry — callable tools for agent-driven retrieval and analysis.

Each tool is an async callable with a name, description, and parameter schema.
Agents select tools based on their current state and call them in a loop
until their coverage/confidence threshold is met.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
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


# ═══════════════════════════════════════════════════════════════════════
#  Built-in tools
# ═══════════════════════════════════════════════════════════════════════


async def _parse_jd(jd_text: str, **_: Any) -> dict:
    """Extract structured fields from a job description (deterministic)."""
    text = jd_text or ""
    # Extract keywords by frequency (simple but deterministic)
    words = re.findall(r"\b[A-Za-z][A-Za-z+#./\-]{1,30}\b", text)
    freq: dict[str, int] = {}
    stop_words = {
        "the", "and", "for", "with", "that", "this", "are", "you", "will",
        "our", "have", "from", "your", "can", "not", "but", "all", "been",
        "has", "their", "what", "who", "which", "into", "about", "more",
        "than", "its", "also", "should", "would", "could", "may", "must",
    }
    for w in words:
        low = w.lower()
        if low not in stop_words and len(low) > 2:
            freq[low] = freq.get(low, 0) + 1

    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:30]

    return {
        "keyword_frequency": {k: v for k, v in sorted_kw},
        "total_words": len(words),
        "top_keywords": [k for k, _ in sorted_kw[:15]],
    }


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
    """Deterministic ATS keyword overlap between document and JD."""
    doc_words = set(
        w.lower() for w in re.findall(r"\b[A-Za-z][A-Za-z+#./\-]{1,30}\b", document_text or "")
    )
    jd_words = set(
        w.lower() for w in re.findall(r"\b[A-Za-z][A-Za-z+#./\-]{1,30}\b", jd_text or "")
    )
    common = doc_words & jd_words
    jd_only = jd_words - doc_words

    return {
        "matched_keywords": sorted(common)[:50],
        "missing_from_document": sorted(jd_only)[:30],
        "match_ratio": round(len(common) / max(len(jd_words), 1), 3),
        "jd_unique_keywords": len(jd_words),
        "doc_unique_keywords": len(doc_words),
    }


async def _compute_readability(text: str, **_: Any) -> dict:
    """Deterministic readability metrics (Flesch-Kincaid approximation)."""
    sentences = re.split(r"[.!?]+", text or "")
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r"\b\w+\b", text or "")
    syllable_count = 0
    for word in words:
        # Simple syllable count heuristic
        vowels = len(re.findall(r"[aeiouy]+", word.lower()))
        syllable_count += max(1, vowels)

    num_sentences = max(len(sentences), 1)
    num_words = max(len(words), 1)

    # Flesch Reading Ease
    flesch = 206.835 - 1.015 * (num_words / num_sentences) - 84.6 * (syllable_count / num_words)
    # Flesch-Kincaid Grade Level
    grade = 0.39 * (num_words / num_sentences) + 11.8 * (syllable_count / num_words) - 15.59

    # Avg sentence length
    avg_sentence_len = num_words / num_sentences

    return {
        "flesch_reading_ease": round(max(0, min(100, flesch)), 1),
        "grade_level": round(max(0, grade), 1),
        "avg_sentence_length": round(avg_sentence_len, 1),
        "total_words": num_words,
        "total_sentences": num_sentences,
    }


async def _extract_claims(document_text: str, **_: Any) -> dict:
    """Extract factual claims from document text (deterministic heuristic)."""
    text = document_text or ""
    claims: list[dict] = []

    # Look for quantified claims
    quant_patterns = [
        r"(\d+[\+%]?\s*(?:years?|months?)\s+(?:of\s+)?experience)",
        r"((?:led|managed|built|designed|developed|created|launched|grew|reduced|improved|increased|decreased|saved|generated|delivered)\s+[^.]{10,80})",
        r"(\d[\d,]*\+?\s*(?:users?|customers?|clients?|team\s+members?|engineers?|projects?|applications?))",
        r"(\$[\d,.]+[KMB]?\s+[^.]{5,50})",
        r"(\d+%\s+[^.]{5,60})",
    ]
    for pattern in quant_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claims.append({
                "text": match.group(0).strip(),
                "type": "quantified",
                "position": match.start(),
            })

    # Look for credential claims (degrees, certifications)
    cred_patterns = [
        r"((?:B\.?S\.?|M\.?S\.?|Ph\.?D\.?|MBA|Bachelor|Master|Doctor)[^.]{5,80})",
        r"((?:certified|certification|certificate)\s+[^.]{5,60})",
    ]
    for pattern in cred_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            claims.append({
                "text": match.group(0).strip(),
                "type": "credential",
                "position": match.start(),
            })

    # Deduplicate by position
    seen_positions: set[int] = set()
    unique_claims = []
    for c in sorted(claims, key=lambda x: x["position"]):
        if c["position"] not in seen_positions:
            seen_positions.add(c["position"])
            unique_claims.append(c)

    return {
        "claims": unique_claims[:50],
        "total_claims_found": len(unique_claims),
    }


async def _match_claims_to_evidence(
    claims: list[dict], evidence: dict, **_: Any,
) -> dict:
    """Match extracted claims against profile evidence (deterministic)."""
    skills_lower = {s.lower() for s in (evidence.get("skills") or [])}
    companies_lower = {c.lower() for c in (evidence.get("companies") or [])}
    titles_lower = {t.lower() for t in (evidence.get("titles") or [])}
    certs_lower = {c.lower() for c in (evidence.get("certifications") or [])}
    edus_lower = {e.lower() for e in (evidence.get("education") or [])}

    matched: list[dict] = []
    unmatched: list[dict] = []

    for claim in claims:
        text_lower = claim.get("text", "").lower()
        sources: list[str] = []

        # Check against all evidence pools
        for skill in skills_lower:
            if skill in text_lower:
                sources.append(f"skill:{skill}")
        for company in companies_lower:
            if company in text_lower:
                sources.append(f"company:{company}")
        for title in titles_lower:
            if title in text_lower:
                sources.append(f"title:{title}")
        for cert in certs_lower:
            if cert in text_lower:
                sources.append(f"cert:{cert}")
        for edu in edus_lower:
            if edu in text_lower:
                sources.append(f"education:{edu}")

        if sources:
            matched.append({**claim, "sources": sources})
        else:
            unmatched.append(claim)

    return {
        "matched_claims": matched,
        "unmatched_claims": unmatched,
        "match_rate": round(len(matched) / max(len(claims), 1), 3),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Pre-built registries
# ═══════════════════════════════════════════════════════════════════════

def build_researcher_tools() -> ToolRegistry:
    """Tools available to the ResearcherAgent."""
    reg = ToolRegistry()

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
