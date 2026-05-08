"""AIM source retriever (PR m6-pr19).

Wrapper around the `aim_sources_match` SQL function. Embeds the query,
calls Supabase RPC, returns top-k. score = 1 - cosine_distance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
MAX_TOP_K = 50

Embedder = Callable[[str], Awaitable[list[float]]]


@dataclass(frozen=True)
class RetrievedSource:
    id: str
    title: str
    summary: str
    relevant_quotes: list[str]
    reliability_tier: str
    score: float  # 1 - cosine_distance, in [0, 1]


def _coerce_quotes(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if item is not None]
    if isinstance(raw, str):
        return [raw]
    return []


class SourceRetriever:
    def __init__(
        self,
        *,
        supabase: Any,
        embedder: Embedder,
        rpc_name: str = "aim_sources_match",
    ) -> None:
        self._supabase = supabase
        self._embedder = embedder
        self._rpc_name = rpc_name

    async def search(
        self,
        *,
        assignment_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[RetrievedSource]:
        if not query.strip():
            return []
        k = max(1, min(int(top_k), MAX_TOP_K))
        vector = await self._embedder(query)

        rpc_response = self._supabase.rpc(
            self._rpc_name,
            {
                "p_assignment_id": assignment_id,
                "p_query_embedding": vector,
                "p_limit": k,
            },
        ).execute()

        rows: list[dict[str, Any]] = list(getattr(rpc_response, "data", None) or [])
        results: list[RetrievedSource] = []
        for row in rows:
            distance = float(row.get("distance") or 0.0)
            score = max(0.0, min(1.0, 1.0 - distance))
            results.append(
                RetrievedSource(
                    id=str(row.get("id") or ""),
                    title=str(row.get("title") or "").strip(),
                    summary=(row.get("extracted_summary") or "").strip(),
                    relevant_quotes=_coerce_quotes(row.get("relevant_quotes")),
                    reliability_tier=str(row.get("reliability_tier") or "tier_4"),
                    score=round(score, 4),
                )
            )

        logger.info(
            "aim_source_retriever.search_complete",
            extra={
                "assignment_id": assignment_id,
                "query_chars": len(query),
                "result_count": len(results),
            },
        )
        return results


def format_sources_for_prompt(
    sources: list[RetrievedSource], *, max_quote_chars: int = 280
) -> str:
    """Render retrieved sources as Markdown for prompt injection."""
    if not sources:
        return ""
    lines: list[str] = ["## Retrieved sources (RAG)"]
    for idx, src in enumerate(sources, start=1):
        title = src.title or "(untitled source)"
        lines.append(
            f"{idx}. **{title}** [{src.reliability_tier}, "
            f"relevance {src.score:.2f}]"
        )
        if src.summary:
            lines.append(f"   - Summary: {src.summary[:max_quote_chars]}")
        for quote in src.relevant_quotes[:3]:
            lines.append(f"   - Quote: \u201c{quote[:max_quote_chars]}\u201d")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_TOP_K",
    "MAX_TOP_K",
    "Embedder",
    "RetrievedSource",
    "SourceRetriever",
    "format_sources_for_prompt",
]
