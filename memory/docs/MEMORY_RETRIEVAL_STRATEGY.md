# Memory retrieval strategy

Defines exactly how `scripts.memory.retriever.Retriever.search` ranks
chunks. Read this before tuning weights or adding a new signal.

## The full ranking formula

For every candidate chunk `c` (union of BM25 hits and cosine hits):

```
score(c)  =   bm25_weight       *  bm25(c, query)
            + cosine_weight     *  max(0, cosine(c.embed, query.embed))
            + importance_weight *  log1p(c.doc.importance * c.importance)
            + recency_weight    *  0.5 ^ (age_days / 90)
```

Defaults (in `retriever.py`):

| Weight | Value | Rationale |
| ------ | ----- | --------- |
| `bm25_weight` | 1.0 | BM25 is the strongest signal on identifier-heavy text |
| `cosine_weight` | 1.0 | Equal billing — feature-hash cosine catches synonyms BM25 misses |
| `importance_weight` | 0.4 | Logarithmic so a 5x-importance ADR doesn't crush a perfect-match code chunk |
| `recency_weight` | 0.15 | Small thumb on the scale; never overrides relevance |

Negative cosine scores are clipped to zero — they add noise.

## Stage 1 — candidate generation

Two parallel posting-list lookups:

1. **BM25** (`_bm25`): tokenize the query, look up each term's posting
   list via `Store.chunks_for_terms(terms)`. Score each chunk with
   classic BM25 (`k1=1.5, b=0.75`) using per-chunk `token_count` and
   the global `avg_token_count`.
2. **Cosine** (`_cosine`): embed the query once with the active
   embedder, then `mat @ q_vec` against all stored embeddings. Drop
   any vectors whose dim doesn't match (defensive against model swaps).

Candidate set = `bm25_scores.keys() | cosine_scores.keys()`. We do
**not** intersect — that loses recall on queries where one signal is
weak.

## Stage 2 — filter

`kinds` and `path_prefix` filters are applied here, before final
scoring. Cheap, and avoids reranking dead candidates.

## Stage 3 — combine + rerank

For each surviving candidate we fetch joined chunk+document metadata
in batched SQL (`Store.chunk_meta`) and apply the formula above.

The `importance` term is `doc_importance * chunk_importance`. Today
chunk importance == doc importance (set in indexer), but the schema
supports per-chunk importance for future use (e.g. boost a code chunk
that contains the symbol named in the query).

`recency` uses an exponential half-life of 90 days. ADRs and incidents
have high `importance` so they survive aging; transient session notes
(memory: 2.5) decay faster than ADRs (5.0) because the importance term
amplifies the recency contribution non-linearly.

## Stage 4 — top-k

Sort descending, slice. The CLI's default `k` is 8 for `search`, 16
for `context` (with token-budget filling described in
`CONTEXT_ENGINEERING_RULES.md`).

## Worked example

Query: `"critic retry policy"`, run against the live store today, top-3:

```
14.48  [code  ]  backend/app/temporal/activities/production.py#0
       bm25=13.72 cosine=0.14 importance=2.25  → BM25-dominant: code chunk literally
                                                  contains "critic" + "retry" near
                                                  each other.
13.56  [adr   ]  docs/adrs/0040-ack-on-success-and-dlq.md#7
       bm25=12.06 cosine=0.05 importance=25.00 → ADR boosted by importance (5×5)
                                                  enough to displace lower-imp code.
13.10  [code  ]  ai_engine/agents/orchestrator.py#22
       bm25=12.29 cosine=0.19 importance=2.25  → strong cosine because hash embeds
                                                  "critic" + "retry" trigrams.
```

The ADR placement is intentional. When a contributor asks about retry
policy, the *decision* explaining why we chose the current shape should
be one click away from the *implementation*.

## Filters in practice

```bash
# Only ADRs
cli search "ack on success" --kind adr

# Only code in the orchestrator path
cli search "model router" --kind code --path-prefix ai_engine/

# Only incidents from the last quarter
cli search "rate limit 429" --kind incident
```

## Tuning checklist (when the eval set lands)

1. Sweep `cosine_weight` ∈ {0.5, 1.0, 1.5, 2.0} with
   `bm25_weight = 1.0` fixed. Record recall@5 and MRR.
2. Re-sweep with OpenAI embeddings. Expect cosine_weight to climb to
   ~1.5 because OpenAI vectors are stronger than hash vectors.
3. Sweep `importance_weight` ∈ {0.0, 0.2, 0.4, 0.8}. We expect a
   shallow optimum around 0.4 (current); much higher and ADRs crowd
   out implementation chunks.
4. Sweep `recency_weight` ∈ {0.0, 0.15, 0.3}. Watch for "stale ADR
   gets demoted by yesterday's WIP note" failures.

Until that eval lands, **do not blindly retune** — the current weights
are deliberate Robertson + log-importance defaults.

## What's missing today (and the plan)

- **No reciprocal rank fusion.** We sum raw BM25 and cosine even
  though they're on different scales. RRF would be more principled.
  Defer until eval shows it matters.
- **No diversification (MMR).** Top-k can return 5 near-duplicate
  chunks of the same doc. The `context` command compensates by
  deduping per `chunk_id` and adding neighbour expansion separately.
- **No query expansion.** A future PR can stem / synonym-expand the
  query (`temporal → workflow, activity, worker`). Cheap to add when
  the eval set demonstrates need.
- **No personalisation.** The store is single-tenant by design.
