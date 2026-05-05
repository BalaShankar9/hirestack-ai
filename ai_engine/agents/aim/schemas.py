"""
AIM — Pydantic-style schemas (OpenAPI-3 dicts for Gemini response_schema).

Every schema includes ``confidence`` (0..1) and an optional ``version`` so
agent outputs are versionable end to end.
"""
from __future__ import annotations

# ── Parser ─────────────────────────────────────────────────────────────
RUBRIC_CRITERION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "criterion": {"type": "string"},
        "weight": {"type": "number"},        # percent, 0..100
        "descriptors": {                     # band descriptors keyed by grade band
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
    "required": ["criterion", "weight"],
}

PARSER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "directive": {"type": "string"},                          # analyse|evaluate|discuss|critique|...
        "academic_level": {"type": "string"},                     # ug|pg|mba|phd|other
        "referencing_style": {"type": "string"},                  # harvard|apa|mla|chicago|ieee|other
        "word_count": {"type": "integer"},
        "rubric_breakdown": {"type": "array", "items": RUBRIC_CRITERION_SCHEMA},
        "hidden_expectations": {"type": "array", "items": {"type": "string"}},
        "clarification_questions": {                              # surfaced when confidence < 0.9
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["question"],
            },
        },
        "confidence": {"type": "number"},                         # 0..1
    },
    "required": ["directive", "rubric_breakdown", "confidence"],
}

# ── Recon ──────────────────────────────────────────────────────────────
RECON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "what_its_really_asking": {"type": "string"},
        "mark_loss_patterns": {                                   # top 5
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "why_it_costs_marks": {"type": "string"},
                },
                "required": ["pattern", "why_it_costs_marks"],
            },
        },
        "distinction_strategy": {"type": "string"},
        "section_strategy": {                                     # per-section scoring logic
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_title": {"type": "string"},
                    "scoring_logic": {"type": "string"},
                    "criteria_targeted": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["section_title", "scoring_logic"],
            },
        },
        "structure": {                                            # outline used to seed aim_sections
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "key_argument": {"type": "string"},
                    "word_limit": {"type": "integer"},
                    "order_index": {"type": "integer"},
                },
                "required": ["title", "purpose", "word_limit", "order_index"],
            },
        },
        "confidence": {"type": "number"},
    },
    "required": [
        "what_its_really_asking",
        "mark_loss_patterns",
        "distinction_strategy",
        "structure",
        "confidence",
    ],
}

# ── Writer ─────────────────────────────────────────────────────────────
# Writer always returns a single section. The 5-part block (claim \u2192 explanation
# \u2192 evidence suggestion \u2192 counterpoint \u2192 micro-conclusion) is enforced via prompt
# and reviewer; we keep the schema light so the model can flow prose naturally.
WRITER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},                            # full section prose
        "blocks": {                                               # internal structural breakdown
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "explanation": {"type": "string"},
                    "evidence_suggestion": {"type": "string"},   # SOURCE TYPE only \u2014 never fabricate citations
                    "counterpoint": {"type": "string"},
                    "micro_conclusion": {"type": "string"},
                },
                "required": ["claim", "explanation", "micro_conclusion"],
            },
        },
        "word_count": {"type": "integer"},
        "confidence": {"type": "number"},
    },
    "required": ["content", "blocks", "confidence"],
}

# ── Reviewer ───────────────────────────────────────────────────────────
REVIEWER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "sub_scores": {
            "type": "object",
            "properties": {
                "directive_alignment": {"type": "number"},
                "analytical_depth": {"type": "number"},
                "academic_tone": {"type": "number"},
                "originality": {"type": "number"},
                "structure": {"type": "number"},
            },
            "required": [
                "directive_alignment",
                "analytical_depth",
                "academic_tone",
                "originality",
                "structure",
            ],
        },
        "ranked_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string"},               # critical|high|medium|low
                    "dimension": {"type": "string"},
                    "issue": {"type": "string"},
                    "where": {"type": "string"},                  # quote/section ref
                    "suggested_fix": {"type": "string"},
                    "expected_gain": {"type": "number"},
                },
                "required": ["severity", "dimension", "issue", "suggested_fix"],
            },
        },
        "verdict": {"type": "string"},                            # pass | revise | reject
        "confidence": {"type": "number"},
    },
    "required": ["sub_scores", "ranked_issues", "verdict", "confidence"],
}

# ── Grade Predictor ────────────────────────────────────────────────────
GRADE_PREDICTOR_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "predicted_grade_low": {"type": "integer"},               # 0..100
        "predicted_grade_high": {"type": "integer"},
        "band": {"type": "string"},                               # e.g. "2:1" / "Distinction" / "B"
        "per_criterion": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "score": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": ["criterion", "score", "reasoning"],
            },
        },
        "feedback": {
            "type": "object",
            "properties": {
                "strengths": {"type": "array", "items": {"type": "string"}},
                "weaknesses": {"type": "array", "items": {"type": "string"}},
                "improvement_priorities": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["strengths", "weaknesses", "improvement_priorities"],
        },
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "predicted_grade_low",
        "predicted_grade_high",
        "band",
        "per_criterion",
        "feedback",
        "confidence",
    ],
}

# ── Fix Diagnostic ─────────────────────────────────────────────────────
FIX_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "weak_arguments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "why_weak": {"type": "string"},
                    "how_to_strengthen": {"type": "string"},
                },
                "required": ["quote", "why_weak", "how_to_strengthen"],
            },
        },
        "missing_analysis": {"type": "array", "items": {"type": "string"}},
        "structural_issues": {"type": "array", "items": {"type": "string"}},
        "rewrite_suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["before", "after", "reason"],
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["weak_arguments", "missing_analysis", "structural_issues", "confidence"],
}

__all__ = [
    "PARSER_SCHEMA",
    "RECON_SCHEMA",
    "WRITER_SCHEMA",
    "REVIEWER_SCHEMA",
    "GRADE_PREDICTOR_SCHEMA",
    "FIX_SCHEMA",
    "RUBRIC_CRITERION_SCHEMA",
]
