#!/usr/bin/env python3
"""
Architecture anti-pattern enforcement.

Catches the highest-blast-radius forbidden patterns from
docs/architecture/WORLD_CLASS_ARCHITECTURE_BLUEPRINT.md §17.

Each check fails CI on first hit. Add an exemption ONLY by listing the
specific file path with rationale and a TODO(YYYY-MM-DD) sunset.

Run: python scripts/governance/check_architecture.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def files(rel_root: str, suffixes: tuple[str, ...]) -> list[pathlib.Path]:
    base = ROOT / rel_root
    if not base.exists():
        return []
    out: list[pathlib.Path] = []
    for suf in suffixes:
        out.extend(p for p in base.rglob(f"*{suf}") if "node_modules" not in p.parts)
    return out


def grep(pattern: str, paths: list[pathlib.Path], flags: int = 0) -> list[tuple[pathlib.Path, int, str]]:
    rx = re.compile(pattern, flags)
    hits: list[tuple[pathlib.Path, int, str]] = []
    for p in paths:
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append((p, i, line.rstrip()))
        except OSError:
            continue
    return hits


def report(label: str, hits: list[tuple[pathlib.Path, int, str]], allowlist: set[str] = frozenset()) -> int:
    if not hits:
        print(f"PASS  {label}")
        return 0
    real = [(p, i, l) for p, i, l in hits if str(p.relative_to(ROOT)) not in allowlist]
    if not real:
        print(f"PASS  {label} (all hits exempted)")
        return 0
    print(f"FAIL  {label}", file=sys.stderr)
    for p, i, l in real[:30]:
        print(f"      {p.relative_to(ROOT)}:{i}: {l[:160]}", file=sys.stderr)
    if len(real) > 30:
        print(f"      ... and {len(real) - 30} more", file=sys.stderr)
    return 1


def main() -> int:
    rc = 0

    # AP-2: native EventSource forbidden in frontend (must use @microsoft/fetch-event-source).
    # Allow inside the SSE client wrapper itself, plus type defs / vendored libs.
    rc |= report(
        "AP-2 native EventSource forbidden",
        grep(r"\bnew EventSource\b", files("frontend/src", (".ts", ".tsx", ".js"))),
        allowlist={
            # The wrapper module is the one place permitted to instantiate the polyfill if ever needed.
            "frontend/src/lib/sse/eventSourceClient.ts",
            # TODO(2026-09-30): port useApplication SSE consumer to the SSE client wrapper (P0-7 / M9-pr33).
            "frontend/src/modules/application/hooks/useApplication.ts",
        },
    )

    # AP-4: code_ref / arbitrary callable bound outside the resolver registry.
    # Heuristic: literal `code_ref=` outside the registry implementation + its tests.
    py = files("ai_engine", (".py",)) + files("backend/app", (".py",))
    AP4_ALLOW = {
        "ai_engine/agents/tools.py",                  # the registry resolvers themselves
        "ai_engine/registry/supabase_store.py",       # registry persistence layer
        "ai_engine/registry/seed.py",                 # static seed catalog (PR m7-pr29)
        "ai_engine/registry/resolvers.py",            # canonical RESOLVERS allowlist (ADR-0033)
    }
    rc |= report(
        "AP-4 code_ref outside RESOLVERS registry",
        [
            h for h in grep(r"\bcode_ref\s*=", py)
            if str(h[0].relative_to(ROOT)) not in AP4_ALLOW
            and "/tests/" not in h[0].as_posix()
            and not h[0].as_posix().endswith("_test.py")
        ],
    )

    # AP-8: workflows must not call non-deterministic stdlib (datetime.now, time.time, uuid4, random).
    wf = files("backend/app/temporal/workflows", (".py",))
    if wf:
        bad = (
            grep(r"\bdatetime\.now\b", wf)
            + grep(r"\btime\.time\(\)", wf)
            + grep(r"\buuid\.uuid4\b", wf)
            + grep(r"\brandom\.\w+\(", wf)
        )
        rc |= report("AP-8 non-determinism in Temporal workflow", bad)

    # AP-10: hardcoded secrets — narrow patterns for high-confidence catches.
    # Exclude tests/ (legitimate fixtures like AKIAIOSFODNN7EXAMPLE) and avoid
    # spurious matches on adr filenames containing `risk-` (which trips a naive
    # `sk-` regex). Require a key-like prefix character class boundary.
    src = [
        p for p in (
            files("ai_engine", (".py",))
            + files("backend", (".py",))
            + files("frontend/src", (".ts", ".tsx", ".js"))
        )
        if "/tests/" not in p.as_posix() and not p.as_posix().endswith("_test.py")
    ]
    rc |= report(
        "AP-10 likely hardcoded secret",
        grep(
            r"(?<![A-Za-z0-9-])sk-(?:proj-)?[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}",
            src,
        ),
    )

    # AP-1 / AP-2 frontend additional: bare fetch with EventSource-style usage warning.
    # (Skip: already handled by lint/types.)

    # AP-12: cross-context import — covered by .importlinter, but flag obvious offenders fast.
    # backend.* must NOT be imported from ai_engine.
    # Allowlist sunset 2026-08-01 — same date as ruff TID251 carve-outs in
    # pyproject.toml. These four files use lazy `from backend.*` inside
    # try/except ImportError to avoid hard coupling at module import time.
    # Tracked under M11-pr39 → fully eliminate by carving the legacy bridge
    # into ai_engine.api adapters per ADR-0014 / blueprint §6.
    rc |= report(
        "AP-12 ai_engine importing backend.*",
        grep(r"^\s*from\s+backend(\.|\s)|^\s*import\s+backend(\.|\s)", files("ai_engine", (".py",)), re.MULTILINE),
        allowlist={
            "ai_engine/client.py",                     # TODO(2026-08-01): drop lazy retry-emitter import
            "ai_engine/model_router.py",               # TODO(2026-08-01): inject supabase via constructor
            "ai_engine/agents/tools.py",               # TODO(2026-08-01): inject redis via tool registry
            "ai_engine/agents/sub_agents/base.py",     # TODO(2026-08-01): inject substep emitter
        },
    )

    # AP-17: queue ACK before success (heuristic: xack inside try without await of handler completion).
    # Too hard to grep reliably; skip and rely on review + tests for now.

    # Doc hedge audit: forbid vague *prose* language inside docs/architecture/*.md.
    # "TBD/TBA" intentionally NOT in this list — they are legitimate placeholder
    # markers in tables (e.g., ADR acceptance date pending). They're tracked
    # by the ADR README index, not by this hedge audit.
    arch_docs = list((ROOT / "docs" / "architecture").glob("*.md"))
    hedges = grep(
        r"\b(eventually|maybe|perhaps|probably|hopefully)\b",
        arch_docs,
    )
    rc |= report("Architecture docs: vague hedges", hedges)

    print("=" * 60)
    print("DONE" if rc == 0 else "FAILED — see above")
    return rc


if __name__ == "__main__":
    sys.exit(main())
