"""Repository-wide secret scanner.

Catches JWT-shaped tokens, Supabase keys, AWS access keys, GitHub
PATs, and OpenAI keys checked into source. Exists because the prior
CI scanner missed Supabase JWTs (`eyJ...`) and a service-role key
shipped to git history.

Run as part of the backend pytest suite \u2014 every PR sees the gate.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# JWT-shape: header.payload.signature, base64url segments.
# Anchored to a long enough payload to avoid hitting random base64 noise.
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")
AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
GH_PAT_RE = re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")
OPENAI_RE = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")

# Files allowed to mention example-shaped credentials. The example files
# stop at "eyJ\u2026" so they will not match JWT_RE; this allow-list is
# defense in depth for placeholders like AKIAIOSFODNN7EXAMPLE.
ALLOW_BASENAMES = {".env.example"}
ALLOW_PATH_FRAGMENTS = (
    "/tests/test_no_hardcoded_secrets.py",  # this file
    "/docs/audits/S10-infra-deploy.md",     # audit doc cites the leaked refs by name only
    # Supabase ANON keys are public-by-design for client SDKs (RLS gates writes)
    # so embedding the anon key in the Android BuildConfig is acceptable.
    # Tracked for follow-up in mobile-release squad: move to local.properties /
    # Gradle property so rotation does not require an APK rebuild commit.
    "/mobile/android/app/build.gradle.kts",
)


def _tracked_files() -> list[Path]:
    out = subprocess.check_output(
        ["git", "ls-files"], cwd=REPO_ROOT, text=True
    )
    paths: list[Path] = []
    for rel in out.splitlines():
        if not rel:
            continue
        p = REPO_ROOT / rel
        if not p.is_file():
            continue
        # Skip binary-ish extensions.
        if p.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
            ".woff", ".woff2", ".ttf", ".otf", ".eot",
            ".zip", ".gz", ".tar", ".jar", ".keystore", ".jks",
            ".lock",  # package-lock.json is huge & has no JWTs
        }:
            continue
        if p.name == "package-lock.json":
            continue
        paths.append(p)
    return paths


def _is_allowed(path: Path) -> bool:
    if path.name in ALLOW_BASENAMES:
        return True
    posix = path.as_posix()
    return any(frag in posix for frag in ALLOW_PATH_FRAGMENTS)


@pytest.mark.parametrize(
    "pattern,label",
    [
        (JWT_RE, "JWT"),
        (AWS_KEY_RE, "AWS access key"),
        (GH_PAT_RE, "GitHub token"),
        (OPENAI_RE, "OpenAI key"),
    ],
)
def test_no_hardcoded_secrets(pattern: re.Pattern[str], label: str) -> None:
    hits: list[str] = []
    for p in _tracked_files():
        if _is_allowed(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            hits.append(f"{p.relative_to(REPO_ROOT)}:{line_no}  [{label}]")
    assert not hits, (
        f"Hardcoded {label} found in tracked source files:\n  "
        + "\n  ".join(hits)
        + "\n\nMove credentials to environment variables. If this is a"
        " documentation example, add the file to ALLOW_PATH_FRAGMENTS."
    )


def test_smoke_test_script_does_not_inline_credentials() -> None:
    """Defense in depth: the file that previously held the leak."""
    smoke = (REPO_ROOT / "scripts" / "smoke_test.py").read_text()
    assert "dkfmcnfhvbqwsgpkgoag" not in smoke, "supabase project ref must not be hardcoded"
    assert "E2eTest1234" not in smoke, "test password must not be hardcoded"
    assert "os.environ[\"SUPABASE_ANON_KEY\"]" in smoke
    assert "os.environ[\"SUPABASE_SERVICE_ROLE_KEY\"]" in smoke


def test_smoke_test_script_fails_closed_without_env(tmp_path, monkeypatch) -> None:
    """Running smoke_test.py with no env vars must exit 2 and name each."""
    import sys as _sys
    for k in (
        "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
        "SMOKE_TEST_EMAIL", "SMOKE_TEST_PASSWORD",
    ):
        monkeypatch.delenv(k, raising=False)
    proc = subprocess.run(
        [_sys.executable, str(REPO_ROOT / "scripts" / "smoke_test.py")],
        capture_output=True, text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 2, f"expected exit 2, got {proc.returncode}: {proc.stderr}"
    for k in (
        "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
        "SMOKE_TEST_EMAIL", "SMOKE_TEST_PASSWORD",
    ):
        assert k in proc.stderr, f"missing {k} not surfaced in stderr"
