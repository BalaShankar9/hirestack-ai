"""A4 — `whats_new` pure-fn core.

Parses the project `CHANGELOG.md` (Keep a Changelog 1.1.0 format) into
structured release entries, then produces a per-user "What's New since you
last logged in" digest.

This module is **pure**: no I/O, no DB, no clock. The caller passes the
raw changelog markdown and the user's last-seen version (or `None` for a
brand-new user). Composition with FastAPI / DB lives in a follow-up slice.

Plan reference: docs/MASTER_INTEGRATION_PLAN.md Week 2 Fri —
"A4 What's New panel + /api/changelog | Reads from existing release notes".

Voice / scope guards
--------------------
- Highlights the **Security** section as a separate priority tag (so the
  UI can show a red dot) — this is the only category with elevated weight
  in the current ruleset; everything else is rendered chronologically.
- Caps each release section to `MAX_BULLETS_PER_SECTION` so the panel
  cannot explode for a giant release. Truncation is recorded so the UI can
  render a "see full changelog" link.
- Skips the `[Unreleased]` block — only published versions count toward
  the digest. (Unreleased may contain placeholder bullets that have not
  shipped yet.)
- Version comparison is the strict Keep-a-Changelog subset:
  `MAJOR.MINOR.PATCH` integer triple. Pre-release tags (`-rc.1`) are
  parsed but compared as a 4th element where empty > any tag.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
import re

# ────────────────────────────── Constants ──────────────────────────────

MAX_BULLETS_PER_SECTION: Final[int] = 6
MAX_RELEASES_IN_DIGEST: Final[int] = 5
SECURITY_SECTION: Final[str] = "Security"
UNRELEASED_TOKEN: Final[str] = "Unreleased"

# Section names recognised by Keep a Changelog 1.1.0; bullets under any
# other ### subheader are merged under "Other".
KNOWN_SECTIONS: Final[tuple[str, ...]] = (
    "Added", "Changed", "Deprecated", "Removed", "Fixed", "Security",
)

# ────────────────────────────── Models ─────────────────────────────────


@dataclass(frozen=True)
class SemVer:
    """Strict MAJOR.MINOR.PATCH (with optional pre-release tag)."""
    major: int
    minor: int
    patch: int
    prerelease: str = ""  # "" = stable; non-empty sorts BEFORE stable

    def as_tuple(self) -> tuple[int, int, int, int, str]:
        # prerelease "" must sort AFTER any tag → use sentinel ordering.
        # 1 = stable (no pre), 0 = pre-release.
        stability = 1 if self.prerelease == "" else 0
        return (self.major, self.minor, self.patch, stability, self.prerelease)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base


@dataclass(frozen=True)
class ReleaseSection:
    """One category (Added / Changed / ...) inside a release."""
    name: str
    bullets: tuple[str, ...]
    truncated: bool = False  # True iff bullets were capped


@dataclass(frozen=True)
class ReleaseEntry:
    """A single published release block from CHANGELOG.md."""
    version: SemVer
    date: str  # raw "YYYY-MM-DD" string, or "" if missing
    sections: tuple[ReleaseSection, ...]

    @property
    def has_security(self) -> bool:
        return any(s.name == SECURITY_SECTION and s.bullets for s in self.sections)


@dataclass(frozen=True)
class WhatsNewDigest:
    """Per-user slice of the changelog newer than `since_version`."""
    entries: tuple[ReleaseEntry, ...]
    total_changes: int
    since_version: SemVer | None  # None = first-time user, show top N
    has_security: bool
    truncated_releases: bool  # True iff older releases were dropped


# ────────────────────────────── Parsing ────────────────────────────────

_RELEASE_HEADER = re.compile(
    r"^##\s+\[(?P<ver>[^\]]+)\](?:\s*[—\-]\s*(?P<date>\d{4}-\d{2}-\d{2}))?\s*$"
)
_SECTION_HEADER = re.compile(r"^###\s+(?P<name>.+?)\s*$")
_BULLET = re.compile(r"^[-*]\s+(?P<body>.+?)\s*$")
_SEMVER = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<pre>[A-Za-z0-9.\-]+))?$"
)


def parse_semver(raw: str) -> SemVer | None:
    """Return SemVer or None for unparseable / `Unreleased` tokens."""
    m = _SEMVER.match(raw.strip())
    if not m:
        return None
    return SemVer(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        prerelease=m.group("pre") or "",
    )


def parse_changelog(markdown_text: str) -> tuple[ReleaseEntry, ...]:
    """Parse a Keep-a-Changelog markdown body into release entries.

    Skips `[Unreleased]`. Unknown / malformed version headers are ignored.
    Bullets under unknown ### sections are merged into a synthetic "Other"
    section so they still appear in the digest.
    Returns entries in source order (i.e. newest first as is conventional
    in Keep a Changelog).
    """
    entries: list[ReleaseEntry] = []
    cur_ver: SemVer | None = None
    cur_date: str = ""
    cur_sections: dict[str, list[str]] = {}
    cur_section_name: str | None = None

    def _flush() -> None:
        if cur_ver is None:
            return
        sections: list[ReleaseSection] = []
        for name in (*KNOWN_SECTIONS, "Other"):
            bullets = cur_sections.get(name)
            if not bullets:
                continue
            truncated = len(bullets) > MAX_BULLETS_PER_SECTION
            kept = bullets[:MAX_BULLETS_PER_SECTION]
            sections.append(ReleaseSection(
                name=name, bullets=tuple(kept), truncated=truncated,
            ))
        entries.append(ReleaseEntry(
            version=cur_ver, date=cur_date, sections=tuple(sections),
        ))

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()

        m_rel = _RELEASE_HEADER.match(line)
        if m_rel:
            _flush()
            cur_sections = {}
            cur_section_name = None
            cur_date = m_rel.group("date") or ""
            ver_token = m_rel.group("ver").strip()
            if ver_token == UNRELEASED_TOKEN:
                cur_ver = None
                continue
            # Tolerate leading "v"
            cur_ver = parse_semver(ver_token.lstrip("vV"))
            continue

        if cur_ver is None:
            # Inside [Unreleased] or pre-first-release content; skip.
            continue

        m_sec = _SECTION_HEADER.match(line)
        if m_sec:
            name = m_sec.group("name").strip()
            cur_section_name = name if name in KNOWN_SECTIONS else "Other"
            cur_sections.setdefault(cur_section_name, [])
            continue

        m_bul = _BULLET.match(line)
        if m_bul and cur_section_name is not None:
            body = m_bul.group("body").strip()
            if body:
                cur_sections[cur_section_name].append(body)

    _flush()
    return tuple(entries)


# ─────────────────────────────── Digest ────────────────────────────────


def _is_newer(entry: ReleaseEntry, since: SemVer | None) -> bool:
    if since is None:
        return True
    return entry.version.as_tuple() > since.as_tuple()


def compose_whats_new(
    entries: tuple[ReleaseEntry, ...] | list[ReleaseEntry],
    since_version: SemVer | None,
) -> WhatsNewDigest:
    """Slice `entries` to those newer than `since_version`.

    Newest-first ordering is preserved. If the resulting set is larger than
    `MAX_RELEASES_IN_DIGEST` the **oldest** are dropped and
    `truncated_releases=True` is flagged.
    """
    eligible = [e for e in entries if _is_newer(e, since_version)]
    eligible.sort(key=lambda e: e.version.as_tuple(), reverse=True)

    truncated = len(eligible) > MAX_RELEASES_IN_DIGEST
    kept = tuple(eligible[:MAX_RELEASES_IN_DIGEST])

    total_changes = sum(
        len(sec.bullets) for entry in kept for sec in entry.sections
    )
    has_security = any(entry.has_security for entry in kept)

    return WhatsNewDigest(
        entries=kept,
        total_changes=total_changes,
        since_version=since_version,
        has_security=has_security,
        truncated_releases=truncated,
    )


def whats_new_from_markdown(
    markdown_text: str,
    since_version_raw: str | None,
) -> WhatsNewDigest:
    """Convenience: parse + compose in one call.

    `since_version_raw=None` → first-time user (top N most recent).
    Unparseable `since_version_raw` is treated as None (defensive).
    """
    entries = parse_changelog(markdown_text)
    since = parse_semver(since_version_raw.lstrip("vV")) if since_version_raw else None
    return compose_whats_new(entries, since)


__all__ = [
    "MAX_BULLETS_PER_SECTION",
    "MAX_RELEASES_IN_DIGEST",
    "SECURITY_SECTION",
    "KNOWN_SECTIONS",
    "SemVer",
    "ReleaseSection",
    "ReleaseEntry",
    "WhatsNewDigest",
    "parse_semver",
    "parse_changelog",
    "compose_whats_new",
    "whats_new_from_markdown",
]
