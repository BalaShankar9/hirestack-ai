# Memory ranking system

How importance and recency get assigned, persisted, and combined.

## Importance is assigned at ingest

`scripts.memory.indexer.classify(rel_path)` returns `(kind, importance)`
from `KIND_TABLE`. The current table:

| Kind | Glob | Importance |
| ---- | ---- | ---------- |
| `adr` | `docs/adrs/*.md` | 5.0 |
| `security` | `memory/security/*.md` | 4.5 |
| `architecture` | `memory/architecture/*.md` | 4.5 |
| `runbook` | `docs/runbooks/*.md`, `docs/SLO.md` | 4.0 |
| `incident` | `memory/incidents/*.md` | 4.0 |
| `decision` | `memory/decisions/*.md` | 4.0 |
| `business_logic` | `memory/business_logic/*.md` | 3.5 |
| `scaling` | `memory/scaling/*.md` | 3.5 |
| `technical_debt` | `memory/technical_debt/*.md` | 3.0 |
| `context` | `context/*.md` | 3.0 |
| `memory_doc` | `memory/docs/*.md` | 3.0 |
| `schema` | `supabase/migrations/*.sql` | 3.0 |
| `release` | `memory/releases/*.md` | 2.5 |
| `testing` | `memory/testing/*.md` | 2.5 |
| `memory` | `memories/repo/*.md` | 2.5 |
| `doc` | other markdown | 2.0 |
| `code` | `backend/app/`, `ai_engine/` | 1.5 |
| `code` | `scripts/` | 1.2 |
| `test` | `backend/tests/`, `frontend/tests/` | 1.0 |

Both kind and importance are persisted on `documents`. Rebuilding the
table requires re-indexing with `--full`.

## Why these specific numbers

The ranking formula uses `log1p(doc_importance * chunk_importance)`,
which is sub-linear:

| importance | log1p(imp²) | relative weight |
| ---------- | ----------- | --------------- |
| 1.0 (test) | 0.69 | 1.0× |
| 1.5 (code) | 1.18 | 1.7× |
| 2.5 (memory) | 1.94 | 2.8× |
| 3.0 (context) | 2.30 | 3.3× |
| 4.0 (incident) | 2.83 | 4.1× |
| 5.0 (adr) | 3.26 | 4.7× |

So an ADR gets ~4.7× the importance contribution of a test file, but
because the importance term is multiplied by 0.4 (the
`importance_weight`), it adds at most ~1.3 to the score. A strong BM25
match (10+) still wins. Importance acts as a tiebreak, not a club.

## Recency is automatic

The retriever computes `recency = 0.5 ^ (age_days / 90)` from the
file's `mtime` (set at ingest from the filesystem). Re-touching a file
without changing its content does NOT update the SHA so it doesn't
reindex — but the `documents.mtime` stays at the original file
timestamp, so recency is honest about when content was written.

This matters: if you `touch foo.md` to "boost it", you've done nothing.
Edit the content if you want it to count as recent.

## Importance × recency interaction

Old + important > new + unimportant, by design:

- 2-year-old ADR (5.0): 4.7× imp boost + 0.001 recency = **strong**
- yesterday's session note (2.5): 2.8× imp boost + 0.99 recency = **moderate**
- 2-year-old session note (2.5): 2.8× imp boost + 0.001 recency = **weak**

This is the right ordering. ADRs encode "the system's brain"; session
notes encode "what someone was working on last week". Both should be
findable; ADRs should outrank.

## Per-chunk importance (today: equal to doc; tomorrow: smarter)

Schema supports `chunks.importance` independent of `documents.importance`.
Today the indexer sets them equal. Future improvements:

- Boost chunks containing the symbol named in the query (set at
  retrieval time as a lightweight rerank signal).
- Boost the first chunk of an ADR (the "Decision" section is usually
  what matters most).
- Demote auto-generated boilerplate inside a code file.

These are deferred until the eval set quantifies the win.

## Never-forget tier

Some content must always surface for relevant queries regardless of
how stale it gets:

- ADRs (`importance 5.0`, half-life 90d)
- Security notes (`4.5`)
- Architecture briefs (`4.5`)
- Incidents (`4.0`)
- Decisions (`4.0`)

For these, after 1 year the recency contribution is ≈ 0.06, but the
importance contribution remains constant. So they slide down a few
slots over time, but are always within k=10 for any matching query.

## When to override importance

We do **not** expose per-file importance overrides today. If a memory
note matters more than its kind suggests, the right move is to convert
it to a higher-tier artefact (decision → ADR, session note →
architecture brief). The kind hierarchy is the lever.

If we ever need to override (we haven't), the implementation is:

```python
# Add to documents schema:
ALTER TABLE documents ADD COLUMN importance_override REAL NULL;
# Update indexer:
doc.importance = override or kind_importance
# Manual via:
sqlite3 memory/vector_indexes/store.sqlite3 \
  "UPDATE documents SET importance_override = 4.5 WHERE path = '...'"
```

## Decay curve reference

`0.5 ^ (age_days / 90)`:

| Age | Recency factor |
| --- | -------------- |
| 0 days | 1.000 |
| 30 days | 0.794 |
| 90 days | 0.500 |
| 180 days | 0.250 |
| 365 days | 0.061 |
| 2 years | 0.004 |

Multiplied by `recency_weight = 0.15`, recency contributes at most
+0.15 to the final score. With BM25 hits routinely scoring 10+, this
is a tiebreaker, not a primary signal.
