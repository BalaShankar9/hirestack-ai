"""SQLite-backed memory store.

Single file at ``memory/vector_indexes/store.sqlite3``. Keeps everything
in one durable, grep-friendly file that survives across worktrees and
CI runs. Schema is intentionally simple — we are not building a
distributed index; we are giving AI agents a reliable read surface.

Tables
------
- ``documents``   one row per ingested file (path, kind, sha, size, mtime)
- ``chunks``      one row per chunk (doc_id, ord, text, token_count, importance)
- ``terms``       BM25 inverted index (term, chunk_id, tf)
- ``meta``        key/value scalars (totals, last-index time, model name)
- ``embeddings``  optional float32 blobs (chunk_id PK, dim, vec)

All writes go through small helpers so the schema can evolve in place.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import struct
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "memory" / "vector_indexes" / "store.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    sha         TEXT NOT NULL,
    size        INTEGER NOT NULL,
    mtime       REAL NOT NULL,
    importance  REAL NOT NULL DEFAULT 1.0,
    indexed_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_kind ON documents(kind);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord         INTEGER NOT NULL,
    text        TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    importance  REAL NOT NULL DEFAULT 1.0,
    UNIQUE(doc_id, ord)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

CREATE TABLE IF NOT EXISTS terms (
    term     TEXT NOT NULL,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    tf       INTEGER NOT NULL,
    PRIMARY KEY(term, chunk_id)
);
CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    dim      INTEGER NOT NULL,
    vec      BLOB NOT NULL
);
"""


# Lexical helpers ---------------------------------------------------------

# Conservative tokenisation for BM25: alphanumerics + underscore, lowercased,
# minimum length 2. Keeps Python identifiers intact, drops noise punctuation.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}")
_STOP = {
    "the", "and", "for", "this", "that", "with", "from", "into",
    "are", "was", "were", "but", "not", "you", "your", "have", "has",
    "had", "will", "would", "should", "could", "all", "any", "one",
    "use", "uses", "used", "via", "per", "out", "off", "yet",
}


def tokenize(text: str) -> List[str]:
    """BM25-friendly tokenisation. Public for tests."""
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 1 and t.lower() not in _STOP]


def encode_vec(vec: np.ndarray) -> bytes:
    if vec.dtype != np.float32:
        vec = vec.astype(np.float32)
    return struct.pack("<i", int(vec.shape[0])) + vec.tobytes()


def decode_vec(blob: bytes) -> np.ndarray:
    (dim,) = struct.unpack("<i", blob[:4])
    arr = np.frombuffer(blob[4:], dtype=np.float32, count=dim)
    return arr


@dataclass
class Chunk:
    """In-memory chunk before insert."""
    text: str
    ord: int
    token_count: int = 0
    importance: float = 1.0

    def __post_init__(self) -> None:
        if not self.token_count:
            self.token_count = len(tokenize(self.text))


@dataclass
class Document:
    """Ingestion-side document descriptor."""
    path: str
    kind: str  # "code" | "memory" | "adr" | "context" | "doc" | "incident"
    sha: str
    size: int
    mtime: float
    importance: float = 1.0
    chunks: List[Chunk] = field(default_factory=list)


class Store:
    """Thin SQLite wrapper. Always opens in WAL mode; safe under concurrent reads."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    # Connection lifecycle ------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA)
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # Meta ----------------------------------------------------------------

    def set_meta(self, key: str, value: Any) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.connect().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    # Documents -----------------------------------------------------------

    def get_document(self, path: str) -> Optional[sqlite3.Row]:
        return self.connect().execute("SELECT * FROM documents WHERE path=?", (path,)).fetchone()

    def upsert_document(self, doc: Document) -> int:
        with self.transaction() as conn:
            existing = conn.execute("SELECT id, sha FROM documents WHERE path=?", (doc.path,)).fetchone()
            if existing and existing["sha"] == doc.sha:
                return int(existing["id"])
            if existing:
                # Schema-stable update: refresh metadata, drop chunks (cascades to terms/embeddings).
                conn.execute(
                    "UPDATE documents SET sha=?, size=?, mtime=?, importance=?, indexed_at=? WHERE id=?",
                    (doc.sha, doc.size, doc.mtime, doc.importance, time.time(), existing["id"]),
                )
                conn.execute("DELETE FROM chunks WHERE doc_id=?", (existing["id"],))
                doc_id = int(existing["id"])
            else:
                cur = conn.execute(
                    "INSERT INTO documents(path, kind, sha, size, mtime, importance, indexed_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (doc.path, doc.kind, doc.sha, doc.size, doc.mtime, doc.importance, time.time()),
                )
                doc_id = int(cur.lastrowid or 0)
            for ch in doc.chunks:
                cur = conn.execute(
                    "INSERT INTO chunks(doc_id, ord, text, token_count, importance) VALUES(?, ?, ?, ?, ?)",
                    (doc_id, ch.ord, ch.text, ch.token_count, ch.importance),
                )
                chunk_id = int(cur.lastrowid or 0)
                # Inverted index: collapse to term frequency per chunk.
                tf: Dict[str, int] = {}
                for tok in tokenize(ch.text):
                    tf[tok] = tf.get(tok, 0) + 1
                if tf:
                    conn.executemany(
                        "INSERT INTO terms(term, chunk_id, tf) VALUES(?, ?, ?)",
                        [(t, chunk_id, n) for t, n in tf.items()],
                    )
            return doc_id

    def delete_document(self, path: str) -> bool:
        with self.transaction() as conn:
            cur = conn.execute("DELETE FROM documents WHERE path=?", (path,))
            return cur.rowcount > 0

    def all_paths(self) -> List[str]:
        return [r["path"] for r in self.connect().execute("SELECT path FROM documents")]

    # Read API for retriever ---------------------------------------------

    def chunk_count(self) -> int:
        row = self.connect().execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        return int(row["n"])

    def chunks_for_terms(self, terms: Sequence[str]) -> Dict[int, Dict[str, int]]:
        """Posting list lookup. Returns {chunk_id: {term: tf}}."""
        if not terms:
            return {}
        out: Dict[int, Dict[str, int]] = {}
        # SQLite has a 999-default param limit; chunk if a query is huge.
        for i in range(0, len(terms), 500):
            batch = list(terms[i:i + 500])
            placeholders = ",".join("?" * len(batch))
            rows = self.connect().execute(
                f"SELECT term, chunk_id, tf FROM terms WHERE term IN ({placeholders})",
                batch,
            ).fetchall()
            for r in rows:
                out.setdefault(int(r["chunk_id"]), {})[r["term"]] = int(r["tf"])
        return out

    def df_for_terms(self, terms: Sequence[str]) -> Dict[str, int]:
        """Document frequency per term (count of distinct chunks containing it)."""
        if not terms:
            return {}
        out: Dict[str, int] = {}
        for i in range(0, len(terms), 500):
            batch = list(terms[i:i + 500])
            placeholders = ",".join("?" * len(batch))
            rows = self.connect().execute(
                f"SELECT term, COUNT(DISTINCT chunk_id) AS df FROM terms "
                f"WHERE term IN ({placeholders}) GROUP BY term",
                batch,
            ).fetchall()
            for r in rows:
                out[r["term"]] = int(r["df"])
        return out

    def chunk_meta(self, chunk_ids: Sequence[int]) -> Dict[int, sqlite3.Row]:
        if not chunk_ids:
            return {}
        out: Dict[int, sqlite3.Row] = {}
        for i in range(0, len(chunk_ids), 500):
            batch = list(chunk_ids[i:i + 500])
            placeholders = ",".join("?" * len(batch))
            rows = self.connect().execute(
                f"SELECT c.id AS chunk_id, c.text, c.ord, c.token_count, c.importance, "
                f"d.id AS doc_id, d.path, d.kind, d.importance AS doc_importance, d.mtime "
                f"FROM chunks c JOIN documents d ON d.id=c.doc_id "
                f"WHERE c.id IN ({placeholders})",
                batch,
            ).fetchall()
            for r in rows:
                out[int(r["chunk_id"])] = r
        return out

    def avg_token_count(self) -> float:
        row = self.connect().execute("SELECT AVG(token_count) AS a FROM chunks").fetchone()
        return float(row["a"] or 0.0)

    # Embeddings ----------------------------------------------------------

    def upsert_embedding(self, chunk_id: int, vec: np.ndarray) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO embeddings(chunk_id, dim, vec) VALUES(?, ?, ?) "
                "ON CONFLICT(chunk_id) DO UPDATE SET dim=excluded.dim, vec=excluded.vec",
                (chunk_id, int(vec.shape[0]), encode_vec(vec)),
            )

    def get_embedding(self, chunk_id: int) -> Optional[np.ndarray]:
        row = self.connect().execute(
            "SELECT vec FROM embeddings WHERE chunk_id=?", (chunk_id,)
        ).fetchone()
        return decode_vec(row["vec"]) if row else None

    def all_embeddings(self) -> Iterable[Tuple[int, np.ndarray]]:
        for row in self.connect().execute("SELECT chunk_id, vec FROM embeddings"):
            yield int(row["chunk_id"]), decode_vec(row["vec"])

    def stats(self) -> Dict[str, Any]:
        c = self.connect()
        return {
            "documents": int(c.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]),
            "chunks": int(c.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]),
            "embeddings": int(c.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()["n"]),
            "terms": int(c.execute("SELECT COUNT(DISTINCT term) AS n FROM terms").fetchone()["n"]),
            "avg_tokens_per_chunk": round(self.avg_token_count(), 2),
            "db_path": str(self.db_path),
            "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "last_index": self.get_meta("last_index"),
            "embedding_model": self.get_meta("embedding_model"),
        }
