"""Memory ingestion pipeline.

Walks the repository, classifies each file by ingestion kind, chunks it,
and persists to the SQLite store. Designed to be idempotent and cheap
to re-run — content-hashed, so unchanged files are skipped.

Ingestion kinds + importance defaults
-------------------------------------
- ``adr``        docs/adrs/*.md                                  importance 5.0
- ``runbook``    docs/runbooks/*.md, docs/SLO.md                 importance 4.0
- ``incident``   memory/incidents/*.md                           importance 4.0
- ``decision``   memory/decisions/*.md                           importance 4.0
- ``context``    context/*.md                                    importance 3.0
- ``memory``     memories/repo/*.md  (Copilot session notes)     importance 2.5
- ``doc``        docs/*.md, README.md, *.md at repo root         importance 2.0
- ``code``       backend/app/**, ai_engine/**, scripts/**        importance 1.5
- ``test``       backend/tests/**, frontend/tests/**             importance 1.0

Importance feeds the retriever's reranking. Higher = surfaced sooner.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .embed import get_embedder
from .store import REPO_ROOT, Chunk, Document, Store

# What to walk. Conservative — heavy build outputs and binaries excluded.
INCLUDE_GLOBS = (
    "context/**/*.md",
    "docs/**/*.md",
    "memory/**/*.md",
    "memories/repo/*.md",
    "backend/app/**/*.py",
    "ai_engine/**/*.py",
    "scripts/**/*.py",
    "scripts/**/*.md",
    "supabase/migrations/*.sql",
    "*.md",
)
EXCLUDE_PATTERNS = (
    "**/__pycache__/**",
    "**/.venv/**",
    "**/node_modules/**",
    "**/coverage/**",
    "**/output/**",
    "**/dist/**",
    "**/build/**",
    "**/.next/**",
    "**/.git/**",
    "memory/vector_indexes/**",
    "memory/agent_logs/**",
    "memory/context_snapshots/**",
)

# Hard caps: we are not indexing 100 KB blobs as a single chunk.
MAX_FILE_BYTES = 1_500_000     # 1.5 MB per file
MAX_CHUNK_TOKENS = 480         # ~ 1900 chars; comfortable embed window
MIN_CHUNK_TOKENS = 8           # ignore noise


KIND_TABLE: Tuple[Tuple[str, str, float], ...] = (
    # (glob, kind, importance)
    ("docs/adrs/*.md", "adr", 5.0),
    ("docs/runbooks/*.md", "runbook", 4.0),
    ("docs/SLO.md", "runbook", 4.0),
    ("memory/incidents/*.md", "incident", 4.0),
    ("memory/decisions/*.md", "decision", 4.0),
    ("memory/security/*.md", "security", 4.5),
    ("memory/scaling/*.md", "scaling", 3.5),
    ("memory/business_logic/*.md", "business_logic", 3.5),
    ("memory/releases/*.md", "release", 2.5),
    ("memory/testing/*.md", "testing", 2.5),
    ("memory/technical_debt/*.md", "technical_debt", 3.0),
    ("memory/architecture/*.md", "architecture", 4.5),
    ("memory/docs/*.md", "memory_doc", 3.0),
    ("context/*.md", "context", 3.0),
    ("memories/repo/*.md", "memory", 2.5),
    ("docs/*.md", "doc", 2.0),
    ("backend/tests/**/*.py", "test", 1.0),
    ("frontend/tests/**/*.py", "test", 1.0),
    ("backend/app/**/*.py", "code", 1.5),
    ("ai_engine/**/*.py", "code", 1.5),
    ("scripts/**/*.py", "code", 1.2),
    ("scripts/**/*.md", "doc", 2.0),
    ("supabase/migrations/*.sql", "schema", 3.0),
    ("*.md", "doc", 2.0),
)


def classify(rel_path: str) -> Tuple[str, float]:
    """Return ``(kind, importance)`` for a repo-relative path."""
    for glob, kind, importance in KIND_TABLE:
        if fnmatch.fnmatch(rel_path, glob):
            return kind, importance
    return "code", 1.0


def _excluded(rel_path: str) -> bool:
    return any(fnmatch.fnmatch(rel_path, p) for p in EXCLUDE_PATTERNS)


def discover(root: Path) -> Iterable[Path]:
    """Yield repo-rooted absolute paths matching INCLUDE_GLOBS minus excludes."""
    seen: set[Path] = set()
    for glob in INCLUDE_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if _excluded(rel):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


# Chunking ---------------------------------------------------------------

_PY_BLOCK_RE = re.compile(r"^(class |def |async def )", re.MULTILINE)
_MD_HEADING_RE = re.compile(r"^#{1,6} ", re.MULTILINE)


def _approx_tokens(text: str) -> int:
    # Rough: 1 token ≈ 4 chars. Avoids tiktoken dep.
    return max(1, len(text) // 4)


def chunk_python(text: str) -> List[str]:
    """Split a Python file at top-level def/class boundaries, then size-cap."""
    if not text.strip():
        return []
    indices = [m.start() for m in _PY_BLOCK_RE.finditer(text)]
    if not indices or indices[0] > 0:
        indices = [0] + indices
    pieces: List[str] = []
    for i, start in enumerate(indices):
        end = indices[i + 1] if i + 1 < len(indices) else len(text)
        pieces.append(text[start:end].strip("\n"))
    return _size_cap(pieces)


def chunk_markdown(text: str) -> List[str]:
    """Split markdown at heading boundaries, then size-cap."""
    if not text.strip():
        return []
    indices = [m.start() for m in _MD_HEADING_RE.finditer(text)]
    if not indices or indices[0] > 0:
        indices = [0] + indices
    pieces: List[str] = []
    for i, start in enumerate(indices):
        end = indices[i + 1] if i + 1 < len(indices) else len(text)
        pieces.append(text[start:end].strip("\n"))
    return _size_cap(pieces)


def chunk_generic(text: str) -> List[str]:
    """Paragraph-then-line chunker for SQL / fallback."""
    if not text.strip():
        return []
    paragraphs = [p.strip("\n") for p in text.split("\n\n") if p.strip()]
    return _size_cap(paragraphs)


def _size_cap(pieces: Sequence[str]) -> List[str]:
    """Split anything over ``MAX_CHUNK_TOKENS`` and merge tiny tails."""
    out: List[str] = []
    for piece in pieces:
        approx = _approx_tokens(piece)
        if approx <= MAX_CHUNK_TOKENS:
            out.append(piece)
            continue
        # Split by lines to preserve readability rather than mid-line cuts.
        lines = piece.split("\n")
        buf: List[str] = []
        buf_tokens = 0
        for ln in lines:
            ln_tokens = _approx_tokens(ln) + 1
            if buf and buf_tokens + ln_tokens > MAX_CHUNK_TOKENS:
                out.append("\n".join(buf))
                buf = [ln]
                buf_tokens = ln_tokens
            else:
                buf.append(ln)
                buf_tokens += ln_tokens
        if buf:
            out.append("\n".join(buf))
    # Merge runs that are smaller than MIN_CHUNK_TOKENS into the previous chunk.
    merged: List[str] = []
    for piece in out:
        if merged and _approx_tokens(piece) < MIN_CHUNK_TOKENS:
            merged[-1] = merged[-1] + "\n\n" + piece
        else:
            merged.append(piece)
    return [m for m in merged if _approx_tokens(m) >= MIN_CHUNK_TOKENS]


def chunk_for(path: Path, text: str) -> List[str]:
    if path.suffix == ".py":
        return chunk_python(text)
    if path.suffix in (".md",):
        return chunk_markdown(text)
    return chunk_generic(text)


# Ingestion driver -------------------------------------------------------

@dataclass
class IndexResult:
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    embedded: int = 0
    errors: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def _sha(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()[:40]


def index(
    root: Path = REPO_ROOT,
    db_path: Optional[Path] = None,
    embed_mode: str = "auto",  # "auto" | "off" | "openai"
    only_changed: bool = True,
    verbose: bool = False,
) -> IndexResult:
    """Run a full index pass.

    Idempotent: documents whose sha matches the stored row are skipped.
    """
    store = Store(db_path)
    embedder = None
    if embed_mode != "off":
        embedder = get_embedder(prefer_openai=(embed_mode == "openai"))
        store.set_meta("embedding_model", embedder.name)

    result = IndexResult()
    pending_chunks: List[Tuple[int, str]] = []   # (chunk_id, text) for batched embed

    for path in discover(root):
        result.scanned += 1
        rel = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            result.errors.append(f"read {rel}: {exc}")
            continue
        if len(raw) > MAX_FILE_BYTES:
            result.skipped += 1
            continue
        sha = _sha(raw)
        existing = store.get_document(rel)
        if only_changed and existing and existing["sha"] == sha:
            result.unchanged += 1
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            result.skipped += 1
            continue
        kind, importance = classify(rel)
        chunk_strs = chunk_for(path, text)
        if not chunk_strs:
            result.skipped += 1
            continue
        doc = Document(
            path=rel,
            kind=kind,
            sha=sha,
            size=len(raw),
            mtime=path.stat().st_mtime,
            importance=importance,
            chunks=[Chunk(text=t, ord=i, importance=importance) for i, t in enumerate(chunk_strs)],
        )
        was_new = existing is None
        doc_id = store.upsert_document(doc)
        if was_new:
            result.inserted += 1
        else:
            result.updated += 1
        if verbose:
            print(f"  {'+' if was_new else '~'} {rel} [{kind}] x{len(chunk_strs)} chunks")
        if embedder is not None:
            # Re-fetch chunk_ids that were just written.
            conn = store.connect()
            for r in conn.execute("SELECT id, text FROM chunks WHERE doc_id=? ORDER BY ord", (doc_id,)):
                pending_chunks.append((int(r["id"]), r["text"]))
            # Flush in 128-chunk batches to keep memory flat.
            if len(pending_chunks) >= 128:
                _flush_embeddings(store, embedder, pending_chunks, result)
                pending_chunks.clear()
    if embedder is not None and pending_chunks:
        _flush_embeddings(store, embedder, pending_chunks, result)
    store.set_meta("last_index", {"ts": time.time(), "result": result.__dict__})
    store.close()
    return result


def _flush_embeddings(store: Store, embedder, batch: List[Tuple[int, str]], result: IndexResult) -> None:
    chunk_ids = [cid for cid, _ in batch]
    texts = [t for _, t in batch]
    try:
        vecs = embedder.embed(texts)
    except Exception as exc:
        result.errors.append(f"embed batch ({len(batch)} chunks): {exc}")
        return
    for cid, v in zip(chunk_ids, vecs):
        store.upsert_embedding(cid, v)
    result.embedded += len(batch)


# CLI shim (parent CLI imports this) ------------------------------------

def _main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="HireStack memory indexer")
    p.add_argument("--root", type=Path, default=REPO_ROOT)
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--embed", choices=("auto", "off", "openai"), default="auto")
    p.add_argument("--full", action="store_true", help="Re-index even unchanged files")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    t0 = time.time()
    result = index(
        root=args.root,
        db_path=args.db,
        embed_mode=args.embed,
        only_changed=not args.full,
        verbose=args.verbose,
    )
    elapsed = time.time() - t0
    print(
        f"indexed in {elapsed:.2f}s | scanned={result.scanned} "
        f"inserted={result.inserted} updated={result.updated} "
        f"unchanged={result.unchanged} skipped={result.skipped} "
        f"embedded={result.embedded} errors={len(result.errors)}"
    )
    if result.errors:
        for e in result.errors[:10]:
            print(f"  ! {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
