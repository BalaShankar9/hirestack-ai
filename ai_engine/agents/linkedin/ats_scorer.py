"""Deterministic ATS-style scoring for LinkedIn profiles (S16-P2).

Pure-python heuristics, zero LLM calls. Used both as a baseline metric
and as the "before/after" oracle inside the optimizer.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set, Tuple

from ai_engine.agents.linkedin.schemas import LinkedInProfile, ProfileScore

_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|x|k|m|users|customers|hours)?\b", re.I)
_ACTION_VERBS = {
    "led", "shipped", "drove", "built", "designed", "owned", "launched",
    "scaled", "reduced", "improved", "automated", "delivered", "grew",
    "managed", "spearheaded", "architected", "negotiated", "mentored",
    "founded", "established", "transformed",
}
_STOPWORDS = {
    "and", "or", "the", "a", "an", "of", "to", "for", "with", "in", "on",
    "at", "by", "is", "are", "was", "were", "be", "this", "that", "from",
    "as", "we", "i", "my", "our", "their", "it", "its",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#\.\-]{1,}")


def _tokens(text: str) -> List[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")]


def _content_tokens(text: str) -> List[str]:
    return [t for t in _tokens(text) if t not in _STOPWORDS and len(t) > 2]


def _role_keywords(target_role: str) -> Set[str]:
    """Very small role-keyword expander — pluggable later."""
    base = set(_content_tokens(target_role))
    role_packs = {
        "engineer": {"python", "java", "system", "design", "scale",
                     "distributed", "api", "production", "reliability"},
        "manager":  {"roadmap", "stakeholder", "strategy", "okr",
                     "metrics", "execution", "team"},
        "data":     {"sql", "etl", "ml", "analytics", "experiment",
                     "model", "pipeline"},
        "designer": {"ux", "ui", "research", "prototype", "figma",
                     "accessibility"},
        "product":  {"roadmap", "discovery", "metrics", "experiment",
                     "stakeholder", "launch"},
    }
    for token in list(base):
        for trigger, pack in role_packs.items():
            if trigger in token:
                base.update(pack)
    return base


# ─── per-section scorers ────────────────────────────────────────────

def _score_headline(headline: str, role_kw: Set[str]) -> Tuple[float, List[str]]:
    text = (headline or "").strip()
    if not text:
        return 0.0, ["Add a headline (80–120 chars is the sweet spot)."]
    n = len(text)
    length_score = 1.0 if 80 <= n <= 120 else (0.6 if 50 <= n < 80 or 120 < n <= 180 else 0.3)
    tokens = set(_content_tokens(text))
    overlap = (len(tokens & role_kw) / max(1, len(role_kw))) if role_kw else 0.0
    keyword_score = min(1.0, overlap * 4)  # 25 % overlap → full marks
    score = 0.5 * length_score + 0.5 * keyword_score
    fb: List[str] = []
    if length_score < 1.0:
        fb.append(f"Headline length is {n} chars; aim for 80–120.")
    if keyword_score < 0.5:
        fb.append("Headline lacks role-relevant keywords.")
    return round(score, 3), fb


def _score_about(about: str, role_kw: Set[str]) -> Tuple[float, List[str]]:
    text = (about or "").strip()
    if not text:
        return 0.0, ["Add an About section (≥600 chars recommended)."]
    n = len(text)
    length_score = 1.0 if n >= 600 else (0.6 if n >= 300 else 0.3)
    tokens = set(_content_tokens(text))
    keyword_overlap = len(tokens & role_kw) / max(1, len(role_kw)) if role_kw else 0.0
    keyword_score = min(1.0, keyword_overlap * 3)
    quantified = 1.0 if _NUMBER_RE.search(text) else 0.4
    score = 0.4 * length_score + 0.4 * keyword_score + 0.2 * quantified
    fb: List[str] = []
    if length_score < 1.0:
        fb.append("About section is short; expand to ≥600 characters.")
    if quantified < 1.0:
        fb.append("About section lacks quantified achievements.")
    if keyword_score < 0.5:
        fb.append("About section under-uses target-role keywords.")
    return round(score, 3), fb


def _score_experience(profile: LinkedInProfile, role_kw: Set[str]) -> Tuple[float, int, List[str]]:
    items = profile.experience or []
    if not items:
        return 0.0, 0, ["No experience entries listed."]
    total = 0.0
    quant_total = 0
    for item in items:
        desc = item.description or ""
        verbs = sum(1 for v in _ACTION_VERBS if v in desc.lower())
        verb_score = min(1.0, verbs / 3)
        nums = len(_NUMBER_RE.findall(desc))
        quant_total += nums
        quant_score = min(1.0, nums / 2)
        keyword_overlap = (
            len(set(_content_tokens(desc)) & role_kw) / max(1, len(role_kw))
            if role_kw else 0.0
        )
        kw_score = min(1.0, keyword_overlap * 3)
        total += 0.4 * verb_score + 0.3 * quant_score + 0.3 * kw_score
    avg = total / len(items)
    fb: List[str] = []
    if avg < 0.5:
        fb.append("Experience descriptions need more action verbs and metrics.")
    if quant_total == 0:
        fb.append("No quantified outcomes detected anywhere in experience.")
    return round(avg, 3), quant_total, fb


def _score_skills(skills: Iterable[str], role_kw: Set[str]) -> Tuple[float, List[str]]:
    skills_list = [s for s in (skills or []) if s.strip()]
    if not skills_list:
        return 0.0, ["No skills listed (LinkedIn rewards 30+ skills)."]
    count_score = min(1.0, len(skills_list) / 30)
    tokens = set(_content_tokens(" ".join(skills_list)))
    overlap_score = (
        min(1.0, (len(tokens & role_kw) / max(1, len(role_kw))) * 3)
        if role_kw else 0.0
    )
    score = 0.5 * count_score + 0.5 * overlap_score
    fb: List[str] = []
    if count_score < 1.0:
        fb.append(f"Listed {len(skills_list)} skills; LinkedIn allows up to 50.")
    if overlap_score < 0.5:
        fb.append("Skills list under-represents target role.")
    return round(score, 3), fb


# ─── public API ─────────────────────────────────────────────────────

def score_section(section: str, text: str, target_role: str) -> Tuple[float, List[str]]:
    """Score a single text blob — used to compute before/after deltas."""
    role_kw = _role_keywords(target_role)
    if section == "headline":
        return _score_headline(text, role_kw)
    if section == "about":
        return _score_about(text, role_kw)
    raise ValueError(f"Unsupported section: {section}")


def score_profile(profile: LinkedInProfile, target_role: str) -> ProfileScore:
    role_kw = _role_keywords(target_role)
    h_score, h_fb = _score_headline(profile.headline, role_kw)
    a_score, a_fb = _score_about(profile.about, role_kw)
    e_score, quantified, e_fb = _score_experience(profile, role_kw)
    s_score, s_fb = _score_skills(profile.skills, role_kw)

    all_text = " ".join([
        profile.headline, profile.about,
        *(item.description for item in profile.experience or []),
        " ".join(profile.skills or []),
    ])
    text_tokens = set(_content_tokens(all_text))
    density = (
        len(text_tokens & role_kw) / max(1, len(role_kw)) if role_kw else 0.0
    )

    overall = round(
        0.20 * h_score + 0.30 * a_score + 0.30 * e_score
        + 0.10 * s_score + 0.10 * min(1.0, density * 2),
        3,
    )

    feedback = h_fb + a_fb + e_fb + s_fb

    return ProfileScore(
        overall=overall,
        headline=h_score,
        about=a_score,
        experience=e_score,
        skills=s_score,
        keyword_density=round(min(1.0, density), 3),
        quantified_achievements=quantified,
        feedback=feedback[:12],
    )
