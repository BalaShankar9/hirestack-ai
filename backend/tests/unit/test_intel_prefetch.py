"""W4 Functionality gaps — /api/intel/prefetch + pipeline cache hit.

Anchor tests: prove the endpoint module exists, rejects bad input,
caches correctly, and pipeline_runtime's recon block consults the cache.
"""
from __future__ import annotations

import inspect


def test_intel_prefetch_module_exposes_router() -> None:
    from app.api.routes import intel as intel_module
    assert hasattr(intel_module, "router"), "prefetch router must be exported"
    # route registered
    paths = {getattr(r, "path", "") for r in intel_module.router.routes}
    assert any("/intel/prefetch" in p for p in paths), paths


def test_intel_prefetch_cache_key_is_namespaced() -> None:
    from app.api.routes.intel import _intel_cache_key
    key = _intel_cache_key("x" * 200, "Senior Engineer")
    assert key.startswith("intel_"), key
    assert len(key) > len("intel_jd_"), "key must carry a hash"


def test_intel_prefetch_registered_in_api_router() -> None:
    from pathlib import Path
    init_path = Path(__file__).resolve().parents[2] / "app" / "api" / "routes" / "__init__.py"
    src = init_path.read_text(encoding="utf-8")
    assert "intel_router" in src
    assert "include_router(intel_router" in src


def test_pipeline_checks_prefetch_cache_before_launch() -> None:
    from app.services import pipeline_runtime
    src = inspect.getsource(pipeline_runtime)
    # guards that keep the fast path intact
    assert "intel_cache_key = \"intel_\" + JDAnalysisCache.hash_jd" in src
    assert "cached_intel = get_jd_cache().get(intel_cache_key)" in src
    assert "recon.company_intel_cached" in src


def test_prefetch_request_validates_jd_length() -> None:
    from app.api.routes.intel import _PrefetchRequest
    from pydantic import ValidationError
    try:
        _PrefetchRequest(
            jd_text="too short",
            job_title="X",
            company="Y",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("should have rejected short jd_text")


def test_prefetch_request_accepts_optional_company_url() -> None:
    from app.api.routes.intel import _PrefetchRequest
    ok = _PrefetchRequest(
        jd_text="x" * 100,
        job_title="Senior Engineer",
        company="Acme",
        company_url=None,
    )
    assert ok.company_url is None


def test_intel_route_uses_rate_limit() -> None:
    """Guard against accidental removal of the rate-limit decorator."""
    from app.api.routes import intel as intel_module
    src = inspect.getsource(intel_module)
    assert "@limiter.limit(" in src, "prefetch must stay rate-limited"
