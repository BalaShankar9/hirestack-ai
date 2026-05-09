# Vector search design

## What we ship today

Two embedding backends, both behind the `_BaseEmbedder` interface in
`scripts/memory/embed.py`:

| Backend | Dim | Source | Cost | Quality on this corpus |
| ------- | --- | ------ | ---- | ---------------------- |
| **HashEmbedder** (default) | 384 | feature hashing on uni/bi/tri-grams | $0, 0 ms net | good on identifier-heavy text (code, ADRs); weak on synonyms |
| **OpenAIEmbedder** | 1536 | `text-embedding-3-small` | ~$0.02 / 1M tokens | strong semantic recall |

Both produce **L2-normalised float32** vectors. The retriever's cosine
calculation is therefore a single matrix-vector dot product:

```python
sims = mat @ q_vec     # mat is (N, d), q_vec is (d,), all unit-normed
```

Storage: `embeddings.vec BLOB`, `dim INTEGER`. Encoded with
`struct.pack("<i", dim) + vec.tobytes()`. Reads via `decode_vec` in
`store.py`. No external vector DB.

## Why not chromadb / qdrant / faiss / pgvector right now

Honest accounting on the m12-pr20 corpus (697 docs / 7,330 chunks):

- A linear scan of 7,330 × 384 float32s is `mat @ q` ≈ 11 MB — under
  10 ms on cold RAM.
- An ANN index (HNSW, IVF) buys nothing until the corpus is north of
  ~50k chunks.
- A vector *server* buys nothing until we want cross-process reads from
  the Temporal worker AND the FastAPI process AND a future MCP server.

**So pgvector is the right next step**, not now. See "Upgrade path".

## Why feature hashing (not LSA / SVD / random projection)

We need an embedder that:

1. Has zero training cost (so first index works on a fresh checkout).
2. Is deterministic (so the same text always hashes to the same vector).
3. Handles out-of-vocab tokens gracefully (lots of identifiers,
   acronyms, generated names in this codebase).
4. Adds zero install footprint.

Feature hashing (Weinberger 2009, "Feature Hashing for Large Scale
Multitask Learning") satisfies all four. It is the algorithm behind
scikit-learn's `HashingVectorizer`, used in production by many
classification pipelines. Concretely, in `embed.py:HashEmbedder`:

```python
for ng in unigrams + bigrams + trigrams:
    bucket = blake2b("p" + ng) % 384
    sign   = +1 or -1 from blake2b("s" + ng)
    v[bucket] += sign
v /= ||v||_2
```

The dual hash (Charikar) corrects the bias of single-hash collisions
to mean-zero — important because we are not in the high-d regime.

## Upgrade path

When we outgrow this — concretely, when retrieval recall@5 drops below
~0.7 on the hireability-eval set — the migration is mechanical:

1. **Try OpenAI first.** Set `HIRESTACK_MEMORY_OPENAI=1 OPENAI_API_KEY=…`
   and re-run `cli index --full --embed openai`. Vectors are persisted;
   no changes to retriever or store needed. Cost ≈ $0.10 for the full
   m12-pr20 corpus, $0.01 for an incremental run.

2. **If OpenAI is slow at scale**, switch storage to **pgvector** in
   Supabase (we already run Postgres):

   ```sql
   create extension vector;
   create table memory_embeddings (
     chunk_id   bigint primary key,
     embedding  vector(1536) not null
   );
   create index on memory_embeddings using hnsw (embedding vector_cosine_ops);
   ```

   Implementation surface: a new `PgVectorStore` mirroring `Store`'s
   embedding methods, plus `Retriever._cosine` becoming
   `select chunk_id, 1 - (embedding <=> $1) as cos from memory_embeddings order by embedding <=> $1 limit 256`.
   The BM25 + ranking parts do not change.

3. **Only if multi-region / sub-10ms p95 matters**, evaluate Qdrant or
   Vespa. Today this is not a concern.

## Quality measurement

We do not yet have a scored eval set. Two follow-up PRs:

- **m12-pr21** (planned): seed `memory/testing/retrieval_eval.jsonl`
  with ~30 hand-labelled `(query, expected_doc_path[])` pairs. Add
  `scripts/memory/eval.py` to compute recall@k and MRR. Run in CI.
- **m12-pr22** (planned): wire agent log feedback — when a retrieved
  chunk gets cited in the final commit / decision, store a positive
  signal; when an agent ignores top-3 and finds context elsewhere, store
  a negative signal. Use this to tune `bm25_weight` / `cosine_weight`.

## Hyperparameters (today)

In `retriever.Retriever.__init__`:

```python
bm25_weight       = 1.0
cosine_weight     = 1.0
importance_weight = 0.4
recency_weight    = 0.15
```

In `retriever._bm25`:

```python
_BM25_K1 = 1.5
_BM25_B  = 0.75
```

In `retriever`:

```python
_RECENCY_HALF_LIFE_DAYS = 90.0
```

These are deliberate Robertson defaults, not tuned. Re-tune after the
eval set lands.

## Failure modes + handling

| Failure | Detection | Handling |
| ------- | --------- | -------- |
| Embedding model swapped, dims mismatch | `Retriever._cosine` checks `v.shape[0] == target_dim` per row | Drop mismatched vectors silently; warn in `summary`. Re-index with `--full --embed <new>` to fix. |
| OpenAI rate-limit / network error | exception bubbles from `OpenAIEmbedder.embed` | Caught in `indexer._flush_embeddings`, appended to `result.errors`, run continues. |
| Embeddings table empty | `_cosine` returns `{}` | Retriever degrades gracefully to BM25-only ranking. |
| Query has only stopwords | `tokenize(query)` returns `[]` | `_bm25` returns `{}`, embeddings still drive ranking if available. |
