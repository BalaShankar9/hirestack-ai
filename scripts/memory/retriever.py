"""Hybrid retriever for the HireStack memory store.

Combines BM25 lexical scoring with optional cosine similarity over the
embedding cache, then reranks by document importance and recency. The
implementation is small (~200 LOC) on purpose — see
``memory/docs/MEMORY_RETRIEVAL_STRATEGY.md`` for the design.

Usage
-----
    from scripts.memory.retriever import Retriever
    r = Retriever()
    hits = r.search("temporal critic retry policy", k=8)
    for h in hits:
        print(h.score, h.path, h.kind)
        print(h.text[:200])
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

from .embed import get_embedder
from .store import Store, tokenize

# BM25 hyperparameters — Robertson 1995 defaults that work well on mixed corpora.
_BM25_K1 = 1.5
_BM25_B = 0.75

# Recency: half-life ≈ 90 days. ADRs / incidents barely decay (handled by importance).
_RECENCY_HALF_LIFE_DAYS = 90.0


@dataclass
class Hit:
    chunk_id: int
    doc_id: int
    path: str
    kind: str
    score: float
    bm25: float
    cosine: float
    importance: float
    text: str
    ord: int


class Retriever:
    """Read-only retriever. Hot-path; no writes to the store."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        embed_mode: str = "auto",
        bm25_weight: float = 1.0,
        cosine_weight: float = 1.0,
        importance_weight: float = 0.4,
        recency_weight: float = 0.15,
    ) -> None:
        self.store = Store(db_path)
        self.bm25_weight = bm25_weight
        self.cosine_weight = cosine_weight
        self.importance_weight = importance_weight
        self.recency_weight = recency_weight
        self._embedder = None if embed_mode == "off" else get_embedder(prefer_openai=(embed_mode == "openai"))

    # Public API ---------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 8,
        kinds: Optional[Sequence[str]] = None,
        path_prefix: Optional[str] = None,
    ) -> List[Hit]:
        if not query.strip():
            return []
        terms = tokenize(query)
        bm25_scores = self._bm25(terms) if terms else {}
        cosine_scores = self._cosine(query) if self._embedder is not None else {}
        # Union of candidate chunks; keep top 4*k by raw signal before final rerank.
        candidates = set(bm25_scores) | set(cosine_scores)
        if not candidates:
            return []
        chunk_meta = self.store.chunk_meta(list(candidates))
        now = time.time()
        ranked: List[Hit] = []
        for cid, meta in chunk_meta.items():
            kind = meta["kind"]
            if kinds and kind not in kinds:
                continue
            if path_prefix and not meta["path"].startswith(path_prefix):
                continue
            bm = bm25_scores.get(cid, 0.0)
            cos = cosine_scores.get(cid, 0.0)
            importance = float(meta["doc_importance"]) * float(meta["importance"])
            age_days = max(0.0, (now - float(meta["mtime"])) / 86400.0)
            recency = math.pow(0.5, age_days / _RECENCY_HALF_LIFE_DAYS)
            score = (
                self.bm25_weight * bm
                + self.cosine_weight * cos
                + self.importance_weight * math.log1p(importance)
                + self.recency_weight * recency
            )
            ranked.append(
                Hit(
                    chunk_id=cid,
                    doc_id=int(meta["doc_id"]),
                    path=meta["path"],
                    kind=kind,
                    score=score,
                    bm25=bm,
                    cosine=cos,
                    importance=importance,
                    text=meta["text"],
                    ord=int(meta["ord"]),
                )
            )
        ranked.sort(key=lambda h: h.score, reverse=True)
        return ranked[:k]

    # Scoring backends ---------------------------------------------------

    def _bm25(self, terms: Sequence[str]) -> Dict[int, float]:
        unique_terms = list(set(terms))
        df = self.store.df_for_terms(unique_terms)
        N = max(1, self.store.chunk_count())
        avgdl = max(1.0, self.store.avg_token_count())
        postings = self.store.chunks_for_terms(unique_terms)
        # Compute IDF once per term.
        idf = {
            t: math.log(1.0 + (N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
            for t in unique_terms
        }
        # Need chunk lengths for normalisation — fetch lazily.
        chunk_ids = list(postings.keys())
        if not chunk_ids:
            return {}
        meta = self.store.chunk_meta(chunk_ids)
        scores: Dict[int, float] = {}
        for cid, term_tfs in postings.items():
            dl = float(meta[cid]["token_count"])
            s = 0.0
            for t, tf in term_tfs.items():
                num = tf * (_BM25_K1 + 1.0)
                den = tf + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * dl / avgdl)
                if den > 0.0:
                    s += idf[t] * num / den
            if s > 0.0:
                scores[cid] = s
        return scores

    def _cosine(self, query: str) -> Dict[int, float]:
        if self._embedder is None:
            return {}
        q_vec = self._embedder.embed([query])[0]
        # Pull all embeddings as one matrix. Fine up to ~100k chunks; beyond that, switch to ANN.
        ids: List[int] = []
        vecs: List[np.ndarray] = []
        for cid, v in self.store.all_embeddings():
            ids.append(cid)
            vecs.append(v)
        if not vecs:
            return {}
        # If embedding dims mismatch (e.g. switched models), drop the rest defensively.
        target_dim = q_vec.shape[0]
        same_dim_ids: List[int] = []
        same_dim_vecs: List[np.ndarray] = []
        for cid, v in zip(ids, vecs):
            if v.shape[0] == target_dim:
                same_dim_ids.append(cid)
                same_dim_vecs.append(v)
        if not same_dim_vecs:
            return {}
        mat = np.vstack(same_dim_vecs)
        sims = mat @ q_vec  # all vectors are unit-normed, so dot == cosine
        # Keep only positives — negatives add noise to the union score.
        return {cid: float(s) for cid, s in zip(same_dim_ids, sims) if s > 0.0}

    # Convenience --------------------------------------------------------

    def neighbours(self, hit: Hit, span: int = 1) -> List[Hit]:
        """Return adjacent chunks of the same doc (for context expansion)."""
        conn = self.store.connect()
        rows = conn.execute(
            "SELECT id FROM chunks WHERE doc_id=? AND ord BETWEEN ? AND ?",
            (hit.doc_id, hit.ord - span, hit.ord + span),
        ).fetchall()
        ids = [int(r["id"]) for r in rows if int(r["id"]) != hit.chunk_id]
        meta = self.store.chunk_meta(ids)
        return [
            Hit(
                chunk_id=cid,
                doc_id=int(m["doc_id"]),
                path=m["path"],
                kind=m["kind"],
                score=hit.score,  # inherits parent score
                bm25=0.0,
                cosine=0.0,
                importance=hit.importance,
                text=m["text"],
                ord=int(m["ord"]),
            )
            for cid, m in meta.items()
        ]
