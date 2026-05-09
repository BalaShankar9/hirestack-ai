"""Embedding backends.

Two real backends:

- :class:`HashEmbedder` — stdlib + numpy. Deterministic 384-d feature
  hashing on token n-grams. Quality is decent on identifier-heavy text
  (code, ADRs) and good enough to beat keyword-only retrieval. Zero
  install cost, zero network calls. Default for CI and local dev.
- :class:`OpenAIEmbedder` — OpenAI ``text-embedding-3-small`` (1536 d).
  Activated when ``OPENAI_API_KEY`` is set or ``--openai`` is passed
  to the indexer. Cached in the SQLite store, so re-runs are free.

Embedders MUST return L2-normalised float32 vectors so cosine similarity
== dot product (the retriever assumes this).
"""

from __future__ import annotations

import hashlib
import os
from typing import Iterable, List, Sequence

import numpy as np

from .store import tokenize


class _BaseEmbedder:
    name: str = "base"
    dim: int = 0

    def embed(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class HashEmbedder(_BaseEmbedder):
    """Feature-hashing embedder. Two-hash trick reduces collision bias.

    For each token + bigram + trigram we hash to ``dim`` buckets with a
    primary hash, sign with a secondary hash, accumulate into a sparse
    vector, then L2-normalise. This is a well-known trick (Weinberger
    et al. 2009) and is the same approach scikit-learn's
    ``HashingVectorizer`` uses.
    """

    name = "hash-trick-384"
    dim = 384

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    @staticmethod
    def _h(token: str, salt: str) -> int:
        return int.from_bytes(
            hashlib.blake2b((salt + token).encode("utf-8"), digest_size=8).digest(),
            "little",
            signed=False,
        )

    def _vector(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = tokenize(text)
        if not toks:
            return v
        # Unigrams + adjacent bigrams + adjacent trigrams.
        ngrams: List[str] = list(toks)
        ngrams.extend(f"{a}_{b}" for a, b in zip(toks, toks[1:]))
        ngrams.extend(f"{a}_{b}_{c}" for a, b, c in zip(toks, toks[1:], toks[2:]))
        for ng in ngrams:
            bucket = self._h(ng, "p") % self.dim
            sign = 1.0 if (self._h(ng, "s") & 1) else -1.0
            v[bucket] += sign
        n = float(np.linalg.norm(v))
        if n > 0.0:
            v /= n
        return v

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        return np.vstack([self._vector(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)


class OpenAIEmbedder(_BaseEmbedder):
    """OpenAI text-embedding-3-small. Lazy client, batched calls, retried."""

    name = "openai/text-embedding-3-small"
    dim = 1536

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI  # type: ignore[import-not-found]

        self.model = model
        self._client = OpenAI()

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        # OpenAI accepts up to ~2048 inputs / call but we batch smaller for memory + retry granularity.
        out: List[np.ndarray] = []
        BATCH = 64
        for i in range(0, len(texts), BATCH):
            batch = list(texts[i:i + BATCH])
            resp = self._client.embeddings.create(model=self.model, input=batch)
            mat = np.array([d.embedding for d in resp.data], dtype=np.float32)
            # Normalise — OpenAI returns close-to-unit but not guaranteed.
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            out.append(mat / norms)
        return np.vstack(out)


def get_embedder(prefer_openai: bool = False) -> _BaseEmbedder:
    """Resolve the active embedder.

    Order: explicit ``prefer_openai`` flag > ``HIRESTACK_MEMORY_OPENAI=1``
    env > fallback ``HashEmbedder``. If OpenAI is requested but the SDK
    or key is missing, fall back loudly (warn but never crash).
    """
    want_openai = prefer_openai or os.environ.get("HIRESTACK_MEMORY_OPENAI") == "1"
    if want_openai and os.environ.get("OPENAI_API_KEY"):
        try:
            return OpenAIEmbedder()
        except Exception as exc:  # pragma: no cover - import / network errors
            import warnings
            warnings.warn(f"OpenAI embedder unavailable, falling back to hash: {exc}")
    return HashEmbedder()
