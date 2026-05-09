"""HireStack memory CLI — single entry point for agents and humans.

Examples
--------
    python -m scripts.memory.cli index                     # incremental index
    python -m scripts.memory.cli index --full --embed openai
    python -m scripts.memory.cli search "critic retry policy"
    python -m scripts.memory.cli search "supabase rls" --kind context --kind adr
    python -m scripts.memory.cli graph
    python -m scripts.memory.cli neighbours code:app.api.routes.generate.jobs --depth 1
    python -m scripts.memory.cli summary
    python -m scripts.memory.cli context "fixing flaky temporal test" --budget 6000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

from . import graph as graph_mod
from . import indexer
from .retriever import Hit, Retriever
from .store import REPO_ROOT, Store


def _cmd_index(args: argparse.Namespace) -> int:
    return indexer._main([
        *(["--full"] if args.full else []),
        "--embed", args.embed,
        *(["-v"] if args.verbose else []),
    ])


def _format_hit(h: Hit, *, with_text: bool, max_chars: int) -> str:
    head = (
        f"  {h.score:6.2f}  [{h.kind:<14}]  {h.path}#{h.ord}\n"
        f"            bm25={h.bm25:.2f} cosine={h.cosine:.2f} importance={h.importance:.2f}"
    )
    if not with_text:
        return head
    snippet = h.text.strip().replace("\n", "\n            ")
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "…"
    return f"{head}\n            ----\n            {snippet}"


def _cmd_search(args: argparse.Namespace) -> int:
    r = Retriever(embed_mode=args.embed)
    hits = r.search(args.query, k=args.k, kinds=args.kind or None, path_prefix=args.path_prefix)
    if not hits:
        print("(no results)")
        return 0
    if args.json:
        print(json.dumps([h.__dict__ for h in hits], indent=2, default=str))
        return 0
    print(f"query: {args.query!r}  →  {len(hits)} hits")
    for h in hits:
        print(_format_hit(h, with_text=not args.short, max_chars=args.snippet))
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    payload = graph_mod.build_graph(write=not args.dry_run)
    counts = payload["counts"]
    print(
        f"graph: nodes={counts['nodes']} edges={counts['edges']} "
        f"(imports={counts['import_edges']}, "
        f"memory→code={counts['memory_to_code_edges']}, "
        f"memory→adr={counts['memory_to_adr_edges']})"
    )
    if not args.dry_run:
        print(f"wrote {graph_mod.GRAPH_PATH.relative_to(REPO_ROOT)}")
    return 0


def _cmd_neighbours(args: argparse.Namespace) -> int:
    nbrs = graph_mod.neighbours(args.node_id, depth=args.depth)
    if not nbrs:
        print(f"no neighbours for {args.node_id}")
        return 0
    print(f"{args.node_id} — {len(nbrs)} neighbours within depth {args.depth}")
    for n in nbrs:
        print(f"  {n.get('kind','?'):<10}  {n.get('path', n['id'])}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    s = Store().stats()
    print(json.dumps(s, indent=2, default=str))
    return 0


def _cmd_context(args: argparse.Namespace) -> int:
    """Assemble a token-budgeted context block for an agent task.

    This is the function agents should call when starting a task. It runs
    the retriever, expands hits with same-doc neighbours when budget allows,
    deduplicates by chunk, and prints a structured markdown bundle.
    """
    r = Retriever(embed_mode=args.embed)
    hits = r.search(args.query, k=args.k * 2, kinds=args.kind or None)
    if not hits:
        print("(no relevant context found)")
        return 0
    selected: List[Hit] = []
    seen_chunks = set()
    used_tokens = 0
    # Greedy budget fill: take top hits, then expand neighbours of the very top hit.
    for h in hits:
        if h.chunk_id in seen_chunks:
            continue
        approx = max(1, len(h.text) // 4)
        if used_tokens + approx > args.budget:
            break
        selected.append(h)
        seen_chunks.add(h.chunk_id)
        used_tokens += approx
        if len(selected) >= args.k:
            break
    # Expand the top hit if budget remains.
    if selected and used_tokens < args.budget * 0.9:
        for nb in r.neighbours(selected[0], span=1):
            if nb.chunk_id in seen_chunks:
                continue
            approx = max(1, len(nb.text) // 4)
            if used_tokens + approx > args.budget:
                break
            selected.append(nb)
            seen_chunks.add(nb.chunk_id)
            used_tokens += approx
    print(f"# Memory context for: {args.query}")
    print(f"# {len(selected)} chunks, ~{used_tokens} tokens "
          f"(budget {args.budget}, kinds={args.kind or 'any'})")
    print()
    for h in selected:
        print(f"## [{h.kind}] `{h.path}` (chunk {h.ord}, score {h.score:.2f})")
        print(h.text.strip())
        print()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="scripts.memory.cli", description="HireStack memory CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("index", help="Walk the repo and (re)index changed files")
    pi.add_argument("--full", action="store_true")
    pi.add_argument("--embed", choices=("auto", "off", "openai"), default="auto")
    pi.add_argument("-v", "--verbose", action="store_true")
    pi.set_defaults(func=_cmd_index)

    ps = sub.add_parser("search", help="Hybrid BM25 + cosine search")
    ps.add_argument("query")
    ps.add_argument("-k", type=int, default=8)
    ps.add_argument("--kind", action="append", default=[],
                    help="Filter by kind (repeatable). e.g. --kind adr --kind incident")
    ps.add_argument("--path-prefix", default=None)
    ps.add_argument("--short", action="store_true", help="Headers only, no snippets")
    ps.add_argument("--snippet", type=int, default=600)
    ps.add_argument("--json", action="store_true")
    ps.add_argument("--embed", choices=("auto", "off", "openai"), default="auto")
    ps.set_defaults(func=_cmd_search)

    pg = sub.add_parser("graph", help="Rebuild the knowledge graph at memory/graph/graph.json")
    pg.add_argument("--dry-run", action="store_true")
    pg.set_defaults(func=_cmd_graph)

    pn = sub.add_parser("neighbours", help="Show graph neighbours of a node id")
    pn.add_argument("node_id")
    pn.add_argument("--depth", type=int, default=1)
    pn.set_defaults(func=_cmd_neighbours)

    pu = sub.add_parser("summary", help="Print store statistics")
    pu.set_defaults(func=_cmd_summary)

    pc = sub.add_parser("context", help="Assemble token-budgeted context block")
    pc.add_argument("query")
    pc.add_argument("-k", type=int, default=8)
    pc.add_argument("--budget", type=int, default=6000)
    pc.add_argument("--kind", action="append", default=[])
    pc.add_argument("--embed", choices=("auto", "off", "openai"), default="auto")
    pc.set_defaults(func=_cmd_context)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
