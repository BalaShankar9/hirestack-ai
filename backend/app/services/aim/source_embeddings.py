"""AIM source embeddings (PR m6-pr19). Behind ff_aim_rag.

Embeds `title + extracted_summary` (truncated to 8K chars) and
upserts the vector + provenance columns. Embedder is injected so
tests can substitute deterministic vectors.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 1536
DEFAULT_MODEL = "text-embedding-3-small"
MAX_INPUT_CHARS = 8_000


# ── Pure helpers ────────────────────────────────────────────────────────


def build_embedding_input(
    title: Optional[str], extracted_summary: Optional[str]
) -> str:
    """Concatenate title + summary, normalised and truncated.

    Returns "" when both inputs are empty/None — callers should skip
    embedding such rows.
    """
    parts = [
        (title or "").strip(),
        (extracted_summary or "").strip(),
    ]
    text = "\n\n".join(p for p in parts if p)
    return text[:MAX_INPUT_CHARS]


# ── Embedder protocol ───────────────────────────────────────────────────
#
# An embedder is an async callable: (text) -> list[float] of length
# EMBEDDING_DIMENSIONS. We don't use a Protocol class so the type stays
# friendly to lambdas in tests.

Embedder = Callable[[str], Awaitable[list[float]]]


@dataclass
class EmbedResult:
    source_id: str
    model: str
    embedded_at: datetime
    dimensions: int


# ── Service ─────────────────────────────────────────────────────────────


class SourceEmbeddingsService:
    """Embed and persist a single `aim_sources` row."""

    def __init__(
        self,
        *,
        supabase: Any,
        embedder: Embedder,
        model: str = DEFAULT_MODEL,
        table_name: str = "aim_sources",
    ) -> None:
        self._supabase = supabase
        self._embedder = embedder
        self._model = model
        self._table_name = table_name

    async def embed_source(
        self, *, source_id: str, title: Optional[str], extracted_summary: Optional[str]
    ) -> Optional[EmbedResult]:
        text = build_embedding_input(title, extracted_summary)
        if not text:
            logger.info(
                "aim_source_embeddings.skip_empty",
                extra={"source_id": source_id},
            )
            return None

        vector = await self._embedder(text)
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSIONS}-dim vector, got {len(vector)}"
            )

        embedded_at = datetime.now(timezone.utc)
        self._supabase.table(self._table_name).update(
            {
                "embedding": vector,
                "embedding_model": self._model,
                "embedded_at": embedded_at.isoformat(),
            }
        ).eq("id", source_id).execute()

        logger.info(
            "aim_source_embeddings.persisted",
            extra={
                "source_id": source_id,
                "model": self._model,
                "dimensions": len(vector),
            },
        )
        return EmbedResult(
            source_id=source_id,
            model=self._model,
            embedded_at=embedded_at,
            dimensions=len(vector),
        )


__all__ = [
    "DEFAULT_MODEL",
    "EMBEDDING_DIMENSIONS",
    "MAX_INPUT_CHARS",
    "EmbedResult",
    "Embedder",
    "SourceEmbeddingsService",
    "build_embedding_input",
]
