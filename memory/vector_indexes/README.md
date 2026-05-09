# memory/vector_indexes

**Generated**, gitignored. Holds the SQLite store + WAL files written
by `scripts/memory/store.py`:

- `store.sqlite3` — main DB (documents, chunks, terms, embeddings, meta)
- `store.sqlite3-wal` — write-ahead log (WAL mode is enabled)
- `store.sqlite3-shm` — shared memory file

Rebuild any time with:

```bash
python -m scripts.memory.cli index --full
```

Do not commit anything here.
