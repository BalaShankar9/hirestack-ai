"""Pin docker-compose canonicalisation contract (S10-F3).

Before this squad two divergent compose files existed:

  docker-compose.yml          - root, no worker, no Redis password,
                                immutable images, env_file based
  infra/docker-compose.yml    - production-shaped: worker, Redis
                                requirepass, env-driven config, BUT
                                shadowed images with bind mounts

ADR-0012 designates infra/docker-compose.yml as the SINGLE canonical
file. The root file is removed. Dev bind mounts are stripped from
the canonical file so it represents true production parity; local
hot-reload uses `make dev-backend` / `make dev-frontend` directly.

Tests pin:
1. Only one compose file remains (root absent).
2. The canonical file has no host bind mounts on production
   services (only named volumes are allowed).
3. Redis still requires a password.
4. The Makefile docker-* targets reference the canonical file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "infra" / "docker-compose.yml"


def _yaml() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(CANONICAL.read_text())


def test_root_compose_file_is_absent() -> None:
    """Eliminating drift: only infra/docker-compose.yml exists."""
    root_compose = REPO_ROOT / "docker-compose.yml"
    assert not root_compose.exists(), (
        "Root docker-compose.yml has reappeared. ADR-0012 designates "
        "infra/docker-compose.yml as the single canonical file."
    )


def test_canonical_compose_file_exists() -> None:
    assert CANONICAL.exists(), "infra/docker-compose.yml is missing"


def test_canonical_has_expected_services() -> None:
    data = _yaml()
    services = set(data.get("services", {}).keys())
    expected = {"backend", "frontend", "redis", "worker"}
    missing = expected - services
    assert not missing, f"canonical compose missing services: {missing}"


@pytest.mark.parametrize("service", ["backend", "frontend", "worker"])
def test_no_source_bind_mounts_on_production_services(service: str) -> None:
    """Source bind mounts shadow built images and defeat prod parity.

    Named volumes (e.g. 'uploads:/app/uploads') are fine; host paths
    (anything starting with '.' or '/') are not, except the explicit
    Docker-managed anonymous volume pattern '/app/node_modules' which
    is also banned because it implies dev hot-reload wiring.
    """
    data = _yaml()
    svc = data["services"][service]
    volumes = svc.get("volumes") or []
    bad: list[str] = []
    for v in volumes:
        # Strings of form 'src:dst[:mode]' or short volume name 'name:dst'.
        if not isinstance(v, str):
            continue
        src = v.split(":", 1)[0]
        # Host paths begin with '.' or '/'. Anonymous-volume short forms
        # like '/app/node_modules' (single token, starts with '/') are
        # also banned because they imply hot-reload semantics.
        if src.startswith(".") or src.startswith("/"):
            bad.append(v)
    assert not bad, (
        f"Service {service!r} has source/anonymous bind mounts that "
        f"shadow the built image: {bad}. Move dev wiring to a separate "
        f"override file."
    )


def test_redis_still_requires_password() -> None:
    data = _yaml()
    redis = data["services"]["redis"]
    cmd = redis.get("command", "")
    assert "requirepass" in cmd, (
        "Redis must run with --requirepass; this is the only auth "
        "barrier between worker/backend and the data plane."
    )


def test_makefile_targets_reference_canonical_compose() -> None:
    mk = (REPO_ROOT / "Makefile").read_text()
    # Each docker-* target line must point at the canonical path.
    for target in ("docker-up", "docker-down", "docker-logs"):
        # Find the body line(s) for the target.
        idx = mk.find(target + ":")
        assert idx >= 0, f"Makefile target {target!r} missing"
        # Look at the next few lines for the compose-file path.
        body = mk[idx : idx + 400]
        assert "infra/docker-compose.yml" in body, (
            f"Makefile target {target!r} does not reference "
            f"infra/docker-compose.yml; found:\n{body[:300]}"
        )
        assert "-f docker-compose.yml" not in body, (
            f"Makefile target {target!r} still references the deleted "
            f"root docker-compose.yml"
        )
