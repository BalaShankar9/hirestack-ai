"""S12-F4: pin pytest-timeout in backend/requirements.txt.

Closes audit risk R5: backend/pytest.ini declared `timeout = 30` but
`pytest-timeout` was not in requirements, so pytest emitted
``PytestConfigWarning: Unknown config option: timeout`` and the
deadlock guard was silently disabled.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"
PYTEST_INI = REPO_ROOT / "backend" / "pytest.ini"


def test_pytest_timeout_is_declared_in_requirements() -> None:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    # Match `pytest-timeout` followed by an optional version specifier
    # at the start of a line (so we don't catch comments).
    assert re.search(
        r"^pytest-timeout(?:[<>=!~ ]|$)",
        text,
        re.MULTILINE,
    ), "backend/requirements.txt must declare pytest-timeout"


def test_pytest_ini_uses_timeout_directive() -> None:
    text = PYTEST_INI.read_text(encoding="utf-8")
    # The directive is what justifies the dependency; if someone removes
    # it, the dependency loses its purpose.
    assert re.search(r"^timeout\s*=\s*\d+", text, re.MULTILINE), (
        "backend/pytest.ini must keep the `timeout = N` directive"
    )


def test_pytest_timeout_plugin_is_importable() -> None:
    # If the dependency is in requirements but the local env hasn't
    # installed it, the deadlock guard is still inactive. This test
    # surfaces that drift in CI (where requirements were just installed).
    pytest_timeout = __import__("pytest_timeout")
    assert pytest_timeout is not None
