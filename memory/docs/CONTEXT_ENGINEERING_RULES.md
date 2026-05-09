# Context engineering rules

How to assemble a token-budgeted memory bundle for an agent task. Read
this before changing the `context` command in
`scripts/memory/cli.py:_cmd_context`.

## The contract

Caller asks for ~N tokens of relevant context. We return:

- A header naming the query, kind filter, and actual token usage.
- A series of sections, each: `## [kind] path (chunk N, score X.XX)`
  followed by the raw chunk text.
- Output is plain markdown so it pastes cleanly into chat / a prompt.

The agent (or human) is then responsible for using this as their
working memory for the task.

## Budget shape

Default budget: **6,000 tokens** (≈ 24,000 chars).

Why 6,000:

- Most agent prompts run with 100k+ context windows; 6k is ~6% — large
  enough for substance, small enough to leave room for the actual
  task, tools, and tool results.
- Average chunk size in the store is ~76 tokens; 6,000 budget ≈ 75
  chunks of headroom. We typically return 8–16 chunks plus neighbours.
- Override per call: `cli context "query" --budget 12000`.

## The fill algorithm

Implemented in `_cmd_context`. Greedy with two passes:

1. **Top-k retrieval pass.** Run `retriever.search(query, k * 2)` to
   over-fetch. Walk hits in score order, skipping any chunk already
   selected. For each candidate compute approx tokens (`len // 4`),
   stop when adding the next would exceed budget. Cap at `k` chunks.

2. **Neighbour expansion pass.** If <90% of budget is used and we have
   at least one hit, expand the *top* hit's same-document neighbours
   (chunk ord ± 1) and add any that fit. This restores broken
   structural context (the section before/after a heading), without
   requiring fancy reranking.

Deduplication is by `chunk_id`. If the same chunk surfaces from BM25
and cosine, it's added once.

## What we deliberately do NOT do

- **No "must-include" pinning** of high-importance docs. If your query
  doesn't match an ADR, we won't shoehorn it in. Importance acts as a
  tiebreak in the retriever, not as a forced injection here.
- **No summarisation.** We return raw chunk text. Summaries lose the
  exact identifier names, line numbers, and code shapes that an agent
  needs to act safely.
- **No recursive expansion.** We expand neighbours of the *top* hit
  once, not transitively. Recursive expansion floods the budget with
  one document.
- **No graph-walk expansion (yet).** A future PR can pull in
  imports/cites neighbours of the top hit; today the cost (extra
  graph load + dedupe) outweighs the benefit on this corpus.

## Calibrating budget

| Task class | Suggested budget | Reasoning |
| ---------- | ---------------- | --------- |
| Bugfix in a known file | 3,000 | One area, narrow context |
| Cross-cutting refactor | 8,000–12,000 | Multiple files + ADRs |
| New feature design | 12,000–20,000 | Lots of architectural recall |
| Incident triage | 6,000 + `--kind incident --kind runbook` | Pull procedural memory first |

## Quality heuristics for the caller

When invoking `cli context`, prefer **specific identifiers over English**:

- Bad: `"how does the agent pipeline work"`
- Good: `"orchestrator critic optimizer DraftEvaluation pipeline"`

Why: BM25 contributes ~50% of the score and rewards identifier overlap.
The hash embedder rewards the same thing because it hashes
n-grams of identifiers. Vague queries get vague results.

## Output format example

```markdown
# Memory context for: critic retry policy
# 9 chunks, ~1840 tokens (budget 6000, kinds=any)

## [code] `backend/app/temporal/activities/production.py` (chunk 0, score 14.48)
"""Production temporal activities for the critic loop."""
from datetime import timedelta
...

## [adr] `docs/adrs/0040-ack-on-success-and-dlq.md` (chunk 7, score 13.56)
## Decision
The critic agent uses an exponential retry policy with three attempts...

## [code] `ai_engine/agents/orchestrator.py` (chunk 22, score 13.10)
def run_critic_pipeline(draft, max_retries=3):
    ...
```

## Failure modes

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| `(no relevant context found)` on a clearly-relevant query | Index stale: file edited but not re-indexed | `cli index` (incremental, ~1 s) |
| Way too many duplicates from one file | Long file with repetitive structure (e.g. CHANGELOG) | Add `--path-prefix` or `--kind` filter |
| Important ADR never appears | ADR words don't match query lexicon | Either rephrase with ADR's own terms, or run `--kind adr` separately |
| Budget exhausted by one giant chunk | A chunk near `MAX_CHUNK_TOKENS` consumed >25% of budget | Lower `MAX_CHUNK_TOKENS` in `indexer.py` and re-index `--full` |
