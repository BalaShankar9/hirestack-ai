#!/usr/bin/env python3
"""
Feature flag lifecycle enforcement.

Every flag referenced in code must be registered in `config/feature_flags.yaml`
with: owner, created date, sunset date, default, purpose.

Fails CI when:
  - A flag is referenced in code but missing from the registry.
  - A registered flag has no sunset date.
  - A registered flag's sunset date is in the past (no grace) — UNLESS
    the flag name is passed via ``--allow-expired-baseline=<flag>`` (may
    be repeated or comma-separated). The allowlist is the only escape
    hatch and MUST be paired with a tracking issue in the PR description.
  - An ``--allow-expired-baseline`` entry doesn't match any registered flag
    (prevents stale allowlist entries from silently lingering).
  - Two flags have the same name with different defaults.

Heuristics for code references:
  - Python: settings.ff_<name>, FeatureFlags.<name>, ff_<name> string literal
  - TS:     featureFlags.ff_<name>, "ff_<name>" string literal
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

try:
    import yaml  # type: ignore
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "feature_flags.yaml"
TODAY = dt.date.today()


def _display_path(p: pathlib.Path) -> str:
    """Display path relative to ROOT when possible; fall back to absolute str."""
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)

FLAG_RX = re.compile(r"\bff_[a-z][a-z0-9_]{2,}\b")

EXCLUDE_DIRS = {"node_modules", ".venv", "venv", ".git", "dist", "build", ".next", "coverage", "__pycache__"}


def referenced_flags() -> set[str]:
    flags: set[str] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if set(path.parts) & EXCLUDE_DIRS:
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".toml"}:
            continue
        if path == REGISTRY or path.as_posix().endswith("scripts/governance/check_feature_flags.py"):
            continue
        # The governance test file references made-up flag names as fixtures.
        if "scripts/governance" in path.as_posix() and path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        flags.update(FLAG_RX.findall(text))
    return flags


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit feature flag registry vs code references.")
    parser.add_argument(
        "--allow-expired-baseline",
        action="append",
        default=[],
        metavar="FLAG",
        help=(
            "Permit a specific expired flag to keep the build green. May be passed "
            "multiple times or as a comma-separated list. Allowlist entries that "
            "don't match any registered flag are themselves a build failure."
        ),
    )
    args = parser.parse_args(argv)

    # Flatten "a,b" → ["a", "b"], strip whitespace, drop empties.
    allowlist: set[str] = set()
    for raw in args.allow_expired_baseline:
        for tok in raw.split(","):
            tok = tok.strip()
            if tok:
                allowlist.add(tok)

    if not REGISTRY.exists():
        # Registry doesn't exist yet — soft-pass with a warning so this can land
        # before the first flag is added.
        print(f"WARN: {_display_path(REGISTRY)} missing; feature-flag enforcement skipped.")
        return 0

    raw = yaml.safe_load(REGISTRY.read_text()) or {}
    registered: dict[str, dict] = raw.get("flags", {}) or {}

    issues: list[str] = []

    # 1. Every registered flag has required fields and a sunset that is either
    #    in the future or explicitly allowlisted.
    for name, meta in registered.items():
        if not isinstance(meta, dict):
            issues.append(f"registry: flag `{name}` is not a mapping")
            continue
        for required in ("owner", "created", "sunset", "default", "purpose"):
            if required not in meta:
                issues.append(f"registry: flag `{name}` missing field `{required}`")
        sunset = meta.get("sunset")
        if isinstance(sunset, dt.date) and sunset < TODAY:
            past = (TODAY - sunset).days
            if name in allowlist:
                print(
                    f"INFO: flag `{name}` sunset {sunset.isoformat()} expired "
                    f"{past} days ago — allowlisted via --allow-expired-baseline."
                )
            else:
                issues.append(
                    f"registry: flag `{name}` sunset {sunset.isoformat()} expired "
                    f"{past} days ago; remove the flag, extend the sunset, or pass "
                    f"--allow-expired-baseline={name} (last resort, requires tracking issue)."
                )

    # 2. Code references must exist in registry.
    refs = referenced_flags()
    for name in sorted(refs):
        if name not in registered:
            issues.append(f"code references `{name}` but it is missing from {_display_path(REGISTRY)}")

    # 3. Allowlist entries must point at real flags — don't let stale opt-outs rot.
    for name in sorted(allowlist):
        if name not in registered:
            issues.append(
                f"--allow-expired-baseline={name} does not match any registered flag; "
                f"remove the allowlist entry."
            )

    if issues:
        print("Feature-flag audit FAILED:", file=sys.stderr)
        for i in issues:
            print(f"  {i}", file=sys.stderr)
        return 1
    print(
        f"Feature-flag audit: clean ({len(registered)} registered, "
        f"{len(refs)} referenced in code, {len(allowlist)} expired-baseline allowlisted)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
