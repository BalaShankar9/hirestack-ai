"""
Per-agent output schemas for structured Gemini responses.

These schemas are passed to complete_json(schema=...) so the model
returns validated JSON that matches the agent's contract.
Gemini's response_schema uses a subset of OpenAPI 3.0 (not JSON Schema).
"""
from __future__ import annotations

# ── Researcher output schema ───────────────────────────────────────────
RESEARCHER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "industry": {"type": "string"},
        "company_culture": {"type": "string"},
        "role_emphasis": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_format": {"type": "string"},
        "keyword_priority": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "mentions": {"type": "integer"},
                    "priority": {"type": "string"},
                },
                "required": ["keyword", "priority"],
            },
        },
        "tone_recommendation": {"type": "string"},
        "key_signals": {
            "type": "array",
            "items": {"type": "string"},
        },
        "coverage_score": {"type": "number"},
    },
    "required": [
        "industry",
        "keyword_priority",
        "key_signals",
        "coverage_score",
    ],
}


# ── Critic output schema ──────────────────────────────────────────────
CRITIC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "quality_scores": {
            "type": "object",
            "properties": {
                "impact": {"type": "number"},
                "clarity": {"type": "number"},
                "tone_match": {"type": "number"},
                "completeness": {"type": "number"},
            },
            "required": ["impact", "clarity", "tone_match", "completeness"],
        },
        "needs_revision": {"type": "boolean"},
        "feedback": {
            "type": "object",
            "properties": {
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "improvements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "critical_issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {"type": "string"},
                            "severity": {"type": "string"},
                            "issue": {"type": "string"},
                            "suggestion": {"type": "string"},
                        },
                        "required": ["section", "severity", "issue"],
                    },
                },
            },
            "required": ["strengths", "improvements", "critical_issues"],
        },
        "overall_assessment": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "quality_scores",
        "needs_revision",
        "feedback",
        "confidence",
    ],
}


# ── Optimizer output schema ────────────────────────────────────────────
OPTIMIZER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "keyword_analysis": {
            "type": "object",
            "properties": {
                "present": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "missing": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "insertion_suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string"},
                            "location": {"type": "string"},
                            "suggestion": {"type": "string"},
                        },
                        "required": ["keyword", "suggestion"],
                    },
                },
            },
            "required": ["present", "missing"],
        },
        "readability_score": {"type": "number"},
        "quantification": {
            "type": "object",
            "properties": {
                "quantified_count": {"type": "integer"},
                "vague_statements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "suggestion": {"type": "string"},
                        },
                        "required": ["text", "suggestion"],
                    },
                },
            },
            "required": ["quantified_count"],
        },
        "ats_score": {"type": "number"},
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "priority": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["type", "priority", "text"],
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["keyword_analysis", "readability_score", "suggestions", "confidence"],
}


# ── Fact-Checker output schema ─────────────────────────────────────────
FACT_CHECKER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "classification": {"type": "string"},
                    "source_reference": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["text", "classification", "confidence"],
            },
        },
        "summary": {
            "type": "object",
            "properties": {
                "verified": {"type": "integer"},
                "inferred": {"type": "integer"},
                "embellished": {"type": "integer"},
                "enhanced": {"type": "integer"},
                "fabricated": {"type": "integer"},
            },
            "required": ["verified", "fabricated"],
        },
        "fabricated_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        "overall_accuracy": {"type": "number"},
        "confidence": {"type": "number"},
    },
    "required": ["claims", "summary", "fabricated_claims", "overall_accuracy", "confidence"],
}


# ── Validator output schema ────────────────────────────────────────────
VALIDATOR_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "checks": {
            "type": "object",
            "properties": {
                "schema_compliant": {"type": "boolean"},
                "format_valid": {"type": "boolean"},
                "all_sections_present": {"type": "boolean"},
                "length_appropriate": {"type": "boolean"},
            },
            "required": [
                "schema_compliant",
                "format_valid",
                "all_sections_present",
                "length_appropriate",
            ],
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "severity": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["field", "severity", "message"],
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["valid", "checks", "issues", "confidence"],
}
