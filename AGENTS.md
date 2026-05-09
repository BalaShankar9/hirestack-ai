# HireStack AI — Agent contract

> **Mandatory pre-task and post-task protocol for every AI agent
> (Copilot, Claude, Cursor, custom subagents) and every human using
> AI assistance in this repo.**

## Pre-task

Before writing code, opening a PR, or making a non-trivial decision,
load relevant memory:

```bash
python -m scripts.memory.cli context "<5-12 word task description>" --budget 6000
```

Specialised lookups:

```bash
python -m scripts.memory.cli search "<topic>" --kind adr --kind decision   # has this been decided?
python -m scripts.memory.cli search "<symptom>" --kind incident             # has this broken before?
python -m scripts.memory.cli search "<operation>" --kind runbook            # is there a procedure?
```

If you've edited files since the last index, re-index first
(~1 second incremental):

```bash
python -m scripts.memory.cli index
```

## Post-task

After shipping (PR opened, decision made, incident resolved), write a
session note to `/memories/repo/<slug>.md` containing:

- title and date
- PR / commit link
- why this happened
- what changed (with backtick-wrapped file paths so the graph picks them up)
- validation evidence (test counts, smoke results)
- follow-ups
- linked ADRs / incidents / prior memory notes

Then re-index so the note is queryable for the next task:

```bash
python -m scripts.memory.cli index
```

## Where things go (decision tree)

| Trigger | Target |
| ------- | ------ |
| PR shipped | `/memories/repo/<slug>-shipped.md` |
| Irreversible architectural choice | `docs/adrs/NNNN-<slug>.md` (+ memory note linking it) |
| Production incident | `memory/incidents/<YYYY-MM-DD>-<slug>.md` |
| New operational procedure | `docs/runbooks/<slug>.md` |
| Reversible decision worth remembering | `memory/decisions/<slug>.md` |
| Domain rule the code enforces | `memory/business_logic/<slug>.md` |
| Security posture / threat model entry | `memory/security/<slug>.md` |
| Performance / capacity decision | `memory/scaling/<slug>.md` |
| Tech debt with cost/benefit | `memory/technical_debt/<slug>.md` |

## Full specifications

- [memory/docs/MEMORY_ARCHITECTURE.md](memory/docs/MEMORY_ARCHITECTURE.md) — system design
- [memory/docs/AGENT_MEMORY_PROTOCOL.md](memory/docs/AGENT_MEMORY_PROTOCOL.md) — the long version of this file
- [memory/docs/MEMORY_UPDATE_WORKFLOW.md](memory/docs/MEMORY_UPDATE_WORKFLOW.md) — what goes where, and why
- [memory/docs/FAILURE_LEARNING_SYSTEM.md](memory/docs/FAILURE_LEARNING_SYSTEM.md) — incident note schema
- [memory/docs/MEMORY_RETRIEVAL_STRATEGY.md](memory/docs/MEMORY_RETRIEVAL_STRATEGY.md) — how ranking actually works
- [memory/docs/CONTEXT_ENGINEERING_RULES.md](memory/docs/CONTEXT_ENGINEERING_RULES.md) — token budget rules
- [memory/docs/MEMORY_PIPELINE.md](memory/docs/MEMORY_PIPELINE.md) — ingestion mechanics
- [memory/docs/VECTOR_SEARCH_DESIGN.md](memory/docs/VECTOR_SEARCH_DESIGN.md) — embedding stack + upgrade path
- [memory/docs/KNOWLEDGE_GRAPH_DESIGN.md](memory/docs/KNOWLEDGE_GRAPH_DESIGN.md) — graph schema
- [memory/docs/MEMORY_RANKING_SYSTEM.md](memory/docs/MEMORY_RANKING_SYSTEM.md) — importance + decay

## Rationale (one paragraph)

We have ADRs, runbooks, session notes, context briefs, and a project
journal — all valuable, all underused because nobody can find what
they need at the moment they need it. The memory system is the
retrieval + ranking layer that makes those existing assets
agent-actionable. Skipping the protocol wastes the system; following
it compounds.

## Quality bar

- **Be specific.** Backtick-wrap file paths
  (`` `backend/app/api/routes/generate/jobs.py` ``). Cite ADRs by id
  (`ADR-0040`). Specifics get picked up by the graph builder and
  surface for future queries.
- **Use concrete validation.** "Tests pass" is useless. "109/109 tests
  green in 2.94s" is useful.
- **One topic per memory note.** Easier to retrieve, easier to age out.
- **Re-index after writing.** Otherwise your note isn't queryable for
  the next task.

## Don't

- Don't write to `/memories/repo/` for choices that are irreversible
  (use ADRs).
- Don't update an old ADR in place to flip its decision (open a new
  one and link both directions).
- Don't write memory notes with no concrete identifiers — the graph
  ignores them and BM25 can't index them.
- Don't `touch` files to "boost" them — recency uses content sha, not
  filesystem mtime tricks.
