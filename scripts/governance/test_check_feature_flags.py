"""m11-pr42: feature-flag sunset enforcement."""
from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import sys
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "governance" / "check_feature_flags.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_feature_flags", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_feature_flags"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cff(monkeypatch, tmp_path):
    """Load the script with REGISTRY pointed at a tmp_path file and TODAY pinned."""
    mod = _load_module()
    registry = tmp_path / "feature_flags.yaml"
    monkeypatch.setattr(mod, "REGISTRY", registry)
    monkeypatch.setattr(mod, "TODAY", dt.date(2026, 5, 8))
    # Stop the script from scanning the real repo.
    monkeypatch.setattr(mod, "referenced_flags", lambda: set())
    return mod, registry


def _write(registry: pathlib.Path, body: str) -> None:
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(textwrap.dedent(body))


def test_clean_registry_passes(cff, capsys):
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_alpha:
            owner: bala
            created: 2026-04-01
            sunset: 2026-12-01
            default: false
            purpose: test
        """,
    )
    assert mod.main([]) == 0
    out = capsys.readouterr().out
    assert "clean" in out


def test_expired_flag_fails_without_allowlist(cff, capsys):
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_old:
            owner: bala
            created: 2026-01-01
            sunset: 2026-04-01
            default: false
            purpose: test
        """,
    )
    rc = mod.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ff_old" in err and "expired" in err
    assert "--allow-expired-baseline=ff_old" in err


def test_expired_flag_passes_with_allowlist(cff, capsys):
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_old:
            owner: bala
            created: 2026-01-01
            sunset: 2026-04-01
            default: false
            purpose: test
        """,
    )
    rc = mod.main(["--allow-expired-baseline=ff_old"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "allowlisted" in out


def test_expired_flag_one_day_past_fails(cff):
    """No grace: one day past sunset fails (was 14-day grace pre-pr42)."""
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_yesterday:
            owner: bala
            created: 2026-01-01
            sunset: 2026-05-07
            default: false
            purpose: test
        """,
    )
    assert mod.main([]) == 1


def test_sunset_today_passes(cff):
    """Sunset == TODAY is still in-window (only strictly past triggers)."""
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_today:
            owner: bala
            created: 2026-01-01
            sunset: 2026-05-08
            default: false
            purpose: test
        """,
    )
    assert mod.main([]) == 0


def test_allowlist_for_unknown_flag_fails(cff, capsys):
    """Stale allowlist entries must not silently linger."""
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_alpha:
            owner: bala
            created: 2026-04-01
            sunset: 2026-12-01
            default: false
            purpose: test
        """,
    )
    rc = mod.main(["--allow-expired-baseline=ff_does_not_exist"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ff_does_not_exist" in err
    assert "does not match any registered flag" in err


def test_allowlist_accepts_comma_separated(cff):
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_a:
            owner: bala
            created: 2026-01-01
            sunset: 2026-04-01
            default: false
            purpose: t
          ff_b:
            owner: bala
            created: 2026-01-01
            sunset: 2026-04-01
            default: false
            purpose: t
        """,
    )
    rc = mod.main(["--allow-expired-baseline=ff_a,ff_b"])
    assert rc == 0


def test_allowlist_accepts_repeated_flag(cff):
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_a:
            owner: bala
            created: 2026-01-01
            sunset: 2026-04-01
            default: false
            purpose: t
          ff_b:
            owner: bala
            created: 2026-01-01
            sunset: 2026-04-01
            default: false
            purpose: t
        """,
    )
    rc = mod.main(["--allow-expired-baseline=ff_a", "--allow-expired-baseline=ff_b"])
    assert rc == 0


def test_missing_required_field_fails(cff, capsys):
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_broken:
            owner: bala
            sunset: 2026-12-01
            default: false
            purpose: t
        """,
    )
    rc = mod.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "missing field `created`" in err


def test_unregistered_code_reference_fails(cff, monkeypatch, capsys):
    mod, reg = cff
    _write(
        reg,
        """
        flags:
          ff_alpha:
            owner: bala
            created: 2026-04-01
            sunset: 2026-12-01
            default: false
            purpose: t
        """,
    )
    monkeypatch.setattr(mod, "referenced_flags", lambda: {"ff_alpha", "ff_ghost"})
    rc = mod.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ff_ghost" in err and "missing from" in err


def test_missing_registry_soft_passes(cff, capsys):
    mod, reg = cff
    # registry path doesn't exist
    assert not reg.exists()
    rc = mod.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "missing" in out
