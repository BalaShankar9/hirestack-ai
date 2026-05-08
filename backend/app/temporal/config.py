"""Temporal connection settings (PR m6-pr17)."""

from __future__ import annotations

import os
from dataclasses import dataclass

GENERATION_TASK_QUEUE = "hirestack-generation"


@dataclass(frozen=True)
class TemporalSettings:
    host: str
    namespace: str
    task_queue: str
    api_key: str | None
    tls: bool

    @property
    def enabled(self) -> bool:
        return bool(self.host)


def load_settings() -> TemporalSettings:
    """Pure environment read; safe to call at import time."""
    return TemporalSettings(
        host=os.getenv("TEMPORAL_HOST", ""),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", GENERATION_TASK_QUEUE),
        api_key=os.getenv("TEMPORAL_API_KEY") or None,
        tls=os.getenv("TEMPORAL_TLS", "0").lower() in ("1", "true", "yes", "on"),
    )
