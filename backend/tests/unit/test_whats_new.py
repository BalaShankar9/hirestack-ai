"""Unit tests for `whats_new` pure-fn core (A4)."""
from __future__ import annotations

from textwrap import dedent

import pytest

from app.services.whats_new import (
    KNOWN_SECTIONS,
    MAX_BULLETS_PER_SECTION,
    MAX_RELEASES_IN_DIGEST,
    SECURITY_SECTION,
    ReleaseEntry,
    ReleaseSection,
    SemVer,
    compose_whats_new,
    parse_changelog,
    parse_semver,
    whats_new_from_markdown,
)


# ───────────────────────────── parse_semver ─────────────────────────────


def test_parse_semver_basic() -> None:
    v = parse_semver("1.2.3")
    assert v == SemVer(1, 2, 3, "")


def test_parse_semver_prerelease() -> None:
    v = parse_semver("2.0.0-rc.1")
    assert v == SemVer(2, 0, 0, "rc.1")


def test_parse_semver_rejects_garbage() -> None:
    assert parse_semver("not-a-version") is None
    assert parse_semver("1.2") is None
    assert parse_semver("v1.0.0") is None  # callers strip the v themselves


def test_semver_ordering_stable_beats_prerelease() -> None:
    stable = SemVer(1, 0, 0, "")
    pre = SemVer(1, 0, 0, "rc.1")
    assert stable.as_tuple() > pre.as_tuple()


def test_semver_ordering_patch_beats_minor_beats_major() -> None:
    assert SemVer(2, 0, 0, "").as_tuple() > SemVer(1, 99, 99, "").as_tuple()
    assert SemVer(1, 1, 0, "").as_tuple() > SemVer(1, 0, 99, "").as_tuple()
    assert SemVer(1, 0, 1, "").as_tuple() > SemVer(1, 0, 0, "").as_tuple()


def test_semver_str_roundtrip() -> None:
    assert str(SemVer(1, 2, 3, "")) == "1.2.3"
    assert str(SemVer(1, 2, 3, "rc.1")) == "1.2.3-rc.1"


# ───────────────────────────── parse_changelog ─────────────────────────


_SAMPLE = dedent("""\
    # Changelog

    ## [Unreleased]

    ### Added
    - placeholder for next release

    ## [1.0.1] — 2026-04-29

    ### Added
    - new feature A
    - new feature B

    ### Changed
    - tweaked behaviour C

    ### Security
    - patched CVE-foo

    ## [1.0.0] — 2026-04-20

    Initial baseline.

    ### Added
    - everything
""")


def test_parse_skips_unreleased_block() -> None:
    entries = parse_changelog(_SAMPLE)
    versions = [str(e.version) for e in entries]
    assert versions == ["1.0.1", "1.0.0"]
    # Unreleased placeholder must NOT leak as an entry.
    for e in entries:
        for s in e.sections:
            assert "placeholder" not in " ".join(s.bullets).lower()


def test_parse_extracts_dates() -> None:
    entries = parse_changelog(_SAMPLE)
    assert entries[0].date == "2026-04-29"
    assert entries[1].date == "2026-04-20"


def test_parse_groups_sections_in_canonical_order() -> None:
    entry = parse_changelog(_SAMPLE)[0]
    names = [s.name for s in entry.sections]
    # Added before Changed before Security per KNOWN_SECTIONS order.
    assert names == ["Added", "Changed", "Security"]


def test_parse_extracts_bullet_bodies_unwrapped() -> None:
    entry = parse_changelog(_SAMPLE)[0]
    added = next(s for s in entry.sections if s.name == "Added")
    assert added.bullets == ("new feature A", "new feature B")
    assert added.truncated is False


def test_parse_handles_release_with_no_date() -> None:
    text = dedent("""\
        ## [0.9.0]

        ### Added
        - undated release
    """)
    entries = parse_changelog(text)
    assert len(entries) == 1
    assert entries[0].date == ""
    assert entries[0].version == SemVer(0, 9, 0, "")


def test_parse_handles_v_prefix_in_header() -> None:
    text = dedent("""\
        ## [v1.2.3] — 2026-01-01

        ### Added
        - one
    """)
    entries = parse_changelog(text)
    assert entries[0].version == SemVer(1, 2, 3, "")


def test_parse_buckets_unknown_sections_under_other() -> None:
    text = dedent("""\
        ## [1.0.0] — 2026-01-01

        ### Migrations
        - ran X
        - ran Y
    """)
    entry = parse_changelog(text)[0]
    sec = entry.sections[0]
    assert sec.name == "Other"
    assert sec.bullets == ("ran X", "ran Y")


def test_parse_truncates_long_section_and_flags() -> None:
    bullets = "\n".join(f"- bullet {i}" for i in range(MAX_BULLETS_PER_SECTION + 3))
    text = "## [1.0.0] — 2026-01-01\n\n### Added\n" + bullets + "\n"
    entry = parse_changelog(text)[0]
    added = entry.sections[0]
    assert len(added.bullets) == MAX_BULLETS_PER_SECTION
    assert added.truncated is True


def test_parse_skips_blank_bullets() -> None:
    text = dedent("""\
        ## [1.0.0] — 2026-01-01

        ### Added
        -
        - real bullet
    """)
    entry = parse_changelog(text)[0]
    assert entry.sections[0].bullets == ("real bullet",)


def test_parse_ignores_garbage_version_headers() -> None:
    text = dedent("""\
        ## [not-a-version] — 2026-01-01

        ### Added
        - leaks?

        ## [1.0.0] — 2026-01-02

        ### Added
        - keep me
    """)
    entries = parse_changelog(text)
    assert len(entries) == 1
    assert str(entries[0].version) == "1.0.0"


def test_parse_empty_input() -> None:
    assert parse_changelog("") == ()
    assert parse_changelog("# Just a header\n") == ()


def test_parse_preserves_em_dash_and_hyphen_dates() -> None:
    text = dedent("""\
        ## [1.0.0] - 2026-01-01

        ### Added
        - hyphen variant
    """)
    entry = parse_changelog(text)[0]
    assert entry.date == "2026-01-01"


# ───────────────────────────── compose_whats_new ───────────────────────


def _entry(ver: str, *, security: bool = False, n_added: int = 1) -> ReleaseEntry:
    sections: list[ReleaseSection] = [
        ReleaseSection("Added", tuple(f"a{i}" for i in range(n_added))),
    ]
    if security:
        sections.append(ReleaseSection("Security", ("patched x",)))
    return ReleaseEntry(
        version=parse_semver(ver),  # type: ignore[arg-type]
        date="2026-01-01",
        sections=tuple(sections),
    )


def test_compose_first_time_user_sees_everything() -> None:
    entries = (_entry("1.0.1"), _entry("1.0.0"))
    digest = compose_whats_new(entries, since_version=None)
    assert len(digest.entries) == 2
    assert digest.since_version is None


def test_compose_filters_to_newer_only() -> None:
    entries = (_entry("1.0.1"), _entry("1.0.0"))
    digest = compose_whats_new(entries, since_version=SemVer(1, 0, 0, ""))
    assert [str(e.version) for e in digest.entries] == ["1.0.1"]


def test_compose_returns_empty_when_user_is_current() -> None:
    entries = (_entry("1.0.1"), _entry("1.0.0"))
    digest = compose_whats_new(entries, since_version=SemVer(1, 0, 1, ""))
    assert digest.entries == ()
    assert digest.total_changes == 0
    assert digest.has_security is False


def test_compose_total_changes_counts_all_bullets() -> None:
    entries = (_entry("1.0.1", n_added=3), _entry("1.0.0", n_added=2))
    digest = compose_whats_new(entries, since_version=None)
    assert digest.total_changes == 5


def test_compose_has_security_when_any_release_has_security() -> None:
    entries = (_entry("1.0.1"), _entry("1.0.0", security=True))
    digest = compose_whats_new(entries, since_version=None)
    assert digest.has_security is True


def test_compose_caps_release_count_and_flags_truncation() -> None:
    too_many = tuple(
        _entry(f"1.0.{i}") for i in range(MAX_RELEASES_IN_DIGEST + 3)
    )
    digest = compose_whats_new(too_many, since_version=None)
    assert len(digest.entries) == MAX_RELEASES_IN_DIGEST
    assert digest.truncated_releases is True
    # Newest kept, oldest dropped.
    assert str(digest.entries[0].version) == f"1.0.{MAX_RELEASES_IN_DIGEST + 2}"


def test_compose_orders_newest_first() -> None:
    entries = (_entry("1.0.0"), _entry("2.0.0"), _entry("1.5.0"))
    digest = compose_whats_new(entries, since_version=None)
    assert [str(e.version) for e in digest.entries] == [
        "2.0.0", "1.5.0", "1.0.0",
    ]


def test_compose_accepts_list_input() -> None:
    # Defensive: callers may pass a list rather than a tuple.
    digest = compose_whats_new([_entry("1.0.0")], since_version=None)
    assert len(digest.entries) == 1


def test_compose_prerelease_treated_as_older_than_stable() -> None:
    # A user on 1.0.0-rc.1 should see 1.0.0 stable in their digest.
    entries = (_entry("1.0.0"),)
    digest = compose_whats_new(entries, since_version=SemVer(1, 0, 0, "rc.1"))
    assert [str(e.version) for e in digest.entries] == ["1.0.0"]


# ───────────────────────────── whats_new_from_markdown ─────────────────


def test_end_to_end_with_real_changelog_format() -> None:
    digest = whats_new_from_markdown(_SAMPLE, since_version_raw="1.0.0")
    assert [str(e.version) for e in digest.entries] == ["1.0.1"]
    assert digest.has_security is True
    # 2 Added + 1 Changed + 1 Security = 4 bullets
    assert digest.total_changes == 4


def test_end_to_end_handles_v_prefix_in_since() -> None:
    digest = whats_new_from_markdown(_SAMPLE, since_version_raw="v1.0.0")
    assert [str(e.version) for e in digest.entries] == ["1.0.1"]


def test_end_to_end_treats_unparseable_since_as_first_time() -> None:
    digest = whats_new_from_markdown(_SAMPLE, since_version_raw="garbage")
    assert digest.since_version is None
    assert len(digest.entries) == 2  # both releases shown


def test_end_to_end_none_since_returns_all_releases() -> None:
    digest = whats_new_from_markdown(_SAMPLE, since_version_raw=None)
    assert len(digest.entries) == 2


# ───────────────────────────── module surface ──────────────────────────


def test_known_sections_includes_security() -> None:
    assert SECURITY_SECTION in KNOWN_SECTIONS


def test_constants_are_positive() -> None:
    assert MAX_BULLETS_PER_SECTION > 0
    assert MAX_RELEASES_IN_DIGEST > 0
