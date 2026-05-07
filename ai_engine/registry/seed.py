"""Initial tool catalog + grants for ``ai_tools`` (PR m5-pr14)."""

from __future__ import annotations

from typing import Any

INITIAL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_user_history",
        "code_ref": "ai_engine.agents.tools:search_user_history",
        "description": "Look up the user's prior generations and uploads.",
        "input_schema": {"type": "object", "required": ["query"],
                          "properties": {"query": {"type": "string"},
                                          "limit": {"type": "integer"}}},
        "output_schema": {"type": "array"},
        "timeout_ms": 5_000,
    },
    {
        "name": "extract_claims",
        "code_ref": "ai_engine.agents.tools:extract_claims",
        "description": "Pull factual claims out of a passage of text.",
        "input_schema": {"type": "object", "required": ["text"],
                          "properties": {"text": {"type": "string"}}},
        "output_schema": {"type": "array"},
        "timeout_ms": 10_000,
    },
]

# Default grants — wildcard '*' means every agent.
INITIAL_GRANTS: list[tuple[str, str]] = [
    ("*", "search_user_history"),
    ("*", "extract_claims"),
]


def seed_rows() -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Return (tools, grants) ready for upsert."""
    return list(INITIAL_TOOLS), list(INITIAL_GRANTS)
