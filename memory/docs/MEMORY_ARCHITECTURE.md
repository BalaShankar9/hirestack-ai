# Memory architecture

> Status: shipped in m12-pr20 — `scripts/memory/` toolchain + `/memory/`
> tree + this docs set. Future work: pgvector backend, agent feedback loop.

The HireStack AI memory system is a **content-addressed, hybrid-retrievable
knowledge base** for everything an engineering agent needs to act safely
in this repo: ADRs, runbooks, incident notes, context briefs, code
imports, security posture, and historical decisions.

It is built on top of surfaces that already existed (`docs/adrs/`,
`docs/PROJECT_JOURNAL.md`, `context/*.md`, `/memories/repo/*.md`,
`docs/superpowers/`). We did not replace them — we ingested them and
wired retrieval + ranking on top.

## Layered model

The five-layer cognitive model (Kahneman / Tulving) maps cleanly onto
existing artefacts in this repo. We use the same names so contributors
can reason about where new information belongs:

| Layer | Purpose | This repo's surface |
| ----- | ------- | ------------------- |
| **Working** | The current task's context bundle (transient, < 1 turn) | `scripts/memory/cli.py context "<task>"` |
| **Episodic** | What happened, when, why | `/memories/repo/*.md` (PR notes), `memory/incidents/`, `memory/releases/` |
| **Semantic** | Stable facts about the system | `context/*.md`, `docs/architecture/`, `memory/business_logic/` |
| **Procedural** | How to do things | `docs/runbooks/`, `docs/superpowers/`, `memory/testing/` |
| **Decisional** | Why we chose X over Y | `docs/adrs/`, `memory/decisions/` |

## Physical layout

```
memory/
  architecture/        Design briefs, system maps                         [importance 4.5]
  business_logic/      Hireability rules, scoring rubrics, JD/resume contracts  [3.5]
  context_snapshots/   Auto-snapshots from `cli context` runs (gitignored)
  decisions/           Lightweight "why we picked X" notes (lighter than ADRs)  [4.0]
  docs/                The 10 spec docs (this directory)                  [3.0]
  graph/               Generated graph.json (output of `cli graph`)
  incidents/           Postmortems with root cause + prevention           [4.0]
  releases/            Per-release notes (produces episodic memory)       [2.5]
  scaling/             Capacity, performance, hot-path rules              [3.5]
  security/            RLS policies, threat model, key rotation log       [4.5]
  technical_debt/      TD register, cost/benefit, target PRs              [3.0]
  testing/             Flake registers, slow-test ledger, fixture map     [2.5]
  vector_indexes/      SQLite store + WAL files (gitignored)
  agent_logs/          Future: per-agent decision logs (gitignored)
```

```
scripts/memory/
  __init__.py          Package entry
  store.py             SQLite + BM25 inverted index + embedding cache
  embed.py             HashEmbedder (default), OpenAIEmbedder (upgrade)
  indexer.py           Walks repo, chunks, embeds, persists
  retriever.py         Hybrid BM25 + cosine + recency + importance
  graph.py             AST import graph + memory cross-references
  cli.py               Single CLI: index | search | graph | summary | context | neighbours
```

## Stack choices

We use **stdlib + numpy only**. Specifically NOT installed:

- `chromadb` / `qdrant-client` — would drag PyTorch (~1 GB) into CI for
  marginal quality gain over BM25 + hash embeddings on a 7k-chunk corpus.
- `sentence_transformers` — same. Use OpenAI `text-embedding-3-small`
  when real semantic search is needed (see `VECTOR_SEARCH_DESIGN.md`).
- `networkx` — the graph we need (~600 nodes, 1700 edges) is small
  enough that a flat JSON + dict-of-lists adjacency is the right call.
- `tiktoken` — we approximate token count as `len(text) // 4`, which is
  within ±15% for English/code and never blocks correctness.

This is reversible. The `Embedder` interface is one method
(`embed(texts) -> ndarray[N, d]`). When a future PR migrates to
pgvector or Qdrant, only `store.py` and `retriever._cosine` change.

## Where content comes from

Every file under the include globs in `scripts/memory/indexer.py:INCLUDE_GLOBS`
is content-addressed (sha256[:40]) and skipped on re-index if unchanged.
Current corpus (m12-pr20 baseline):

- 697 documents
- 7,330 chunks
- 24,843 unique terms in the BM25 inverted index
- 7,330 hash embeddings (384-d)
- 635 graph nodes, 1,722 edges
- ~44 MB SQLite DB

## What this is NOT

- Not a replacement for git history. Use `git log` for "what changed".
- Not a chat memory. The `/memories/repo/` Copilot scope is per-conversation
  session memory — it's *ingested* here so any agent can read past
  sessions, but the source of truth still lives there.
- Not a CRM. No people, no PII, no customer data. Engineering memory only.

## Cross-references

- Pipeline mechanics → [MEMORY_PIPELINE.md](MEMORY_PIPELINE.md)
- Vector design + upgrade path → [VECTOR_SEARCH_DESIGN.md](VECTOR_SEARCH_DESIGN.md)
- Graph design → [KNOWLEDGE_GRAPH_DESIGN.md](KNOWLEDGE_GRAPH_DESIGN.md)
- How retrieval ranks → [MEMORY_RETRIEVAL_STRATEGY.md](MEMORY_RETRIEVAL_STRATEGY.md)
- Token budget rules → [CONTEXT_ENGINEERING_RULES.md](CONTEXT_ENGINEERING_RULES.md)
- Agent contract → [AGENT_MEMORY_PROTOCOL.md](AGENT_MEMORY_PROTOCOL.md)
- Update workflow → [MEMORY_UPDATE_WORKFLOW.md](MEMORY_UPDATE_WORKFLOW.md)
- Importance + decay → [MEMORY_RANKING_SYSTEM.md](MEMORY_RANKING_SYSTEM.md)
- Failure capture → [FAILURE_LEARNING_SYSTEM.md](FAILURE_LEARNING_SYSTEM.md)
