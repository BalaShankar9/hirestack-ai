"""Tests for AIM source embeddings & RAG retriever (PR m6-pr19)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from app.services.aim.source_embeddings import (
    EMBEDDING_DIMENSIONS,
    SourceEmbeddingsService,
    build_embedding_input,
)
from ai_engine.rag.source_retriever import (
    DEFAULT_TOP_K,
    RetrievedSource,
    SourceRetriever,
    format_sources_for_prompt,
)


def test_build_embedding_input_concatenation_and_truncation() -> None:
    assert build_embedding_input("My Title", "  Some summary text. ") == (
        "My Title\n\nSome summary text."
    )
    assert build_embedding_input("Only title", None) == "Only title"
    assert build_embedding_input(None, "Only summary") == "Only summary"
    assert build_embedding_input("", "   ") == ""
    assert len(build_embedding_input("t", "x" * 20_000)) == 8_000


class _FakeSupabaseQuery:
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink
        self._payload: dict[str, Any] | None = None

    def update(self, payload: dict[str, Any]) -> "_FakeSupabaseQuery":
        self._payload = payload
        return self

    def eq(self, column: str, value: Any) -> "_FakeSupabaseQuery":
        assert column == "id" and self._payload is not None
        self._sink.append({"id": value, **self._payload})
        return self

    def execute(self) -> dict[str, Any]:
        return {"status": 204}


class _FakeSupabase:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    def table(self, name: str) -> _FakeSupabaseQuery:
        assert name == "aim_sources"
        return _FakeSupabaseQuery(self.writes)


@pytest.mark.asyncio
async def test_embed_source_persists_vector_and_metadata() -> None:
    sb = _FakeSupabase()
    seen: list[str] = []

    async def embedder(text: str) -> list[float]:
        seen.append(text)
        return [0.1] * EMBEDDING_DIMENSIONS

    svc = SourceEmbeddingsService(supabase=sb, embedder=embedder)
    result = await svc.embed_source(
        source_id="src-1",
        title="Quantum entanglement primer",
        extracted_summary="A short summary of QE.",
    )

    assert result is not None
    assert result.source_id == "src-1"
    assert result.dimensions == EMBEDDING_DIMENSIONS
    assert result.model == "text-embedding-3-small"
    assert isinstance(result.embedded_at, datetime)
    assert seen == ["Quantum entanglement primer\n\nA short summary of QE."]
    assert len(sb.writes) == 1 and sb.writes[0]["id"] == "src-1"
    assert sb.writes[0]["embedding_model"] == "text-embedding-3-small"
    assert len(sb.writes[0]["embedding"]) == EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_embed_source_skips_empty_and_rejects_bad_dim() -> None:
    sb = _FakeSupabase()

    async def never(text: str) -> list[float]:  # pragma: no cover
        raise AssertionError("should not be called")

    svc = SourceEmbeddingsService(supabase=sb, embedder=never)
    assert await svc.embed_source(
        source_id="x", title=None, extracted_summary="   "
    ) is None
    assert sb.writes == []

    async def short(text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    bad = SourceEmbeddingsService(supabase=sb, embedder=short)
    with pytest.raises(ValueError, match="1536-dim"):
        await bad.embed_source(source_id="x", title="t", extracted_summary="s")
    assert sb.writes == []


class _FakeRpcResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeRpc:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> "_FakeRpc":
        self.calls.append((name, params))
        return self

    def execute(self) -> _FakeRpcResponse:
        return _FakeRpcResponse(self._data)


@pytest.mark.asyncio
async def test_retriever_search_returns_scored_sources() -> None:
    fake = _FakeRpc(
        data=[
            {
                "id": "src-A", "title": "Source A",
                "extracted_summary": "Summary A",
                "relevant_quotes": ["Quote A1", "Quote A2"],
                "reliability_tier": "tier_1", "distance": 0.1,
            },
            {
                "id": "src-B", "title": "Source B",
                "extracted_summary": "Summary B",
                "relevant_quotes": "single-quote-string",
                "reliability_tier": "tier_3", "distance": 0.5,
            },
        ]
    )

    async def embedder(text: str) -> list[float]:
        return [0.0] * EMBEDDING_DIMENSIONS

    retriever = SourceRetriever(supabase=fake, embedder=embedder)
    results = await retriever.search(
        assignment_id="asgn-1", query="thesis on QE", top_k=DEFAULT_TOP_K
    )

    assert [r.id for r in results] == ["src-A", "src-B"]
    assert results[0].score == pytest.approx(0.9, rel=1e-3)
    assert results[0].relevant_quotes == ["Quote A1", "Quote A2"]
    assert results[1].relevant_quotes == ["single-quote-string"]
    name, params = fake.calls[0]
    assert name == "aim_sources_match"
    assert params["p_assignment_id"] == "asgn-1"
    assert params["p_limit"] == DEFAULT_TOP_K
    assert len(params["p_query_embedding"]) == EMBEDDING_DIMENSIONS


@pytest.mark.asyncio
async def test_retriever_blank_query_and_clamping() -> None:
    fake = _FakeRpc(data=[])

    async def embedder(text: str) -> list[float]:
        return [0.0] * EMBEDDING_DIMENSIONS

    retriever = SourceRetriever(supabase=fake, embedder=embedder)
    assert await retriever.search(assignment_id="a", query="   ") == []

    await retriever.search(assignment_id="a", query="q", top_k=999)
    assert fake.calls[-1][1]["p_limit"] == 50
    await retriever.search(assignment_id="a", query="q", top_k=0)
    assert fake.calls[-1][1]["p_limit"] == 1


def test_format_sources_for_prompt() -> None:
    out = format_sources_for_prompt(
        [
            RetrievedSource(
                id="x", title="A Paper", summary="Summary text",
                relevant_quotes=["q1", "q2", "q3", "q4"],
                reliability_tier="tier_1", score=0.83,
            )
        ]
    )
    assert out.startswith("## Retrieved sources (RAG)")
    assert "**A Paper**" in out
    assert "tier_1" in out
    assert "relevance 0.83" in out
    assert out.count("Quote:") == 3
    assert format_sources_for_prompt([]) == ""
