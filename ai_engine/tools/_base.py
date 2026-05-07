"""
Tool ABC (PR m5-pr14).

Every tool exposed through the registry implements :class:`Tool`. The
dispatcher resolves a ``code_ref`` to the class, instantiates it once,
and calls ``invoke``. Schemas live on the registry row, not on the class,
so the same code can back multiple registered variants.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Async, side-effect-aware unit of work behind a registry name."""

    name: str = ""

    @abstractmethod
    async def invoke(self, **kwargs: Any) -> Any:
        """Execute the tool. Must be idempotent if ``read_only`` is True."""

    read_only: bool = True
