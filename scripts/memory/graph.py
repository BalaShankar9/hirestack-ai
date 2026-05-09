"""Knowledge graph builder for the HireStack codebase + memory.

Produces a JSON graph at ``memory/graph/graph.json`` describing:

- ``files``  — every Python file in ``backend/`` and ``ai_engine/``
- ``imports`` — directed edges from importer → imported (resolved within repo)
- ``memory_refs`` — edges from memory notes / ADRs / context files to code
                    files they mention (path-token match)
- ``adr_refs`` — edges between memory notes and ADRs they cite (id match)

Pure-stdlib AST walk + regex for memory cross-references. NetworkX is
*not* required — we emit a flat node/edge JSON that any consumer
(retriever, future neo4j export, frontend visualiser) can ingest.

Usage
-----
    python -m scripts.memory.cli graph
    # or programmatically:
    from scripts.memory.graph import build_graph
    g = build_graph()
"""

from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .store import REPO_ROOT

# Scope of the import graph. Kept narrow on purpose to keep node count tractable.
CODE_ROOTS: Tuple[Path, ...] = (REPO_ROOT / "backend" / "app", REPO_ROOT / "ai_engine", REPO_ROOT / "scripts")

# Scope of the memory cross-reference graph.
MEMORY_ROOTS: Tuple[Path, ...] = (
    REPO_ROOT / "memory",
    REPO_ROOT / "memories" / "repo",
    REPO_ROOT / "context",
    REPO_ROOT / "docs",
)

ADR_REF_RE = re.compile(r"\bADR[- ]?(\d{3,4})\b", re.IGNORECASE)
PATH_REF_RE = re.compile(r"`([^`\s]+\.[a-z]{2,4})`")

GRAPH_PATH = REPO_ROOT / "memory" / "graph" / "graph.json"


@dataclass
class Graph:
    nodes: Dict[str, dict] = field(default_factory=dict)
    edges: List[dict] = field(default_factory=list)

    def add_node(self, node_id: str, **attrs: object) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, **attrs}
        else:
            self.nodes[node_id].update({k: v for k, v in attrs.items() if v is not None})

    def add_edge(self, src: str, dst: str, kind: str, **attrs: object) -> None:
        self.edges.append({"src": src, "dst": dst, "kind": kind, **attrs})

    def to_json(self) -> dict:
        return {
            "version": 1,
            "generated_at": time.time(),
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
        }


# ---- Code: import graph -------------------------------------------------

def _module_for(path: Path) -> str:
    """Convert backend/app/api/routes/generate/jobs.py → app.api.routes.generate.jobs.

    Mirrors the actual sys.path layout: ``backend/`` is on path so ``app.*`` is
    importable, ``ai_engine/`` is on path so ``ai_engine.*`` is importable.
    ``scripts/`` is rooted at repo for ``scripts.*``.
    """
    rel = path.relative_to(REPO_ROOT).with_suffix("").as_posix().split("/")
    if rel[0] == "backend":
        rel = rel[1:]      # strip "backend"
    return ".".join(rel)


def _walk_python_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts or ".venv" in p.parts:
            continue
        yield p


def _resolve_import(module: str, current_module: str, known: Set[str]) -> Optional[str]:
    """Return the matching known module if ``module`` resolves inside the repo."""
    if module in known:
        return module
    # Try walking up: ``app.api.routes.generate.jobs`` may import ``.helpers`` which
    # the AST already turned into ``app.api.routes.generate.helpers``.
    if module.startswith(("app.", "ai_engine.", "scripts.")):
        # Match the longest known prefix.
        parts = module.split(".")
        while parts:
            cand = ".".join(parts)
            if cand in known:
                return cand
            parts.pop()
    return None


def _collect_imports(tree: ast.AST, current_module: str) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            level = node.level or 0
            module = node.module
            if level:
                base = current_module.split(".")
                # Drop ``level`` packages from the current module to resolve relative.
                if level <= len(base):
                    base = base[:-level]
                    module = ".".join(base + [module]) if module else ".".join(base)
            out.append((module, node.lineno))
    return out


def _build_import_graph(graph: Graph) -> int:
    """Add code nodes + import edges. Returns number of edges added."""
    files: List[Tuple[Path, str]] = []
    for root in CODE_ROOTS:
        if not root.exists():
            continue
        for path in _walk_python_files(root):
            files.append((path, _module_for(path)))
    known = {m for _, m in files}
    for path, mod in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        graph.add_node(
            f"code:{mod}",
            kind="code",
            path=rel,
            module=mod,
            loc=sum(1 for _ in path.read_text("utf-8", errors="ignore").splitlines()),
        )
    edges = 0
    for path, mod in files:
        try:
            src = path.read_text("utf-8", errors="ignore")
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        seen: Set[str] = set()
        for imported, lineno in _collect_imports(tree, mod):
            resolved = _resolve_import(imported, mod, known)
            if resolved and resolved != mod and resolved not in seen:
                graph.add_edge(f"code:{mod}", f"code:{resolved}", "imports", lineno=lineno)
                seen.add(resolved)
                edges += 1
    return edges


# ---- Memory + ADR cross-references --------------------------------------

def _walk_md_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*.md"):
        if any(part in (".git", "node_modules", ".venv") for part in p.parts):
            continue
        yield p


def _build_memory_refs(graph: Graph) -> Tuple[int, int]:
    code_paths_to_node: Dict[str, str] = {}
    for nid, node in graph.nodes.items():
        if node.get("kind") == "code":
            code_paths_to_node[node["path"]] = nid
    code_basenames: Dict[str, List[str]] = {}
    for path, nid in code_paths_to_node.items():
        base = Path(path).name
        code_basenames.setdefault(base, []).append(nid)
    # ADR id → node
    adr_node_by_id: Dict[str, str] = {}
    memory_nodes: List[Tuple[str, Path]] = []
    for root in MEMORY_ROOTS:
        for md in _walk_md_files(root):
            rel = md.relative_to(REPO_ROOT).as_posix()
            kind = "adr" if "/adrs/" in rel else (
                "memory" if "memories/repo" in rel else (
                    "context" if rel.startswith("context/") else "doc"
                )
            )
            nid = f"{kind}:{rel}"
            graph.add_node(nid, kind=kind, path=rel, title=md.stem)
            memory_nodes.append((nid, md))
            if kind == "adr":
                m = re.match(r"^(\d{4})-", md.stem)
                if m:
                    adr_node_by_id[m.group(1).lstrip("0") or "0"] = nid
    code_edges = 0
    adr_edges = 0
    for nid, md in memory_nodes:
        try:
            text = md.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        # path mentions
        seen_paths: Set[str] = set()
        for path_ref in PATH_REF_RE.findall(text):
            ref = path_ref.lstrip("./")
            target = code_paths_to_node.get(ref)
            if target is None:
                # try basename
                bn = Path(ref).name
                cand = code_basenames.get(bn)
                if cand and len(cand) == 1:
                    target = cand[0]
            if target and target not in seen_paths:
                graph.add_edge(nid, target, "mentions")
                seen_paths.add(target)
                code_edges += 1
        # ADR mentions
        seen_adrs: Set[str] = set()
        for adr_id in ADR_REF_RE.findall(text):
            normalised = str(int(adr_id))
            target = adr_node_by_id.get(normalised)
            if target and target != nid and target not in seen_adrs:
                graph.add_edge(nid, target, "cites")
                seen_adrs.add(target)
                adr_edges += 1
    return code_edges, adr_edges


def build_graph(write: bool = True) -> dict:
    g = Graph()
    n_imports = _build_import_graph(g)
    n_code_refs, n_adr_refs = _build_memory_refs(g)
    payload = g.to_json()
    payload["counts"] = {
        "nodes": len(payload["nodes"]),
        "edges": len(payload["edges"]),
        "import_edges": n_imports,
        "memory_to_code_edges": n_code_refs,
        "memory_to_adr_edges": n_adr_refs,
    }
    if write:
        GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
        GRAPH_PATH.write_text(json.dumps(payload, indent=2))
    return payload


def neighbours(node_id: str, graph_payload: Optional[dict] = None, depth: int = 1) -> List[dict]:
    """Return outbound + inbound neighbours up to ``depth`` hops."""
    payload = graph_payload or json.loads(GRAPH_PATH.read_text("utf-8"))
    nodes_by_id = {n["id"]: n for n in payload["nodes"]}
    out_idx: Dict[str, List[dict]] = {}
    in_idx: Dict[str, List[dict]] = {}
    for e in payload["edges"]:
        out_idx.setdefault(e["src"], []).append(e)
        in_idx.setdefault(e["dst"], []).append(e)
    frontier = {node_id}
    seen = {node_id}
    for _ in range(depth):
        next_frontier: Set[str] = set()
        for n in frontier:
            for e in out_idx.get(n, []):
                if e["dst"] not in seen:
                    next_frontier.add(e["dst"])
            for e in in_idx.get(n, []):
                if e["src"] not in seen:
                    next_frontier.add(e["src"])
        seen |= next_frontier
        frontier = next_frontier
    return [nodes_by_id[n] for n in seen if n in nodes_by_id and n != node_id]
