# memory/

The HireStack AI **engineering memory system** — what every agent and
contributor reads to avoid re-deriving things and re-breaking things.

This directory holds curated, append-mostly knowledge artefacts. The
indexer + retriever live in [`scripts/memory/`](../scripts/memory/);
the agent contract lives in [`AGENTS.md`](../AGENTS.md) at the repo
root.

## Subdirectories

| Path | Contents | Importance |
| ---- | -------- | ---------- |
| [`architecture/`](architecture/) | Cross-cutting design briefs (not ADRs) | 4.5 |
| [`business_logic/`](business_logic/) | Domain rules the code enforces | 3.5 |
| [`context_snapshots/`](context_snapshots/) | Auto-snapshot output (gitignored) | — |
| [`decisions/`](decisions/) | Lightweight reversible decisions | 4.0 |
| [`docs/`](docs/) | The 10 spec docs for this memory system | 3.0 |
| [`graph/`](graph/) | Generated graph.json (output of `cli graph`, gitignored) | — |
| [`incidents/`](incidents/) | Postmortems with root cause + prevention | 4.0 |
| [`releases/`](releases/) | Per-release notes | 2.5 |
| [`scaling/`](scaling/) | Capacity, performance, hot-path rules | 3.5 |
| [`security/`](security/) | RLS, threat model, secret rotation log | 4.5 |
| [`technical_debt/`](technical_debt/) | TD register with cost/benefit | 3.0 |
| [`testing/`](testing/) | Flake registers, slow-test ledger, fixture maps | 2.5 |
| [`vector_indexes/`](vector_indexes/) | SQLite store + WAL files (gitignored) | — |
| [`agent_logs/`](agent_logs/) | Future: per-agent decision logs (gitignored) | — |

## How to use this directory

1. **Reading**: never browse manually. Use the CLI:
   ```bash
   python -m scripts.memory.cli context "<task>"
   python -m scripts.memory.cli search "<topic>" --kind <kind>
   ```
2. **Writing**: see [`docs/MEMORY_UPDATE_WORKFLOW.md`](docs/MEMORY_UPDATE_WORKFLOW.md)
   for the decision tree on where a new note goes.
3. **Re-indexing** after a write:
   ```bash
   python -m scripts.memory.cli index
   ```

## See also

- [`docs/MEMORY_ARCHITECTURE.md`](docs/MEMORY_ARCHITECTURE.md) — system overview
- [`docs/AGENT_MEMORY_PROTOCOL.md`](docs/AGENT_MEMORY_PROTOCOL.md) — agent contract
- [`AGENTS.md`](../AGENTS.md) — the short-form contract at the repo root
