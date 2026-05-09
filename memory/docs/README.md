# memory/docs

The 10 design specifications for the HireStack AI memory system.
Read order for new contributors:

1. [`MEMORY_ARCHITECTURE.md`](MEMORY_ARCHITECTURE.md) — what + why
2. [`AGENT_MEMORY_PROTOCOL.md`](AGENT_MEMORY_PROTOCOL.md) — the contract
3. [`MEMORY_UPDATE_WORKFLOW.md`](MEMORY_UPDATE_WORKFLOW.md) — where things go
4. [`MEMORY_RETRIEVAL_STRATEGY.md`](MEMORY_RETRIEVAL_STRATEGY.md) — how ranking works
5. [`CONTEXT_ENGINEERING_RULES.md`](CONTEXT_ENGINEERING_RULES.md) — token budgets
6. [`MEMORY_PIPELINE.md`](MEMORY_PIPELINE.md) — ingestion mechanics
7. [`VECTOR_SEARCH_DESIGN.md`](VECTOR_SEARCH_DESIGN.md) — embeddings + upgrade path
8. [`KNOWLEDGE_GRAPH_DESIGN.md`](KNOWLEDGE_GRAPH_DESIGN.md) — node/edge schema
9. [`MEMORY_RANKING_SYSTEM.md`](MEMORY_RANKING_SYSTEM.md) — importance + decay
10. [`FAILURE_LEARNING_SYSTEM.md`](FAILURE_LEARNING_SYSTEM.md) — incident schema

The short-form contract for everyday use lives at [`AGENTS.md`](../../AGENTS.md)
and [`.github/copilot-instructions.md`](../../.github/copilot-instructions.md).
