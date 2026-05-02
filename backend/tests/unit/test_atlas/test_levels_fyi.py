"""Unit tests for ATLAS LevelsFYIProvider."""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from ai_engine.agents.sub_agents.atlas.sources.levels_fyi import (
    LevelsFYIProvider,
    _coerce_money,
    _walk_for_percentiles,
)


_run = asyncio.run


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)


class _FakeClient:
    def __init__(self, route_map):
        # route_map: dict[url_prefix -> _FakeResp]
        self._routes = sorted(route_map.items(), key=lambda kv: -len(kv[0]))
        self.calls: list[str] = []

    async def get(self, url, **_kw):
        self.calls.append(url)
        for prefix, resp in self._routes:
            if url.startswith(prefix):
                return resp
        return _FakeResp(404, "")

    async def aclose(self):
        pass


def _wrap_next_data(payload: dict) -> str:
    blob = json.dumps(payload)
    return (
        f"<html><head><title>Salaries</title></head><body>"
        f'<script id="__NEXT_DATA__" type="application/json">{blob}</script>'
        f"</body></html>"
    )


# ---------------------------------------------------------------------------
# _coerce_money
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        (185000, 185000),
        (185000.0, 185000),
        ("$185,000", 185000),
        ("185k", 185000),
        ("1.5M", 1_500_000),
        ("garbage", None),
        ("", None),
        (None, None),
        (-100, None),
        (0, None),
        ([], None),
    ],
)
def test_coerce_money(raw, expected):
    assert _coerce_money(raw) == expected


# ---------------------------------------------------------------------------
# _walk_for_percentiles
# ---------------------------------------------------------------------------

def test_walk_finds_direct_percentiles_dict():
    payload = {"props": {"pageProps": {"compensation": {"p25": 1, "p50": 2, "p75": 3}}}}
    found = _walk_for_percentiles(payload)
    assert found == {"p25": 1, "p50": 2, "p75": 3}


def test_walk_finds_nested_in_list():
    payload = {"data": [{"x": 1}, {"percentiles": {"p25": 100, "p50": 200, "p75": 300}}]}
    found = _walk_for_percentiles(payload)
    assert found == {"p25": 100, "p50": 200, "p75": 300}


def test_walk_returns_none_when_no_percentiles():
    payload = {"props": {"pageProps": {"compensation": {"foo": "bar"}}}}
    assert _walk_for_percentiles(payload) is None


def test_walk_handles_garbage():
    assert _walk_for_percentiles(None) is None
    assert _walk_for_percentiles("string") is None
    assert _walk_for_percentiles(123) is None


# ---------------------------------------------------------------------------
# Slug normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Stripe", "stripe"),
        ("Snap Inc.", "snap-inc"),
        ("FOO_BAR", "foo-bar"),
        ("https://www.levels.fyi/companies/google/", "google"),
        ("  ", None),
        ("", None),
        (None, None),
        ("Acme  Co", "acme-co"),
        ("a---b", "a-b"),
    ],
)
def test_normalize_slug(raw, expected):
    assert LevelsFYIProvider._normalize_slug(raw) == expected


# ---------------------------------------------------------------------------
# fetch — happy / failure paths
# ---------------------------------------------------------------------------

def test_empty_company_returns_failure():
    p = LevelsFYIProvider(http_client=_FakeClient({}))
    out = _run(p.fetch(company=""))
    assert out.success is False
    assert "empty company" in (out.error or "")


def test_non_200_returns_failure():
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(403, "")})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="stripe"))
    assert out.success is False
    assert "status=403" in (out.error or "")


def test_blocked_marker_returns_failure():
    html = "<html><body>Captcha challenge required</body></html>"
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="stripe"))
    assert out.success is False
    assert "blocked" in (out.error or "")


def test_no_next_data_returns_failure():
    html = "<html><body>nothing useful</body></html>"
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="stripe"))
    assert out.success is False
    assert "no percentile data" in (out.error or "")


def test_next_data_without_percentiles_returns_failure():
    html = _wrap_next_data({"props": {"pageProps": {"misc": "foo"}}})
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="stripe"))
    assert out.success is False


def test_happy_path_extracts_full_band():
    payload = {"props": {"pageProps": {"compensation": {
        "p25": "$160,000", "p50": "$185,000", "p75": "$220,000",
    }}}}
    html = _wrap_next_data(payload)
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="Stripe", role="Senior Engineer"))
    assert out.success is True
    assert out.raw["salary_band"] == {"p25": 160000, "p50": 185000, "p75": 220000}
    assert out.raw["company"] == "stripe"
    assert out.raw["role"] == "senior-engineer"
    assert "stripe" in out.raw["url"] and "senior-engineer" in out.raw["url"]


def test_happy_path_with_only_p50_and_p75():
    payload = {"props": {"pageProps": {"percentiles": {
        "p50": 200000, "p75": 250000,
    }}}}
    html = _wrap_next_data(payload)
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="meta"))
    assert out.success is True
    assert out.raw["salary_band"] == {"p50": 200000, "p75": 250000}


def test_alternative_key_names():
    payload = {"props": {"pageProps": {"salaryPercentiles": {
        "twentyFifthPercentile": 150000,
        "median": 180000,
        "seventyFifthPercentile": 210000,
    }}}}
    html = _wrap_next_data(payload)
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="amazon"))
    assert out.success is True
    assert out.raw["salary_band"] == {"p25": 150000, "p50": 180000, "p75": 210000}


def test_p50_missing_aborts():
    payload = {"props": {"pageProps": {"compensation": {
        "p25": 100000, "p75": 200000,  # no p50
    }}}}
    html = _wrap_next_data(payload)
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="stripe"))
    # _walk requires _has_percentile_fields → needs p50 + (p25 or p75)
    assert out.success is False


def test_network_exception_returns_failure():
    class _BoomClient:
        async def get(self, url, **_kw):
            raise RuntimeError("network down")

        async def aclose(self):
            pass

    p = LevelsFYIProvider(http_client=_BoomClient())
    out = _run(p.fetch(company="stripe"))
    assert out.success is False
    assert "network down" in (out.error or "")


def test_default_role_when_not_provided():
    payload = {"props": {"pageProps": {"compensation": {
        "p25": 100000, "p50": 150000, "p75": 200000,
    }}}}
    html = _wrap_next_data(payload)
    client = _FakeClient({"https://www.levels.fyi/": _FakeResp(200, html)})
    p = LevelsFYIProvider(http_client=client)
    out = _run(p.fetch(company="stripe"))
    assert out.success is True
    assert out.raw["role"] == "software-engineer"
    assert "software-engineer" in client.calls[0]


# ---------------------------------------------------------------------------
# Live smoke test (opt-in via RECON_LEVELS_PROVIDER=real)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("RECON_LEVELS_PROVIDER") != "real",
    reason="set RECON_LEVELS_PROVIDER=real to enable the live levels.fyi smoke test",
)
def test_live_levels_fyi_stripe():  # pragma: no cover
    p = LevelsFYIProvider()
    out = _run(p.fetch(company="stripe", role="software-engineer"))
    # Cloudflare or schema drift may still fail; we just assert the call runs.
    assert out.provider == "levels_fyi"
    assert out.layer == 1
    assert isinstance(out.latency_ms, int)
