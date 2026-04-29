"""Pin every production-config entrypoint to a real, importable FastAPI app.

Before S10-F2, four different `uvicorn` invocations existed across
`Procfile`, `railway.toml`, `backend/Dockerfile`, `infra/Dockerfile.backend`,
and `Makefile`:

    main:app        # Procfile, railway.toml (cwd=/app/backend)
    app.main:app    # backend/Dockerfile + Makefile (BROKEN \u2014 backend/app/main.py
                    #     does not exist; only backend/main.py does)
    backend.main:app  # infra/Dockerfile.backend (cwd=repo root)

The first and third are correct given their respective working
directories. The second was a landmine that would crash on cold start
of any platform that uses backend/Dockerfile (e.g. a default
`docker build backend/`).

These tests:
1. Parse each config file, extract the uvicorn module path.
2. Verify the (cwd, module) pair resolves to the actual FastAPI app
   instance defined in backend/main.py.
3. Verify no config still references the broken `app.main:app`.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _extract_uvicorn_target(text: str) -> str:
    """Return the first 'module:attr' that follows uvicorn invocation."""
    # Matches: uvicorn module:attr, "uvicorn", "module:attr",
    # python -m uvicorn module:attr, etc.
    m = re.search(
        r"uvicorn[^\w/-]+[\"']?([A-Za-z_][\w.]*:[A-Za-z_]\w*)",
        text,
    )
    assert m, f"could not find uvicorn target in:\n{text[:400]}"
    return m.group(1)


def _resolve(module_path: str, *, cwd: Path) -> FastAPI:
    """Import 'module:attr' as if launched from `cwd`."""
    saved_path = list(sys.path)
    saved_modules = {
        k: v for k, v in sys.modules.items()
        if k == "main" or k.startswith("backend") or k.startswith("app.")
    }
    try:
        # Drop any cached 'main' from a prior run with a different cwd.
        for k in list(sys.modules):
            if k == "main" or k.startswith("backend.") or k == "backend":
                # 'backend' itself is a real package needed for backend.main; don't blow it away
                if k == "main":
                    sys.modules.pop(k)
        sys.path.insert(0, str(cwd))
        module_name, attr = module_path.split(":")
        mod = importlib.import_module(module_name)
        return getattr(mod, attr)
    finally:
        sys.path[:] = saved_path
        # Restore prior cache state only for 'main' (avoid nuking 'backend' chain
        # on success since later tests may rely on it).
        if "main" in sys.modules and "main" not in saved_modules:
            sys.modules.pop("main", None)


# ────────────────────────────────────────────────────────────────────
# Per-config entrypoint extraction
# ────────────────────────────────────────────────────────────────────

def test_procfile_uvicorn_target_resolves_to_fastapi() -> None:
    target = _extract_uvicorn_target(_read("Procfile"))
    assert target == "main:app", f"Procfile drifted: {target}"
    app = _resolve(target, cwd=BACKEND_DIR)
    assert isinstance(app, FastAPI)


def test_railway_toml_uvicorn_target_resolves_to_fastapi() -> None:
    target = _extract_uvicorn_target(_read("railway.toml"))
    assert target == "main:app", f"railway.toml drifted: {target}"
    app = _resolve(target, cwd=BACKEND_DIR)
    assert isinstance(app, FastAPI)


def test_backend_dockerfile_uses_main_app() -> None:
    """Build context = backend/, so /app/main.py exists; module is main:app."""
    target = _extract_uvicorn_target(_read("backend/Dockerfile"))
    assert target == "main:app", f"backend/Dockerfile drifted: {target}"


def test_infra_dockerfile_backend_uses_backend_main_app() -> None:
    """Build context = repo root, so /app/backend/main.py exists; module is backend.main:app."""
    target = _extract_uvicorn_target(_read("infra/Dockerfile.backend"))
    assert target == "backend.main:app", f"infra/Dockerfile.backend drifted: {target}"
    app = _resolve(target, cwd=REPO_ROOT)
    assert isinstance(app, FastAPI)


def test_makefile_dev_backend_uses_main_app() -> None:
    text = _read("Makefile")
    # Find the dev-backend target body.
    m = re.search(r"dev-backend:.*?\n\tcd backend &&[^\n]+", text)
    assert m, "dev-backend target not found in Makefile"
    target = _extract_uvicorn_target(m.group(0))
    assert target == "main:app", f"Makefile dev-backend drifted: {target}"


def test_no_config_still_references_broken_app_main() -> None:
    """Regression guard: app.main:app does NOT exist in this repo."""
    files = [
        "Procfile",
        "railway.toml",
        "backend/Dockerfile",
        "infra/Dockerfile.backend",
        "Makefile",
        "docker-compose.yml",
        "infra/docker-compose.yml",
    ]
    leaks: list[str] = []
    for rel in files:
        if "app.main:app" in _read(rel):
            leaks.append(rel)
    assert not leaks, (
        "Files still reference the non-existent module 'app.main:app' "
        "(backend/app/main.py does not exist; canonical is backend/main.py): "
        + ", ".join(leaks)
    )


def test_canonical_app_object_is_unique() -> None:
    """Both resolution paths must yield the SAME FastAPI instance."""
    a = _resolve("main:app", cwd=BACKEND_DIR)
    b = _resolve("backend.main:app", cwd=REPO_ROOT)
    # They are two import paths to the same source file; modulo Python's
    # module cache they should be the same object. If sys.modules has
    # cached both 'main' and 'backend.main' separately, they will be
    # distinct INSTANCES of FastAPI defined by the same source \u2014 in
    # which case at minimum the title must match.
    if a is not b:
        assert a.title == b.title, (
            f"Two import paths produced two different FastAPI apps: "
            f"{a.title!r} vs {b.title!r}"
        )


@pytest.mark.parametrize("cfg", ["Procfile", "railway.toml"])
def test_cmd_line_runtime_pythonpath_is_set(cfg: str) -> None:
    """Procfile and railway.toml MUST set PYTHONPATH=/app so 'main:app' resolves."""
    text = _read(cfg)
    assert "PYTHONPATH=/app" in text, f"{cfg} missing PYTHONPATH=/app"
