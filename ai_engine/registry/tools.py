"""Tool catalog read-model (``ai_tools`` + ``ai_agent_tool_grants``)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class ToolRecord:
    """Catalog row for one tool."""

    name: str
    code_ref: str
    description: str = ""
    version: int = 1
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 15_000
    enabled: bool = True


class ToolStore(Protocol):
    """Read-only interface; tests can inject an in-memory implementation."""

    async def get(self, tool_name: str) -> Optional[ToolRecord]: ...

    async def has_grant(self, agent_name: str, tool_name: str) -> bool: ...


@dataclass
class InMemoryToolStore:
    """Test/dev implementation. Wildcard agent ``*`` grants to everyone."""

    tools: dict[str, ToolRecord] = field(default_factory=dict)
    grants: set[tuple[str, str]] = field(default_factory=set)

    async def get(self, tool_name: str) -> Optional[ToolRecord]:
        rec = self.tools.get(tool_name)
        if rec is None or not rec.enabled:
            return None
        return rec

    async def has_grant(self, agent_name: str, tool_name: str) -> bool:
        return (agent_name, tool_name) in self.grants or ("*", tool_name) in self.grants


def is_enabled() -> bool:
    """Feature flag gate. Default OFF; opt-in via env."""
    return os.getenv("FF_TOOL_REGISTRY", "0").lower() in ("1", "true", "yes", "on")
