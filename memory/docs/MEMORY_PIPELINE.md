# Memory pipeline

End-to-end ingestion + maintenance flow for the memory store. Every
arrow in the diagram below is a real call site in `scripts/memory/`.

```
+------------------------+        +------------------+        +--------------------+
| Source files           |        | indexer.py       |        | store.sqlite3      |
| - docs/adrs/*.md       |   -->  | - discover()     |   -->  | documents          |
| - context/*.md         |        | - classify()     |        | chunks             |
| - memory/**/*.md       |        | - chunk_for()    |        | terms (BM25)       |
| - backend/app/**/*.py  |        | - upsert         |        | embeddings (BLOB)  |
| - ai_engine/**/*.py    |        | - embed batch    |        | meta               |
| - memories/repo/*.md   |        +------------------+        +--------------------+
+------------------------+                |                            ^
                                          v                            |
                                  +------------------+                 |
                                  | embed.py         |                 |
                                  | HashEmbedder     |  (or OpenAI)    |
                                  | -> float32[384]  | ----------------+
                                  +------------------+
```

## Phase 1 — discovery

`scripts.memory.indexer.discover(root)` walks the include globs:

```python
INCLUDE_GLOBS = (
    "context/**/*.md", "docs/**/*.md", "memory/**/*.md",
    "memories/repo/*.md", "backend/app/**/*.py",
    "ai_engine/**/*.py", "scripts/**/*.py", "scripts/**/*.md",
    "supabase/migrations/*.sql", "*.md",
)
```

Excludes are conservative: `.venv`, `node_modules`, `coverage`, `output`,
`dist`, `build`, `.next`, `.git`, plus the store and agent logs themselves.

## Phase 2 — classification

`indexer.classify(rel_path)` returns `(kind, importance)` from a glob
table (see `KIND_TABLE` in `indexer.py`). Kind drives filtering at
retrieval time; importance drives ranking. Both are persisted on the
`documents` row, so re-classifying just requires `--full`.

## Phase 3 — chunking

| Extension | Strategy | Anchor |
| --------- | -------- | ------ |
| `.py` | `chunk_python` | `^class ` / `^def ` / `^async def ` |
| `.md` | `chunk_markdown` | `^#{1,6} ` headings |
| anything else | `chunk_generic` | `\n\n` paragraphs |

All strategies pass through `_size_cap`:

- Pieces over `MAX_CHUNK_TOKENS` (480, ≈1900 chars) are line-wise split.
- Pieces under `MIN_CHUNK_TOKENS` (8) are merged into the previous chunk.

## Phase 4 — content-address skip

```python
sha = sha256(raw_bytes)[:40]
if existing and existing["sha"] == sha and only_changed:
    result.unchanged += 1
    continue
```

Re-indexing a clean tree costs ~1.2 s for 700 files because every file
is `read_bytes` + sha + dict lookup, no chunking and no embedding.

## Phase 5 — write

`Store.upsert_document(doc)` is one transaction:

1. Insert/update the `documents` row.
2. Cascade-delete old `chunks` (which cascade-deletes old `terms` and
   `embeddings`).
3. Insert new chunks; for each chunk, build the term-frequency dict and
   `executemany` into `terms`.
4. Return `doc_id` so the caller can attach embeddings.

## Phase 6 — embed (optional)

Embeddings are batched in groups of 128 chunks, then flushed via
`Store.upsert_embedding`. Default backend is `HashEmbedder`; switch to
OpenAI with `--embed openai` (requires `OPENAI_API_KEY`). The embedding
model name is recorded in `meta.embedding_model` so the retriever can
detect a model swap and refuse to mix dimensions.

## Phase 7 — graph

`scripts.memory.graph.build_graph()` is a separate pass:

1. Walk `backend/app/`, `ai_engine/`, `scripts/` for `*.py`.
2. Parse each file with `ast` and collect `Import` / `ImportFrom`.
3. Resolve each import against the known module set (handles relative
   imports via `level`).
4. Walk `memory/`, `memories/repo/`, `context/`, `docs/` for `*.md` and
   regex-extract backtick-wrapped paths + `ADR-NNNN` references.
5. Write `memory/graph/graph.json` with `nodes`, `edges`, `counts`.

The graph is a *separate* artefact from the SQLite store on purpose —
it's read by future UIs and code-review tooling, not by the retriever
hot path.

## Schedule

- **Local dev**: run `python -m scripts.memory.cli index` whenever you
  feel out of sync. ≈9 s for full re-index, ≈1 s for incremental.
- **CI**: runs on every push to `main` (future: `.github/workflows/memory.yml`).
- **Pre-PR**: agents are expected to run an incremental `index` before
  calling `search` so freshly-edited files are visible. See
  `AGENT_MEMORY_PROTOCOL.md`.

## Observability

- `cli summary` prints document/chunk/embedding/term counts + DB size.
- `meta.last_index` stores the last full result (timing, error list).
- Errors during indexing are non-fatal — they accumulate on
  `IndexResult.errors` and print at the end.
