# Knowledge graph design

The knowledge graph is the read-side artefact for "what depends on what,
and what mentions what". Built by `scripts/memory/graph.py`, persisted
to `memory/graph/graph.json`. Today's snapshot:

- **635 nodes**
- **1,722 edges**
  - **1,215** code → code (`imports`)
  - **424** memory/doc → code (`mentions`)
  - **83** memory → ADR (`cites`)

## Node types

| Kind | Source | Example id |
| ---- | ------ | ---------- |
| `code` | `*.py` under `backend/app/`, `ai_engine/`, `scripts/` | `code:app.api.routes.generate.jobs` |
| `adr` | `docs/adrs/NNNN-*.md` | `adr:docs/adrs/0040-ack-on-success-and-dlq.md` |
| `context` | `context/*.md` | `context:context/ENGINEERING_CONTEXT.md` |
| `memory` | `memories/repo/*.md` | `memory:memories/repo/m12-pr19-td1-split-jobs-shipped.md` |
| `doc` | other markdown under `docs/`, `memory/` | `doc:docs/PROJECT_JOURNAL.md` |

Each node carries minimal attributes:

```json
{ "id": "code:app.api.routes.generate.jobs",
  "kind": "code",
  "path": "backend/app/api/routes/generate/jobs.py",
  "module": "app.api.routes.generate.jobs",
  "loc": 2358 }
```

## Edge types

| Kind | Source → Target | Built by |
| ---- | --------------- | -------- |
| `imports` | code → code | `_build_import_graph` (AST: `ast.Import`, `ast.ImportFrom`, including relative imports via `level`) |
| `mentions` | adr/memory/context/doc → code | `_build_memory_refs` regex on `` ` ``-wrapped paths (`PATH_REF_RE`) |
| `cites` | adr/memory/context/doc → adr | `_build_memory_refs` regex on `ADR-NNNN` (`ADR_REF_RE`) |

Edges may carry `lineno` (for `imports`) for click-through into the
source location.

## Why a flat JSON, not Neo4j / NetworkX

- 635 nodes / 1.7k edges is comfortably in-memory as a dict-of-lists.
  `json.loads(graph.read_text())` takes ~5 ms.
- The hot operations are: list outbound neighbours, list inbound
  neighbours, BFS to depth 1–2. All are one-line dict lookups.
- A graph DB makes sense only when (a) the graph is too big for memory
  or (b) we need transactional updates from many writers. Neither
  applies. We rebuild from scratch in ~1 second.
- A future MCP server / IDE plugin can consume the JSON directly with
  no extra service.

## Resolution rules (imports)

`_resolve_import` does sys.path-aware resolution:

- `backend/app/...` → module `app.x.y` (we strip the `backend/` prefix
  because that's how it's imported in this repo).
- `ai_engine/...` → module `ai_engine.x.y`.
- `scripts/...` → module `scripts.x.y`.

Relative imports (`from .helpers import …`) become `app.x.y.helpers`
by walking up `level` segments from the current module before joining.

Imports that don't resolve to a known node (third-party packages,
stdlib) are dropped. We do not pollute the graph with `code:numpy`.

## Cross-reference rules (memory)

For every markdown file under `memory/`, `memories/repo/`, `context/`,
`docs/`:

1. Extract every backtick-wrapped string with at least one `.`
   (heuristic for "this looks like a path"). Strip leading `./`. Try
   exact `path == known_code_path` first; if no match, try basename and
   accept only when the basename is unambiguous (single match across
   all code files). Add a `mentions` edge.
2. Extract every `ADR-NNNN` / `ADR NNNN`. Normalise the number and look
   it up in `adr_node_by_id`. Add a `cites` edge.

Both passes deduplicate within a single source file.

## Read API

Programmatic:

```python
from scripts.memory.graph import build_graph, neighbours

g = build_graph(write=False)            # build in memory only
nbrs = neighbours("code:app.api.routes.generate.jobs", g, depth=1)
```

CLI:

```bash
python -m scripts.memory.cli graph              # rebuild + write graph.json
python -m scripts.memory.cli neighbours code:app.api.routes.generate.jobs --depth 1
```

`neighbours` returns the *union* of inbound and outbound neighbours
(directed graph but you usually want both directions when reasoning
about blast radius).

## Use cases

| Question | Query |
| -------- | ----- |
| "What memory notes mention `jobs.py`?" | inbound `mentions` edges to `code:app.api.routes.generate.jobs` |
| "What ADRs does this PR memory note cite?" | outbound `cites` edges from the memory node |
| "What's the blast radius of changing `_module_state.py`?" | inbound `imports` edges to that node, depth 2 |
| "What modules does the orchestrator depend on?" | outbound `imports` edges from `code:ai_engine.agents.orchestrator` |

## Limits + future work

- **No cross-language edges.** TypeScript imports inside `frontend/`
  are not parsed yet. Follow-up: `_build_ts_import_graph` using a small
  regex on `import … from "..."`. Out of scope for m12-pr20.
- **No PR / commit nodes.** When the agent feedback loop ships
  (m12-pr22), each PR memory note will become a node and edges will
  connect to the files it touched. The data is there
  (`/memories/repo/*.md` already names the changed files).
- **No semantic edges.** Edge "similarity" via cosine of node
  descriptions is plausible future work but adds complexity for
  speculative value.
