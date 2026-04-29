"""S12-R7 — every `uses:` in workflows must pin to a 40-char commit SHA.

Tag refs (`@v4`) silently float; a compromised tag would land on prod CI.
This test forbids any `uses: org/repo@<tag>` line in `.github/workflows/`,
allowing only `uses: org/repo@<40-hex-sha>` (with optional `# vX` comment).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_USES_RE = re.compile(r"^\s*-\s+uses:\s+(\S+)\s*(?:#.*)?$", re.MULTILINE)
_SHA_PIN_RE = re.compile(r"^[A-Za-z0-9_./-]+@[0-9a-f]{40}$")


def _workflow_files() -> list[Path]:
    return sorted(_WORKFLOWS_DIR.glob("*.yml")) + sorted(_WORKFLOWS_DIR.glob("*.yaml"))


def test_workflows_dir_exists() -> None:
    assert _WORKFLOWS_DIR.is_dir(), f"{_WORKFLOWS_DIR} missing"


def test_workflow_files_present() -> None:
    files = _workflow_files()
    assert files, "no workflow files found"


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda p: p.name)
def test_every_uses_is_sha_pinned(workflow: Path) -> None:
    src = workflow.read_text(encoding="utf-8")
    refs = _USES_RE.findall(src)
    assert refs, f"{workflow.name}: no `uses:` lines (sanity check)"
    bad = [r for r in refs if not _SHA_PIN_RE.match(r)]
    assert not bad, (
        f"{workflow.name}: unpinned action references (must be @<40-hex-sha>): {bad}"
    )
