#!/usr/bin/env python3
"""Production deployment verification.

Run AFTER deploying to a real environment (Railway / Netlify) to confirm
the deployed surface is healthy. Designed to be run manually or from CI:

    python scripts/health_check.py --backend https://api.hirestack.app \\
                                   --frontend https://app.hirestack.app

Exit code:
  0  → all checks passed (the deploy is GREEN)
  1  → at least one critical check failed (the deploy is NOT GREEN)
  2  → at least one non-critical check failed (the deploy is DEGRADED)

This is the script the production-readiness verdict cites as the gate
between "code-complete" and "verified live". It runs no migrations,
mutates no state, and reads no secrets — safe to run from anywhere.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Optional
from urllib import error as urlerror
from urllib import request as urlrequest


@dataclass
class CheckResult:
    name: str
    passed: bool
    critical: bool
    detail: str
    latency_ms: int


def _http_get(url: str, *, timeout: float = 10.0) -> tuple[int, str]:
    """Return (status_code, body_text) or raise."""
    req = urlrequest.Request(url, method="GET", headers={
        "User-Agent": "hirestack-health-check/1.0",
        "Accept": "application/json,text/html,*/*",
    })
    with urlrequest.urlopen(req, timeout=timeout) as resp:  # nosec B310 — fixed scheme, operator-supplied URL
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body


def _check(name: str, url: str, *, critical: bool, expect_status: int = 200,
           expect_body_contains: Optional[str] = None,
           expect_json_key: Optional[str] = None) -> CheckResult:
    started = time.perf_counter()
    try:
        status, body = _http_get(url)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if status != expect_status:
            return CheckResult(
                name=name, passed=False, critical=critical,
                detail=f"HTTP {status} (expected {expect_status})",
                latency_ms=latency_ms,
            )

        if expect_body_contains and expect_body_contains not in body:
            return CheckResult(
                name=name, passed=False, critical=critical,
                detail=f"body did not contain {expect_body_contains!r}",
                latency_ms=latency_ms,
            )

        if expect_json_key:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError as exc:
                return CheckResult(
                    name=name, passed=False, critical=critical,
                    detail=f"response is not valid JSON: {exc}",
                    latency_ms=latency_ms,
                )
            if expect_json_key not in parsed:
                return CheckResult(
                    name=name, passed=False, critical=critical,
                    detail=f"JSON missing key {expect_json_key!r}",
                    latency_ms=latency_ms,
                )

        return CheckResult(
            name=name, passed=True, critical=critical,
            detail=f"HTTP {status}",
            latency_ms=latency_ms,
        )

    except urlerror.HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name=name, passed=False, critical=critical,
            detail=f"HTTPError {exc.code} {exc.reason}",
            latency_ms=latency_ms,
        )
    except urlerror.URLError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name=name, passed=False, critical=critical,
            detail=f"URLError {exc.reason}",
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 — we want to capture every failure mode
        latency_ms = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name=name, passed=False, critical=critical,
            detail=f"{type(exc).__name__}: {exc}",
            latency_ms=latency_ms,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", required=True,
                        help="Backend base URL (e.g. https://api.hirestack.app)")
    parser.add_argument("--frontend", required=True,
                        help="Frontend base URL (e.g. https://app.hirestack.app)")
    args = parser.parse_args()

    backend = args.backend.rstrip("/")
    frontend = args.frontend.rstrip("/")

    checks: list[CheckResult] = []

    # ── CRITICAL backend checks ──────────────────────────────────────
    # If any of these fail the deploy is NOT green.
    checks.append(_check(
        "backend.health",
        f"{backend}/health",
        critical=True,
        expect_status=200,
        expect_json_key="status",
    ))
    checks.append(_check(
        "backend.openapi",
        f"{backend}/openapi.json",
        critical=True,
        expect_status=200,
        expect_body_contains='"openapi"',
    ))

    # ── NON-CRITICAL backend checks ──────────────────────────────────
    # These describe DEGRADED state — deploy is up but something is off.
    checks.append(_check(
        "backend.docs",
        f"{backend}/docs",
        critical=False,
        expect_status=200,
        expect_body_contains="Swagger UI",
    ))

    # ── CRITICAL frontend checks ─────────────────────────────────────
    checks.append(_check(
        "frontend.root",
        frontend + "/",
        critical=True,
        expect_status=200,
        expect_body_contains="<html",
    ))

    # ── REPORT ───────────────────────────────────────────────────────
    print("=" * 72)
    print(f"HireStack AI — deployment health check")
    print(f"  backend : {backend}")
    print(f"  frontend: {frontend}")
    print("=" * 72)
    crit_failed = []
    nonc_failed = []
    for c in checks:
        marker = "✓" if c.passed else ("✗" if c.critical else "⚠")
        tag = "CRIT" if c.critical else "WARN"
        print(f"  [{tag}] {marker} {c.name:<22} {c.latency_ms:>5}ms  {c.detail}")
        if not c.passed:
            (crit_failed if c.critical else nonc_failed).append(c)
    print("=" * 72)

    if crit_failed:
        print(f"FAIL: {len(crit_failed)} critical check(s) failed — deploy is NOT GREEN")
        for c in crit_failed:
            print(f"  ✗ {c.name}: {c.detail}")
        return 1
    if nonc_failed:
        print(f"DEGRADED: {len(nonc_failed)} non-critical check(s) failed — deploy is up but suboptimal")
        for c in nonc_failed:
            print(f"  ⚠ {c.name}: {c.detail}")
        return 2
    print(f"PASS: all {len(checks)} checks passed — deploy is GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
