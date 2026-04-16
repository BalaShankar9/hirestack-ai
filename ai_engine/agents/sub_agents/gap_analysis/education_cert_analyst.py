"""
EducationCertAnalyst — education and certification gap assessment.

Compares the candidate's educational background and certifications
against benchmark requirements:
  • Degree level (BSc, MSc, PhD)
  • Field of study alignment
  • Required certifications (AWS, GCP, PMP, etc.)
  • Continuing education signals

Pure deterministic analysis — no LLM call.
"""
from __future__ import annotations

import logging
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = logging.getLogger(__name__)

# Degree level hierarchy
_DEGREE_LEVELS = {
    "high school": 0, "ged": 0, "secondary": 0,
    "associate": 1, "diploma": 1,
    "bachelor": 2, "bsc": 2, "ba": 2, "beng": 2, "btech": 2, "undergraduate": 2,
    "master": 3, "msc": 3, "ma": 3, "mba": 3, "meng": 3, "ms": 3, "postgraduate": 3,
    "phd": 4, "doctorate": 4, "dphil": 4,
}

# Common certification families
_CERT_FAMILIES = {
    "aws": ["aws certified", "aws solutions architect", "aws developer", "aws devops", "aws sysops", "aws cloud practitioner"],
    "gcp": ["gcp certified", "google cloud", "google professional", "google associate cloud"],
    "azure": ["azure certified", "az-900", "az-104", "az-204", "az-305", "az-400", "azure fundamentals", "azure administrator", "azure developer", "azure solutions architect"],
    "kubernetes": ["cka", "ckad", "cks", "certified kubernetes"],
    "security": ["cissp", "cism", "ceh", "comptia security+", "security+", "oscp"],
    "project": ["pmp", "prince2", "scrum master", "csm", "psm", "safe agilist"],
    "data": ["databricks", "snowflake", "google data engineer", "aws data analytics"],
    "ml": ["tensorflow", "google ml engineer", "aws machine learning", "deep learning specialization"],
}


class EducationCertAnalyst(SubAgent):
    """Deterministic education and certification gap analysis."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="education_cert_analyst", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        user_profile = context.get("user_profile", {})
        benchmark = context.get("benchmark", {})

        user_education = user_profile.get("education", [])
        user_certs = user_profile.get("certifications", [])
        ideal_education = benchmark.get("ideal_education", [])
        ideal_certs = benchmark.get("ideal_certifications", [])
        ideal_profile = benchmark.get("ideal_profile", {})

        # ── Education analysis ──────────────────────────────────
        user_max_degree, user_degree_level = self._highest_degree(user_education)
        required_degree = ideal_profile.get("education_level") or ideal_profile.get("minimum_education") or ""
        required_level = self._parse_degree_level(required_degree)
        # Also check ideal_education list
        for edu in ideal_education:
            lvl = self._parse_degree_level(edu.get("level") or edu.get("degree") or "")
            required_level = max(required_level, lvl)

        edu_gap = max(0, required_level - user_degree_level)
        edu_score = 100 if edu_gap == 0 else max(0, 100 - edu_gap * 25)

        # Field of study alignment
        required_fields = set()
        for edu in ideal_education:
            field = (edu.get("field") or edu.get("area") or "").lower()
            if field:
                required_fields.add(field)
        if ideal_profile.get("field_of_study"):
            required_fields.add(ideal_profile["field_of_study"].lower())

        user_fields = set()
        for edu in user_education:
            for key in ["field", "major", "area", "degree"]:
                f = (edu.get(key) or "").lower()
                if f:
                    user_fields.add(f)

        field_match = bool(required_fields & user_fields) or not required_fields
        if not field_match:
            # Fuzzy: check if any required field keyword appears in user fields
            for rf in required_fields:
                for uf in user_fields:
                    if rf in uf or uf in rf:
                        field_match = True
                        break

        # ── Certification analysis ──────────────────────────────
        user_cert_names = set()
        for cert in user_certs:
            name = (cert.get("name") or cert.get("title") or cert if isinstance(cert, str) else "").lower()
            if name:
                user_cert_names.add(name)

        cert_gaps: list[dict] = []
        cert_matches: list[str] = []

        for ideal_cert in ideal_certs:
            cert_name = (ideal_cert.get("name") or ideal_cert.get("title") or (ideal_cert if isinstance(ideal_cert, str) else "")).strip()
            if not cert_name:
                continue

            importance = (ideal_cert.get("importance") or "recommended").lower() if isinstance(ideal_cert, dict) else "recommended"
            matched = self._cert_match(cert_name.lower(), user_cert_names)

            if matched:
                cert_matches.append(cert_name)
            else:
                severity = "major" if "required" in importance or "critical" in importance else "moderate"
                cert_gaps.append({
                    "certification": cert_name,
                    "importance": importance,
                    "gap_severity": severity,
                    "recommendation": self._cert_recommendation(cert_name),
                    "estimated_time": self._cert_time_estimate(cert_name),
                })

        cert_total = len(ideal_certs)
        cert_score = int((len(cert_matches) / max(cert_total, 1)) * 100) if cert_total else 85

        # ── Build education gaps list ───────────────────────────
        education_gaps: list[dict] = []

        if edu_gap > 0:
            level_names = {0: "High School", 1: "Associate", 2: "Bachelor's", 3: "Master's", 4: "PhD"}
            education_gaps.append({
                "area": "Degree Level",
                "required": level_names.get(required_level, f"Level {required_level}"),
                "current": user_max_degree or "Not specified",
                "gap_severity": "major" if edu_gap >= 2 else "moderate",
                "recommendation": self._edu_recommendation(user_degree_level, required_level),
            })

        if not field_match and required_fields:
            education_gaps.append({
                "area": "Field of Study",
                "required": ", ".join(required_fields),
                "current": ", ".join(user_fields) if user_fields else "Not specified",
                "gap_severity": "moderate",
                "recommendation": "Consider relevant coursework, bootcamps, or a specialized certificate in the target field.",
            })

        # ── Overall score ───────────────────────────────────────
        overall_score = int(edu_score * 0.5 + cert_score * 0.5)
        confidence = 0.6 if (user_education or user_certs) else 0.3

        return SubAgentResult(
            agent_name=self.name,
            data={
                "education_score": edu_score,
                "certification_score": cert_score,
                "overall_score": overall_score,
                "education_gaps": education_gaps,
                "certification_gaps": cert_gaps[:10],
                "cert_matches": cert_matches,
                "education_analysis": {
                    "highest_degree": user_max_degree or "Not specified",
                    "degree_level": user_degree_level,
                    "required_level": required_level,
                    "field_match": field_match,
                    "user_fields": list(user_fields),
                    "required_fields": list(required_fields),
                },
                "summary": self._build_summary(edu_score, cert_score, user_max_degree, cert_matches, cert_gaps),
            },
            confidence=confidence,
        )

    def _highest_degree(self, education: list[dict]) -> tuple[str, int]:
        """Find the highest degree level in user education."""
        max_level = 0
        max_name = ""
        for edu in education:
            for key in ["degree", "level", "title"]:
                text = (edu.get(key) or "").lower()
                if text:
                    level = self._parse_degree_level(text)
                    if level > max_level:
                        max_level = level
                        max_name = edu.get(key) or text
        return max_name, max_level

    def _parse_degree_level(self, text: str) -> int:
        text = text.lower().strip()
        for keyword, level in sorted(_DEGREE_LEVELS.items(), key=lambda x: -x[1]):
            if keyword in text:
                return level
        return 0

    def _cert_match(self, target: str, user_certs_lower: set[str]) -> bool:
        """Check if user has a matching certification (exact or fuzzy)."""
        # Exact match
        if target in user_certs_lower:
            return True
        # Substring match either way
        for uc in user_certs_lower:
            if target in uc or uc in target:
                return True
        # Family-level match
        for family, aliases in _CERT_FAMILIES.items():
            target_in_family = any(a in target for a in aliases) or family in target
            if target_in_family:
                user_in_family = any(any(a in uc for a in aliases) or family in uc for uc in user_certs_lower)
                if user_in_family:
                    return True
        return False

    def _cert_recommendation(self, cert_name: str) -> str:
        cert_lower = cert_name.lower()
        for family, aliases in _CERT_FAMILIES.items():
            if any(a in cert_lower for a in aliases) or family in cert_lower:
                return f"Pursue {cert_name} certification — start with official study guides and practice exams."
        return f"Obtain {cert_name} to strengthen your candidacy for this role."

    def _cert_time_estimate(self, cert_name: str) -> str:
        cert_lower = cert_name.lower()
        # Heavy certs
        if any(k in cert_lower for k in ["cissp", "solutions architect professional", "phd", "pmp"]):
            return "3-6 months preparation"
        if any(k in cert_lower for k in ["associate", "fundamentals", "practitioner", "az-900"]):
            return "2-4 weeks preparation"
        return "1-3 months preparation"

    def _edu_recommendation(self, current: int, required: int) -> str:
        if required >= 4:
            return "A PhD is typically required — consider research-oriented programs or demonstrate equivalent research impact."
        if required >= 3:
            return "A Master's degree would strengthen candidacy — consider online MSc programs or demonstrate equivalent depth through published work."
        if required >= 2:
            return "A Bachelor's degree is expected — bootcamp or equivalent experience may substitute, but highlight depth of knowledge."
        return "Formal education requirement is modest — focus on demonstrating practical skills and certifications."

    def _build_summary(self, edu_score: int, cert_score: int, degree: str, matches: list, gaps: list) -> str:
        parts = []
        if degree:
            parts.append(f"Highest degree: {degree} (score: {edu_score}%).")
        else:
            parts.append(f"Education score: {edu_score}%.")
        if matches:
            parts.append(f"{len(matches)} certification(s) matched.")
        if gaps:
            parts.append(f"{len(gaps)} certification gap(s) found.")
        return " ".join(parts)
