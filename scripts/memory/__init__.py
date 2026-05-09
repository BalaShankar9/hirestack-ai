"""HireStack AI memory system — toolchain entry point.

This package is the persistence + retrieval layer for the project's
engineering memory. It deliberately uses only the Python stdlib + numpy
so it has zero install cost and can run in CI, locally, and from
inside the Temporal workers without dragging in PyTorch / chromadb.

Modules
-------
- ``store``     SQLite-backed structured + lexical store (BM25 stats).
- ``embed``     Embedding interface. Default: stdlib hash-trick fallback.
                Upgrades to OpenAI text-embedding-3-small when
                ``OPENAI_API_KEY`` is set.
- ``indexer``   Walks the repo + ``/memory/`` tree, chunks documents,
                writes to the store, and refreshes the embedding cache.
- ``retriever`` Hybrid BM25 + cosine retrieval, with optional graph-walk
                expansion and recency / importance reranking.
- ``graph``     Builds the file-import + memory cross-reference graph,
                persists to JSON for read-side queries.
- ``cli``       Single command-line entry point. ``python -m
                scripts.memory.cli {index,search,graph,summary,...}``.

Design rationale
----------------
A real working retriever today beats a perfect-on-paper retriever next
quarter. The interfaces here are intentionally narrow so the embedding
backend can be swapped (Qdrant, pgvector, OpenAI) without changing call
sites. See ``memory/docs/MEMORY_ARCHITECTURE.md``.
"""

__all__ = ["store", "embed", "indexer", "retriever", "graph", "cli"]
