"""Shared OpenAI embedder factory for AIM (PR m6-pr21).

Centralises the `text-embedding-3-small` AsyncOpenAI wiring so the
consumer (`aim_source_embed`), the backfill script, and the live
section retriever path all use the same embedder shape.

Returns an `Embedder` — `Callable[[str], Awaitable[list[float]]]` —
that the `SourceRetriever` and `SourceEmbeddingsService` already
expect. Lazy-imports the OpenAI SDK so module import stays cheap and
test environments without the real key don't fail at collection time.
"""
from __future__ import annotations

from typing import Awaitable, Callable

EMBEDDING_MODEL = "text-embedding-3-small"

Embedder = Callable[[str], Awaitable[list[float]]]


def build_openai_embedder(model: str = EMBEDDING_MODEL) -> Embedder:
    """Construct a singleton-capable AsyncOpenAI embedder.

    The returned coroutine reuses one `AsyncOpenAI` instance per
    factory call. Callers (consumer / service) typically build it once
    per process startup and pass it down.
    """
    from openai import AsyncOpenAI  # type: ignore[import-not-found]

    client = AsyncOpenAI()

    async def _embed(text: str) -> list[float]:
        resp = await client.embeddings.create(model=model, input=text)
        return list(resp.data[0].embedding)

    return _embed


__all__ = ["build_openai_embedder", "EMBEDDING_MODEL", "Embedder"]
