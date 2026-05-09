"""Roundtrip tests for the memory store + retriever.

Focused, fast, deterministic. We never touch the real
``memory/vector_indexes/store.sqlite3`` — every test creates a fresh
SQLite in tmp_path. The hash embedder is deterministic, so we can
assert exact ranking outcomes.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from scripts.memory.embed import HashEmbedder, get_embedder
from scripts.memory.indexer import (
    chunk_markdown,
    chunk_python,
    classify,
    index,
)
from scripts.memory.retriever import Retriever
from scripts.memory.store import Chunk, Document, Store, decode_vec, encode_vec, tokenize


# --- store ---------------------------------------------------------------

def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    toks = tokenize("The Temporal worker has a retry policy of 3 attempts.")
    assert "temporal" in toks
    assert "worker" in toks
    assert "retry" in toks
    assert "policy" in toks
    assert "the" not in toks    # stopword
    assert "has" not in toks    # stopword
    assert "3" not in toks      # leading digit dropped by regex


def test_encode_decode_vec_roundtrip() -> None:
    v = np.array([0.1, -0.5, 0.9, 0.0], dtype=np.float32)
    assert np.array_equal(decode_vec(encode_vec(v)), v)


def test_store_upsert_idempotent_on_same_sha(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite3"
    s = Store(db)
    doc = Document(
        path="memory/decisions/test.md",
        kind="decision",
        sha="abc123",
        size=42,
        mtime=1.0,
        importance=2.0,
        chunks=[Chunk(text="critic retry policy is fixed at three attempts", ord=0)],
    )
    first = s.upsert_document(doc)
    second = s.upsert_document(doc)  # same sha → no churn
    assert first == second
    assert s.chunk_count() == 1


def test_store_upsert_replaces_chunks_on_sha_change(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite3"
    s = Store(db)
    base = Document(
        path="x.md", kind="doc", sha="v1", size=1, mtime=1.0,
        chunks=[Chunk(text="alpha beta gamma", ord=0)],
    )
    s.upsert_document(base)
    base.sha = "v2"
    base.chunks = [Chunk(text="delta epsilon zeta", ord=0), Chunk(text="eta theta iota", ord=1)]
    s.upsert_document(base)
    assert s.chunk_count() == 2  # old chunk gone


def test_store_stats(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite3"
    s = Store(db)
    s.upsert_document(Document(
        path="x.md", kind="doc", sha="s", size=1, mtime=1.0,
        chunks=[Chunk(text="word", ord=0)],
    ))
    stats = s.stats()
    assert stats["documents"] == 1
    assert stats["chunks"] == 1
    assert stats["db_size_bytes"] > 0


# --- embed ---------------------------------------------------------------

def test_hash_embedder_is_deterministic_and_normalised() -> None:
    e = HashEmbedder()
    a = e.embed(["temporal critic retry policy"])
    b = e.embed(["temporal critic retry policy"])
    assert a.shape == (1, 384)
    assert a.dtype == np.float32
    assert np.allclose(a, b)
    assert pytest.approx(float(np.linalg.norm(a[0])), abs=1e-5) == 1.0


def test_hash_embedder_handles_empty_input() -> None:
    e = HashEmbedder()
    out = e.embed(["", "  "])
    assert out.shape == (2, 384)
    assert np.allclose(out, 0.0)


def test_get_embedder_falls_back_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HIRESTACK_MEMORY_OPENAI", raising=False)
    e = get_embedder(prefer_openai=True)
    assert isinstance(e, HashEmbedder)


# --- chunkers ------------------------------------------------------------

def test_chunk_python_splits_on_def_and_class() -> None:
    src = (
        "import os\nimport json\nfrom typing import Any\n\n"
        "class Foo:\n"
        "    def bar(self, x, y):\n"
        "        result = x + y + 42\n"
        "        return {'result': result, 'kind': 'sum', 'inputs': [x, y]}\n"
        "    def baz(self, items):\n"
        "        return [it.upper() for it in items if isinstance(it, str)]\n"
        "\n"
        "def standalone_function(payload):\n"
        "    parsed = json.loads(payload)\n"
        "    return {'parsed': parsed, 'count': len(parsed.get('items', []))}\n"
    )
    chunks = chunk_python(src)
    assert len(chunks) >= 2
    joined = "\n".join(chunks)
    assert "class Foo" in joined
    assert "standalone_function" in joined


def test_chunk_markdown_splits_on_headings() -> None:
    body_a = "Section A discusses the temporal worker architecture, retry policies, " \
        "exponential backoff strategies, dead-letter queue handling, and idempotency keys."
    body_b = "Section B covers the critic agent pipeline, evaluation rubrics, " \
        "scoring weights, ranking thresholds, and downstream optimisation loops."
    md = f"# Title\n\nIntroduction paragraph with substantive content about the system.\n\n" \
         f"## Section A\n\n{body_a}\n\n## Section B\n\n{body_b}\n"
    chunks = chunk_markdown(md)
    assert len(chunks) >= 2
    joined = "\n".join(chunks)
    assert "Section A" in joined
    assert "Section B" in joined


# --- classify ------------------------------------------------------------

def test_classify_known_paths() -> None:
    assert classify("docs/adrs/0040-ack-on-success-and-dlq.md") == ("adr", 5.0)
    assert classify("memory/incidents/2026-01-foo.md")[0] == "incident"
    assert classify("context/ENGINEERING_CONTEXT.md")[0] == "context"
    assert classify("backend/app/api/routes/jobs.py")[0] == "code"
    assert classify("ai_engine/agents/critic.py")[0] == "code"


# --- end-to-end retrieval ------------------------------------------------

def _seed_corpus(tmp_path: Path, db_path: Path) -> None:
    """Build a tiny repo skeleton so ``index()`` has real files to walk."""
    root = tmp_path / "repo"
    (root / "docs" / "adrs").mkdir(parents=True)
    (root / "context").mkdir(parents=True)
    (root / "ai_engine" / "agents").mkdir(parents=True)
    (root / "memory" / "vector_indexes").mkdir(parents=True)

    (root / "docs" / "adrs" / "0099-test.md").write_text(
        "# 0099 Test ADR\n\n## Decision\n\n"
        "Critic agent uses an exponential retry policy with three attempts.\n"
    )
    (root / "context" / "ENGINEERING_CONTEXT.md").write_text(
        "# Engineering context\n\n"
        "Temporal workers run critic loops with retry policies for resilience.\n"
    )
    (root / "ai_engine" / "agents" / "critic.py").write_text(
        '"""Critic agent with retry policy and exponential backoff."""\n\n'
        "def evaluate_with_retry(draft, max_attempts=3):\n"
        "    # critic retry policy: three attempts, exponential backoff\n"
        "    for attempt in range(max_attempts):\n"
        "        score = compute_critic_score(draft)\n"
        "        if score > 0.7:\n"
        "            return {'score': score, 'attempts': attempt + 1}\n"
        "    return {'score': 0.0, 'attempts': max_attempts}\n"
    )
    return root


def test_index_and_search_roundtrip(tmp_path: Path) -> None:
    repo = _seed_corpus(tmp_path, tmp_path / "store.sqlite3")
    db = tmp_path / "store.sqlite3"

    result = index(root=repo, db_path=db, embed_mode="auto", only_changed=False)
    assert result.errors == []
    assert result.inserted == 3
    assert result.embedded > 0

    r = Retriever(db_path=db, embed_mode="auto")
    hits = r.search("critic retry policy", k=3)
    assert hits, "expected at least one hit"
    # ADR has importance 5.0 vs context 3.0 vs code 1.5 — ADR should be top.
    assert hits[0].kind == "adr"
    assert "0099-test.md" in hits[0].path

    # kind filter
    code_only = r.search("critic retry", k=3, kinds=["code"])
    assert code_only and all(h.kind == "code" for h in code_only)


def test_index_skips_unchanged_files(tmp_path: Path) -> None:
    repo = _seed_corpus(tmp_path, tmp_path / "store.sqlite3")
    db = tmp_path / "store.sqlite3"
    first = index(root=repo, db_path=db, embed_mode="off", only_changed=True)
    assert first.inserted == 3
    second = index(root=repo, db_path=db, embed_mode="off", only_changed=True)
    assert second.inserted == 0
    assert second.unchanged == 3


def test_neighbours_returns_adjacent_chunks(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite3"
    s = Store(db)
    doc = Document(
        path="long.md", kind="doc", sha="z", size=10, mtime=time.time(),
        chunks=[Chunk(text=f"section {i} content alpha beta gamma", ord=i) for i in range(5)],
    )
    s.upsert_document(doc)
    s.close()

    r = Retriever(db_path=db, embed_mode="off")
    hits = r.search("section content alpha", k=1)
    assert hits
    nbrs = r.neighbours(hits[0], span=1)
    # neighbours excludes the hit itself, so up to 2 adjacent chunks
    assert 1 <= len(nbrs) <= 2
    for n in nbrs:
        assert abs(n.ord - hits[0].ord) == 1
