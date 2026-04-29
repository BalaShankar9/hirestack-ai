"""S12-F2: pin backend/VERSION as the single source of truth for app_version.

Closes audit risk R2: settings.app_version was hardcoded "1.0.0", which
defeated the Sentry release-bisect intent of S11-F2. After F2:
- backend/VERSION holds the canonical semver string.
- backend.app.core.config.Settings.app_version reads it at import time.
- A release script can bump the single file atomically.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = REPO_ROOT / "backend" / "VERSION"

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def test_version_file_exists() -> None:
    assert VERSION_FILE.is_file(), f"backend/VERSION missing at {VERSION_FILE}"


def test_version_file_is_semver() -> None:
    text = VERSION_FILE.read_text(encoding="utf-8").strip()
    assert _SEMVER_RE.match(text), (
        f"backend/VERSION must contain a single semver string (got {text!r})"
    )


def test_version_file_has_no_extra_lines() -> None:
    raw = VERSION_FILE.read_text(encoding="utf-8")
    # Allow exactly one trailing newline; reject embedded blank lines or
    # comments. The file must be machine-trivial to bump.
    stripped = raw.rstrip("\n")
    assert "\n" not in stripped, (
        "backend/VERSION must contain exactly one line (the semver string)"
    )


def test_settings_app_version_matches_version_file() -> None:
    # Re-import to bypass any cached lru_cache from earlier tests.
    from backend.app.core import config as config_module

    importlib.reload(config_module)
    settings = config_module.Settings()
    expected = VERSION_FILE.read_text(encoding="utf-8").strip()
    assert settings.app_version == expected, (
        f"Settings.app_version ({settings.app_version!r}) drifted from "
        f"backend/VERSION ({expected!r})"
    )


def test_config_module_uses_version_file_reader() -> None:
    """Regression guard: source must reference _read_version, not a literal."""
    import inspect

    from backend.app.core import config as config_module

    src = inspect.getsource(config_module)
    assert "_read_version" in src, (
        "config.py must define and use _read_version() — do not hardcode app_version"
    )
    # Negative guard: there must not be a literal `app_version: str = "1.0.0"`
    # left over after the F2 migration.
    assert 'app_version: str = "1.0.0"' not in src, (
        "config.py still hardcodes app_version='1.0.0' — must read backend/VERSION"
    )


@pytest.mark.parametrize(
    "fallback_input,expected",
    [
        ("", "0.0.0"),  # empty file → safe fallback
        ("1.2.3", "1.2.3"),
        ("  1.2.3  \n", "1.2.3"),  # whitespace tolerated
    ],
)
def test_read_version_handles_edge_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fallback_input: str,
    expected: str,
) -> None:
    from backend.app.core import config as config_module

    fake_backend_root = tmp_path / "backend"
    fake_backend_root.mkdir()
    (fake_backend_root / "VERSION").write_text(fallback_input, encoding="utf-8")
    monkeypatch.setattr(config_module, "_BACKEND_ROOT", fake_backend_root)
    assert config_module._read_version() == expected


def test_read_version_returns_fallback_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.core import config as config_module

    monkeypatch.setattr(config_module, "_BACKEND_ROOT", tmp_path)  # no VERSION here
    assert config_module._read_version() == "0.0.0"
