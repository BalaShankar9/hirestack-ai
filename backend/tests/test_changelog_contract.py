"""S12-F1: pin CHANGELOG.md contract.

If a future change deletes the changelog or breaks its
Keep-a-Changelog header, this test fails before the PR can land.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


def test_changelog_exists() -> None:
    assert CHANGELOG.is_file(), f"CHANGELOG.md missing at {CHANGELOG}"


def test_changelog_has_keep_a_changelog_header() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    # The header must reference Keep a Changelog so contributors know the
    # contract for adding entries.
    assert "Keep a Changelog" in text, "CHANGELOG must reference Keep a Changelog format"


def test_changelog_has_unreleased_section() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert re.search(r"^##\s+\[Unreleased\]", text, re.MULTILINE), (
        "CHANGELOG must have an [Unreleased] section so the next release has a staging area"
    )


def test_changelog_has_at_least_one_versioned_release() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    # Match `## [1.2.3]` or `## [1.2.3] — date`. At least one historic release
    # must be recorded so the file isn't a stub.
    versions = re.findall(r"^##\s+\[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    assert versions, "CHANGELOG must contain at least one semver release row"


@pytest.mark.parametrize(
    "required_section",
    ["S10", "S11", "S12"],
)
def test_changelog_seeded_with_recent_squads(required_section: str) -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert required_section in text, (
        f"CHANGELOG should mention {required_section} so contributors can trace shipped work"
    )
