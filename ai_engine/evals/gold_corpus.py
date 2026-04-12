"""
Gold Evaluation Corpus — curated test cases for benchmarking agent quality.

Each GoldCase defines:
  - name: human-readable identifier
  - pipeline: which pipeline this tests
  - context: realistic input data (user_profile, jd_text, job_title, company)
  - expected_properties: dict of property_name → assertion_fn(output) → bool
  - failure_conditions: dict of condition_name → condition_fn(output) → bool
    (True means the condition triggered = failure)
  - scoring_rules: dict of score_name → scoring_fn(output) → float (0-1)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class GoldCase:
    """A single evaluation case with inputs and expected outputs."""
    name: str
    pipeline: str
    context: dict[str, Any]
    expected_properties: dict[str, Callable[[dict], bool]] = field(default_factory=dict)
    failure_conditions: dict[str, Callable[[dict], bool]] = field(default_factory=dict)
    scoring_rules: dict[str, Callable[[dict], float]] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
#  Shared test profiles
# ═══════════════════════════════════════════════════════════════════════

_SENIOR_ENGINEER_PROFILE = {
    "name": "Jordan Chen",
    "title": "Senior Software Engineer",
    "summary": "8 years of full-stack development experience specializing in Python and cloud architecture.",
    "skills": [
        {"name": "Python"}, {"name": "TypeScript"}, {"name": "React"},
        {"name": "AWS"}, {"name": "Docker"}, {"name": "PostgreSQL"},
        {"name": "FastAPI"}, {"name": "Redis"}, {"name": "Terraform"},
        {"name": "Kubernetes"},
    ],
    "experience": [
        {
            "title": "Senior Software Engineer",
            "company": "TechFlow Inc",
            "start_date": "2021-01",
            "end_date": "present",
            "description": (
                "Led migration of monolith to microservices architecture serving 2M daily active users. "
                "Reduced API latency by 40% through caching strategies and database optimization. "
                "Mentored team of 4 junior developers through code reviews and pair programming."
            ),
        },
        {
            "title": "Software Engineer",
            "company": "DataPulse",
            "start_date": "2018-06",
            "end_date": "2020-12",
            "description": (
                "Built real-time data processing pipeline handling 500K events/minute using Python and Kafka. "
                "Designed RESTful APIs consumed by 15 internal teams. "
                "Implemented CI/CD pipeline reducing deployment time from 2 hours to 15 minutes."
            ),
        },
        {
            "title": "Junior Developer",
            "company": "StartupHub",
            "start_date": "2016-03",
            "end_date": "2018-05",
            "description": "Developed e-commerce platform features using Django and React. Wrote unit tests achieving 85% coverage.",
        },
    ],
    "education": [
        {"degree": "B.S. Computer Science", "institution": "University of Washington", "year": "2016"},
    ],
    "certifications": [
        {"name": "AWS Solutions Architect Associate"},
        {"name": "Certified Kubernetes Administrator"},
    ],
}

_FINTECH_JD = """
Senior Backend Engineer — FinanceForward (Series B, $45M raised)

We're looking for a Senior Backend Engineer to join our core platform team.

Requirements:
- 5+ years of backend development experience
- Strong proficiency in Python and Go
- Experience with distributed systems and microservices
- PostgreSQL and Redis expertise
- AWS or GCP cloud infrastructure
- CI/CD pipeline experience
- Experience with event-driven architectures (Kafka, RabbitMQ)

Nice to have:
- Kubernetes and container orchestration
- Terraform or Pulumi for IaC
- Experience in fintech or regulated industries
- GraphQL API experience

What you'll do:
- Design and build scalable APIs handling millions of financial transactions
- Lead technical design sessions and mentor junior engineers
- Build real-time fraud detection pipeline
- Optimize database performance for high-throughput workloads
"""

_DATA_SCIENTIST_PROFILE = {
    "name": "Priya Sharma",
    "title": "Data Scientist",
    "skills": [
        {"name": "Python"}, {"name": "R"}, {"name": "SQL"},
        {"name": "TensorFlow"}, {"name": "scikit-learn"}, {"name": "Pandas"},
        {"name": "Tableau"}, {"name": "Spark"},
    ],
    "experience": [
        {
            "title": "Data Scientist",
            "company": "AnalyticsCo",
            "start_date": "2020-01",
            "end_date": "present",
            "description": "Built ML models for customer churn prediction achieving 92% accuracy. Processed 50TB datasets using Spark.",
        },
        {
            "title": "Data Analyst",
            "company": "RetailMax",
            "start_date": "2018-06",
            "end_date": "2019-12",
            "description": "Created executive dashboards in Tableau. Conducted A/B tests increasing conversion by 15%.",
        },
    ],
    "education": [
        {"degree": "M.S. Statistics", "institution": "Stanford University", "year": "2018"},
    ],
    "certifications": [],
}


# ═══════════════════════════════════════════════════════════════════════
#  Gold cases
# ═══════════════════════════════════════════════════════════════════════

GOLD_CASES: list[GoldCase] = [
    # ── Case 1: CV Generation (standard) ──
    GoldCase(
        name="cv_senior_engineer_fintech",
        pipeline="cv_generation",
        context={
            "user_profile": _SENIOR_ENGINEER_PROFILE,
            "jd_text": _FINTECH_JD,
            "job_title": "Senior Backend Engineer",
            "company": "FinanceForward",
        },
        expected_properties={
            "jd_extracts_python": lambda o: "python" in [
                k.lower() for k in o.get("jd_parsed", {}).get("top_keywords", [])
            ],
            "profile_extracts_skills": lambda o: len(
                o.get("evidence", {}).get("skills", [])
            ) >= 8,
            "profile_extracts_companies": lambda o: "TechFlow Inc" in (
                o.get("evidence", {}).get("companies", [])
            ),
            "keyword_overlap_nonzero": lambda o: (
                o.get("keyword_overlap", {}).get("match_ratio", 0) > 0.1
            ),
            "claims_extracted": lambda o: (
                o.get("claims", {}).get("total_claims_found", 0) >= 2
            ),
        },
        failure_conditions={
            "no_jd_keywords": lambda o: len(
                o.get("jd_parsed", {}).get("top_keywords", [])
            ) == 0,
            "empty_evidence": lambda o: (
                o.get("evidence", {}).get("experience_count", 0) == 0
            ),
        },
        scoring_rules={
            "evidence_richness": lambda o: min(1.0, (
                len(o.get("evidence", {}).get("skills", []))
                + len(o.get("evidence", {}).get("companies", []))
                + len(o.get("evidence", {}).get("certifications", []))
            ) / 15),
            "keyword_depth": lambda o: min(1.0, len(
                o.get("jd_parsed", {}).get("top_keywords", [])
            ) / 10),
        },
    ),

    # ── Case 2: Cover Letter ──
    GoldCase(
        name="cover_letter_senior_engineer",
        pipeline="cover_letter",
        context={
            "user_profile": _SENIOR_ENGINEER_PROFILE,
            "jd_text": _FINTECH_JD,
            "job_title": "Senior Backend Engineer",
            "company": "FinanceForward",
        },
        expected_properties={
            "has_keyword_overlap": lambda o: (
                o.get("keyword_overlap", {}).get("match_ratio", 0) > 0
            ),
            "evidence_has_titles": lambda o: len(
                o.get("evidence", {}).get("titles", [])
            ) >= 2,
        },
        failure_conditions={
            "zero_overlap": lambda o: (
                o.get("keyword_overlap", {}).get("match_ratio", 0) == 0
                and bool(o.get("keyword_overlap"))
            ),
        },
        scoring_rules={
            "fit_score": lambda o: o.get("keyword_overlap", {}).get("match_ratio", 0),
        },
    ),

    # ── Case 3: ATS Scanner ──
    GoldCase(
        name="ats_scan_fintech",
        pipeline="ats_scanner",
        context={
            "user_profile": _SENIOR_ENGINEER_PROFILE,
            "jd_text": _FINTECH_JD,
            "job_title": "Senior Backend Engineer",
            "company": "FinanceForward",
        },
        expected_properties={
            "identifies_missing_go": lambda o: "go" in [
                k.lower() for k in o.get("keyword_overlap", {}).get("missing_from_document", [])
            ],
            "identifies_matched_python": lambda o: "python" in [
                k.lower() for k in o.get("keyword_overlap", {}).get("matched_keywords", [])
            ],
            "readability_computed": lambda o: (
                o.get("readability", {}).get("total_words", 0) > 0
            ),
        },
        failure_conditions={},
        scoring_rules={
            "gap_detection": lambda o: min(1.0, len(
                o.get("keyword_overlap", {}).get("missing_from_document", [])
            ) / 5),
        },
    ),

    # ── Case 4: Different profile (Data Scientist) ──
    GoldCase(
        name="cv_data_scientist_career_change",
        pipeline="cv_generation",
        context={
            "user_profile": _DATA_SCIENTIST_PROFILE,
            "jd_text": _FINTECH_JD,  # Applying to backend role
            "job_title": "Senior Backend Engineer",
            "company": "FinanceForward",
        },
        expected_properties={
            "profile_has_skills": lambda o: len(
                o.get("evidence", {}).get("skills", [])
            ) >= 5,
            "detects_skill_gaps": lambda o: len(
                o.get("keyword_overlap", {}).get("missing_from_document", [])
            ) >= 3,  # Should miss many backend-specific keywords
        },
        failure_conditions={
            "claims_but_no_match": lambda o: (
                o.get("claims", {}).get("total_claims_found", 0) > 5
                and o.get("claim_matching", {}).get("match_rate", 0) == 0
            ),
        },
        scoring_rules={
            "gap_identification": lambda o: min(1.0, len(
                o.get("keyword_overlap", {}).get("missing_from_document", [])
            ) / 8),
        },
    ),
]
