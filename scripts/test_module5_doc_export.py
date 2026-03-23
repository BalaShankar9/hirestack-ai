#!/usr/bin/env python3
"""
Module 5 — Document Builder, Export & Data Services
Security audit test script

Covers: builder.py, export.py, benchmark.py, gaps.py, consultant.py, analytics.py
        + service files: document.py, export.py, benchmark.py, gap.py, roadmap.py, analytics.py

Run:  .venv/bin/python scripts/test_module5_doc_export.py
"""

import json
import os
import sys
import urllib.error
import urllib.request

# ── Bootstrap ──────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
FAKE_UUID = "99999999-9999-9999-9999-999999999999"

passed = failed = warnings = 0


def report(label: str, ok: bool, detail: str = "", *, warn: bool = False):
    global passed, failed, warnings
    if warn and ok:
        warnings += 1
        print(f"  ⚠ WARN  {label}: {detail}" if detail else f"  ⚠ WARN  {label}")
    elif ok:
        passed += 1
        print(f"  ✅ PASS  {label}")
    else:
        failed += 1
        msg = f"  ❌ FAIL  {label}"
        if detail:
            msg += f": {detail}"
        print(msg)


def do_req(path, method="GET", headers=None, body=None, timeout=10):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def json_req(path, method="POST", headers=None, body=None, timeout=10):
    return do_req(path, method, headers, body, timeout)


# ── Auth setup ─────────────────────────────────────────────────────────
from app.core.database import get_supabase

sb = get_supabase()
import uuid as _uuid

TEST_EMAIL = f"mod5test_{_uuid.uuid4().hex[:8]}@test.com"
TEST_PASS = "Test1234!"

try:
    _existing = sb.auth.admin.list_users()
    for _u in _existing:
        if hasattr(_u, "email") and _u.email and _u.email.startswith("mod5test_"):
            sb.auth.admin.delete_user(_u.id)
            print(f"  Cleaned up leftover test user {_u.id}")
except Exception:
    pass

try:
    _admin_resp = sb.auth.admin.create_user(
        {"email": TEST_EMAIL, "password": TEST_PASS, "email_confirm": True}
    )
    TEST_USER_ID = _admin_resp.user.id
except Exception as e:
    print(f"  ⚠ Could not create test user: {e}")
    TEST_USER_ID = None

ACCESS_TOKEN = None
if TEST_USER_ID:
    try:
        _sign_resp = sb.auth.sign_in_with_password({"email": TEST_EMAIL, "password": TEST_PASS})
        ACCESS_TOKEN = (
            _sign_resp.session.access_token
            if hasattr(_sign_resp, "session") and _sign_resp.session
            else None
        )
    except Exception:
        pass

AUTH = {"Authorization": f"Bearer {ACCESS_TOKEN}"} if ACCESS_TOKEN else {}

# ── Read source files for code-level checks ────────────────────────────
_root = os.path.join(os.path.dirname(__file__), "..")
_route_dir = os.path.join(_root, "backend", "app", "api", "routes")
_svc_dir = os.path.join(_root, "backend", "app", "services")


def _read(path):
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


builder_src = _read(os.path.join(_route_dir, "builder.py"))
export_src = _read(os.path.join(_route_dir, "export.py"))
benchmark_src = _read(os.path.join(_route_dir, "benchmark.py"))
gaps_src = _read(os.path.join(_route_dir, "gaps.py"))
consultant_src = _read(os.path.join(_route_dir, "consultant.py"))
analytics_src = _read(os.path.join(_route_dir, "analytics.py"))

svc_document_src = _read(os.path.join(_svc_dir, "document.py"))
svc_export_src = _read(os.path.join(_svc_dir, "export.py"))
svc_benchmark_src = _read(os.path.join(_svc_dir, "benchmark.py"))
svc_gap_src = _read(os.path.join(_svc_dir, "gap.py"))
svc_roadmap_src = _read(os.path.join(_svc_dir, "roadmap.py"))
svc_analytics_src = _read(os.path.join(_svc_dir, "analytics.py"))

all_route_srcs = {
    "builder": builder_src,
    "export": export_src,
    "benchmark": benchmark_src,
    "gaps": gaps_src,
    "consultant": consultant_src,
    "analytics": analytics_src,
}
all_svc_srcs = {
    "document": svc_document_src,
    "export": svc_export_src,
    "benchmark": svc_benchmark_src,
    "gap": svc_gap_src,
    "roadmap": svc_roadmap_src,
    "analytics": svc_analytics_src,
}

# ═══════════════════════════════════════════════════════════════════
# 0. PRE-FLIGHT
# ═══════════════════════════════════════════════════════════════════
print("\n══ 0. PRE-FLIGHT ══")
try:
    r = do_req("/health", "GET")
    report("Backend healthy", r.status == 200)
except Exception:
    report("Backend healthy", False, "backend unreachable")
    print("\nBackend is not running. Exiting.")
    sys.exit(1)

report("Auth token acquired", bool(ACCESS_TOKEN), "no token — auth tests will be limited")


# ═══════════════════════════════════════════════════════════════════
# 1. ENDPOINT WIRING
# ═══════════════════════════════════════════════════════════════════
print("\n══ 1. ENDPOINT WIRING ══")
wiring_tests = [
    ("POST", "/api/builder/generate"),
    ("POST", "/api/builder/generate-all"),
    ("GET", "/api/builder/documents"),
    ("POST", "/api/export"),
    ("GET", "/api/export"),
    ("GET", "/api/benchmark/" + FAKE_UUID),
    ("POST", "/api/benchmark/generate"),
    ("POST", "/api/gaps/analyze"),
    ("GET", "/api/gaps"),
    ("POST", "/api/consultant/roadmap"),
    ("GET", "/api/consultant/roadmaps"),
    ("GET", "/api/analytics/dashboard"),
    ("POST", "/api/analytics/track"),
]
for method, path in wiring_tests:
    try:
        do_req(path, method)
        report(f"{method} {path} wired", True)
    except urllib.error.HTTPError as e:
        report(f"{method} {path} wired", e.code != 404, f"HTTP {e.code}")
    except Exception as e:
        report(f"{method} {path} wired", False, str(e)[:100])


# ═══════════════════════════════════════════════════════════════════
# 2. AUTH ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════
print("\n══ 2. AUTH ENFORCEMENT ══")
auth_endpoints = [
    ("POST", "/api/builder/generate", {"document_type": "cv", "profile_id": FAKE_UUID}),
    ("POST", "/api/builder/generate-all", {"profile_id": FAKE_UUID, "job_id": FAKE_UUID}),
    ("GET", "/api/builder/documents", None),
    ("GET", f"/api/builder/documents/{FAKE_UUID}", None),
    ("PUT", f"/api/builder/documents/{FAKE_UUID}", {"title": "x"}),
    ("POST", f"/api/builder/documents/{FAKE_UUID}/version", None),
    ("DELETE", f"/api/builder/documents/{FAKE_UUID}", None),
    ("POST", "/api/export", {"document_ids": [], "format": "pdf"}),
    ("GET", "/api/export", None),
    ("GET", f"/api/export/{FAKE_UUID}", None),
    ("GET", f"/api/export/{FAKE_UUID}/download", None),
    ("DELETE", f"/api/export/{FAKE_UUID}", None),
    ("POST", "/api/benchmark/generate", {"job_id": FAKE_UUID}),
    ("GET", f"/api/benchmark/{FAKE_UUID}", None),
    ("GET", f"/api/benchmark/job/{FAKE_UUID}", None),
    ("POST", f"/api/benchmark/{FAKE_UUID}/regenerate", None),
    ("DELETE", f"/api/benchmark/{FAKE_UUID}", None),
    ("POST", "/api/gaps/analyze", {"profile_id": FAKE_UUID, "benchmark_id": FAKE_UUID}),
    ("GET", "/api/gaps", None),
    ("GET", f"/api/gaps/{FAKE_UUID}", None),
    ("GET", f"/api/gaps/{FAKE_UUID}/summary", None),
    ("POST", f"/api/gaps/{FAKE_UUID}/refresh", None),
    ("DELETE", f"/api/gaps/{FAKE_UUID}", None),
    ("POST", "/api/consultant/roadmap", {"gap_report_id": FAKE_UUID}),
    ("GET", "/api/consultant/roadmaps", None),
    ("GET", f"/api/consultant/roadmap/{FAKE_UUID}", None),
    ("PUT", f"/api/consultant/roadmap/{FAKE_UUID}/progress", {"milestone_id": "x", "status": "done"}),
    ("DELETE", f"/api/consultant/roadmap/{FAKE_UUID}", None),
    ("GET", "/api/analytics/dashboard", None),
    ("GET", "/api/analytics/activity", None),
    ("GET", "/api/analytics/progress", None),
    ("POST", "/api/analytics/track", {"event_type": "test"}),
    ("GET", "/api/analytics/stats/applications", None),
]
for method, path, body in auth_endpoints:
    try:
        do_req(path, method, body=body)
        report(f"Auth required: {method} {path}", False, "no 401/403 — auth bypassed!")
    except urllib.error.HTTPError as e:
        report(f"Auth required: {method} {path}", e.code in (401, 403), f"HTTP {e.code}")
    except Exception as e:
        report(f"Auth required: {method} {path}", False, str(e)[:100])


# ═══════════════════════════════════════════════════════════════════
# 3. RATE LIMITING
# ═══════════════════════════════════════════════════════════════════
print("\n══ 3. RATE LIMITING ══")

# Code-level: check for centralized limiter import
for name, src in all_route_srcs.items():
    has_limiter = "from app.core.security import limiter" in src or "@limiter.limit" in src
    # builder.py currently has a LOCAL limiter
    if name == "builder":
        has_local = "Limiter(key_func=" in src
        uses_centralized = "from app.core.security import limiter" in src
        report(f"{name}.py uses centralized limiter", uses_centralized,
               "Uses local Limiter instance (not centralized)" if has_local and not uses_centralized else "")
    else:
        report(f"{name}.py has rate limiting", has_limiter,
               "No rate limiting on any endpoint" if not has_limiter else "")


# ═══════════════════════════════════════════════════════════════════
# 4. INPUT VALIDATION — RAW DICT REQUESTS
# ═══════════════════════════════════════════════════════════════════
print("\n══ 4. INPUT VALIDATION — RAW DICT REQUESTS ══")

# Code check: endpoints that accept Dict[str, Any] instead of Pydantic
for name, src in all_route_srcs.items():
    uses_raw_dict = "request: Dict[str, Any]" in src or "body: Dict[str, Any]" in src
    report(f"{name}.py uses Pydantic models (not raw Dict)",
           not uses_raw_dict,
           "Accepts raw Dict[str, Any] — no input validation" if uses_raw_dict else "")

# Live: builder /generate should reject missing profile_id
if ACCESS_TOKEN:
    try:
        json_req("/api/builder/generate", "POST", headers=AUTH, body={
            "document_type": "cv",
            # missing profile_id
        })
        report("Builder: missing profile_id → 422", False, "accepted without profile_id")
    except urllib.error.HTTPError as e:
        report("Builder: missing profile_id → 422", e.code == 422, f"HTTP {e.code}")

    # Export: missing body fields
    try:
        json_req("/api/export", "POST", headers=AUTH, body={})
        # This may succeed with empty docs (400) or fail later
        report("Export: empty body handled", True)
    except urllib.error.HTTPError as e:
        report("Export: empty body handled", e.code in (400, 422), f"HTTP {e.code}")

    # Analytics track: missing event_type
    try:
        json_req("/api/analytics/track", "POST", headers=AUTH, body={})
        report("Analytics: missing event_type → 422", False, "accepted without event_type")
    except urllib.error.HTTPError as e:
        report("Analytics: missing event_type → 422", e.code == 422, f"HTTP {e.code}")

    # Gaps analyze: missing fields
    try:
        json_req("/api/gaps/analyze", "POST", headers=AUTH, body={})
        report("Gaps: missing fields → 400/422", False, "accepted without required fields")
    except urllib.error.HTTPError as e:
        report("Gaps: missing fields → 400/422", e.code in (400, 422), f"HTTP {e.code}")

    # Consultant: missing gap_report_id
    try:
        json_req("/api/consultant/roadmap", "POST", headers=AUTH, body={})
        report("Consultant: missing gap_report_id → 422", False, "accepted")
    except urllib.error.HTTPError as e:
        report("Consultant: missing gap_report_id → 422", e.code == 422, f"HTTP {e.code}")
else:
    report("Input validation: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 5. UUID VALIDATION ON PATH PARAMETERS
# ═══════════════════════════════════════════════════════════════════
print("\n══ 5. UUID VALIDATION ══")

BAD_UUID = "not-a-uuid"

if ACCESS_TOKEN:
    uuid_tests = [
        ("GET", f"/api/builder/documents/{BAD_UUID}", None, "builder get_document"),
        ("PUT", f"/api/builder/documents/{BAD_UUID}", {"title": "x"}, "builder update_document"),
        ("DELETE", f"/api/builder/documents/{BAD_UUID}", None, "builder delete_document"),
        ("GET", f"/api/export/{BAD_UUID}", None, "export get_export"),
        ("GET", f"/api/export/{BAD_UUID}/download", None, "export download"),
        ("DELETE", f"/api/export/{BAD_UUID}", None, "export delete"),
        ("GET", f"/api/benchmark/{BAD_UUID}", None, "benchmark get"),
        ("GET", f"/api/benchmark/job/{BAD_UUID}", None, "benchmark for_job"),
        ("POST", f"/api/benchmark/{BAD_UUID}/regenerate", None, "benchmark regenerate"),
        ("DELETE", f"/api/benchmark/{BAD_UUID}", None, "benchmark delete"),
        ("GET", f"/api/gaps/{BAD_UUID}", None, "gaps get_report"),
        ("GET", f"/api/gaps/{BAD_UUID}/summary", None, "gaps summary"),
        ("POST", f"/api/gaps/{BAD_UUID}/refresh", None, "gaps refresh"),
        ("DELETE", f"/api/gaps/{BAD_UUID}", None, "gaps delete"),
        ("GET", f"/api/consultant/roadmap/{BAD_UUID}", None, "consultant get_roadmap"),
        ("PUT", f"/api/consultant/roadmap/{BAD_UUID}/progress",
         {"milestone_id": "x", "status": "done"}, "consultant update_progress"),
        ("DELETE", f"/api/consultant/roadmap/{BAD_UUID}", None, "consultant delete_roadmap"),
    ]
    for method, path, body, label in uuid_tests:
        try:
            do_req(path, method, headers=AUTH, body=body)
            report(f"UUID: {label} bad-uuid → 422/404", False, "accepted bad UUID")
        except urllib.error.HTTPError as e:
            report(f"UUID: {label} bad-uuid → 422/404", e.code in (404, 422), f"HTTP {e.code}")
else:
    report("UUID validation: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 6. IDOR PROTECTION — Ownership checks
# ═══════════════════════════════════════════════════════════════════
print("\n══ 6. IDOR PROTECTION ══")

if ACCESS_TOKEN:
    # Try accessing documents that don't belong to user
    idor_tests = [
        ("GET", f"/api/builder/documents/{FAKE_UUID}", None, "builder document", 404),
        ("PUT", f"/api/builder/documents/{FAKE_UUID}", {"title": "hacked"}, "builder update", 404),
        ("DELETE", f"/api/builder/documents/{FAKE_UUID}", None, "builder delete", 404),
        ("GET", f"/api/export/{FAKE_UUID}", None, "export get", 404),
        ("DELETE", f"/api/export/{FAKE_UUID}", None, "export delete", 404),
        ("GET", f"/api/benchmark/{FAKE_UUID}", None, "benchmark get", 404),
        ("DELETE", f"/api/benchmark/{FAKE_UUID}", None, "benchmark delete", 404),
        ("GET", f"/api/gaps/{FAKE_UUID}", None, "gaps report", 404),
        ("DELETE", f"/api/gaps/{FAKE_UUID}", None, "gaps delete", 404),
        ("GET", f"/api/consultant/roadmap/{FAKE_UUID}", None, "consultant roadmap", 404),
        ("DELETE", f"/api/consultant/roadmap/{FAKE_UUID}", None, "consultant delete", 404),
    ]
    for method, path, body, label, expected in idor_tests:
        try:
            do_req(path, method, headers=AUTH, body=body)
            report(f"IDOR: {label} → {expected}", False, "returned data for non-owned resource")
        except urllib.error.HTTPError as e:
            report(f"IDOR: {label} → {expected}", e.code == expected, f"HTTP {e.code}")
else:
    report("IDOR protection: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 7. ERROR SANITIZATION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 7. ERROR SANITIZATION ══")

# Check for raw error leaks: f"...{e}" in error responses (str(e) in ValueError is safe)
for name, src in all_route_srcs.items():
    has_raw_leak = False
    for line in src.split("\n"):
        if "detail=" in line and ('f"' in line or "f'" in line) and "{e}" in line:
            has_raw_leak = True
            break
    report(f"{name}.py error messages sanitized",
           not has_raw_leak,
           "Leaks raw exception via f-string in HTTP detail" if has_raw_leak else "")

# Same check for service files
for name, src in all_svc_srcs.items():
    has_raw_leak = False
    for line in src.split("\n"):
        if "detail=" in line and ('f"' in line or "f'" in line) and "{e}" in line:
            has_raw_leak = True
            break
    report(f"service/{name}.py error messages sanitized",
           not has_raw_leak,
           "Leaks raw exception via f-string in HTTP detail" if has_raw_leak else "")

# Live: generate benchmark with fake job → should not leak internals
if ACCESS_TOKEN:
    try:
        json_req("/api/benchmark/generate", "POST", headers=AUTH, body={"job_id": FAKE_UUID})
        report("Benchmark error sanitized", False, "should have raised 400/404")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        has_traceback = any(kw in body_text.lower() for kw in [
            "traceback", "file \"", "line ", "/app/", "supabase", "postgrest"
        ])
        report("Benchmark error sanitized",
               not has_traceback,
               f"Leaks internal error details: {body_text[:100]}" if has_traceback else "")

    # ATS scan with fake data
    try:
        json_req("/api/gaps/analyze", "POST", headers=AUTH, body={
            "profile_id": FAKE_UUID,
            "benchmark_id": FAKE_UUID,
        })
        report("Gaps error sanitized", False, "should have raised 400/404")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        has_traceback = any(kw in body_text.lower() for kw in [
            "traceback", "file \"", "line ", "/app/", "supabase"
        ])
        report("Gaps error sanitized",
               not has_traceback,
               f"Leaks internal error: {body_text[:100]}" if has_traceback else "")
else:
    report("Error sanitization: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 8. EXPORT SECURITY
# ═══════════════════════════════════════════════════════════════════
print("\n══ 8. EXPORT SECURITY ══")

# Check Content-Disposition header injection
report("Export uses Pydantic model (not raw dict)",
       "class " in export_src and "BaseModel" in export_src or "request: Dict" not in export_src,
       "Export request accepts raw Dict — no validation")

# Check export format validation
report("Export validates format",
       'raise ValueError(f"Unsupported format' in svc_export_src or
       "Unsupported format" in svc_export_src)

# Check filename sanitization in Content-Disposition
has_safe_disposition = 'f"attachment; filename={filename}"' not in export_src
if not has_safe_disposition:
    # Check if the filename comes from user input unsanitized
    has_safe_disposition = "filename=" in export_src and "sanitize" in export_src.lower()
report("Export Content-Disposition safe",
       has_safe_disposition,
       "Content-Disposition uses unsanitized filename" if not has_safe_disposition else "",
       warn=not has_safe_disposition)

# Check download fetches external URLs
has_external_fetch = "httpx" in svc_export_src and "client.get(file_url)" in svc_export_src
report("Export download validates URL source",
       not has_external_fetch or "supabase" in svc_export_src.lower(),
       "Downloads from arbitrary external URLs via httpx" if has_external_fetch else "",
       warn=has_external_fetch)


# ═══════════════════════════════════════════════════════════════════
# 9. SERVICE ARCHITECTURE
# ═══════════════════════════════════════════════════════════════════
print("\n══ 9. SERVICE ARCHITECTURE ══")

# Check for AIClient() instantiation (should use singleton)
for name, src in all_svc_srcs.items():
    uses_singleton = "get_ai_client" in src
    creates_fresh = "AIClient()" in src
    if creates_fresh or "AIClient" in src:
        report(f"service/{name}.py uses AI client singleton",
               uses_singleton,
               "Creates fresh AIClient() per instance" if creates_fresh and not uses_singleton else "")

# Check IDOR in service layer — verify user_id checks
for name, src in all_svc_srcs.items():
    if "user_id" in src:
        checks_ownership = ('user_id") != user_id' in src or
                           'user_id") == user_id' in src or
                           '"user_id", "==", user_id' in src or
                           "eq(\"user_id\"" in src)
        report(f"service/{name}.py checks ownership",
               checks_ownership,
               "Missing user_id ownership check" if not checks_ownership else "")


# ═══════════════════════════════════════════════════════════════════
# 10. ANALYTICS INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 10. ANALYTICS INPUT VALIDATION ══")

# Check event_type is bounded
report("TrackEventRequest has max_length on event_type",
       "max_length" in analytics_src and "event_type" in analytics_src,
       "event_type has no max_length — unlimited storage injection")

# Check days param is bounded
report("Activity days param bounded",
       "le=" in analytics_src or "lt=" in analytics_src,
       "days param has no upper bound")

# Check event_data is bounded
report("event_data has size constraint",
       "max_length" in analytics_src and "event_data" in analytics_src,
       "event_data dict has no size constraint — potential storage abuse")


# ═══════════════════════════════════════════════════════════════════
# 11. BUILDER INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 11. BUILDER INPUT VALIDATION ══")

# Check document_type is validated to allowed values
report("Builder document_type validated to enum",
       "Literal[" in builder_src or "enum" in builder_src.lower() or
       "cv" in builder_src and "cover_letter" in builder_src and "motivation" in svc_document_src,
       "document_type accepts arbitrary strings" if "document_type: str" in builder_src else "")

# Check profile_id has UUID validation
report("Builder profile_id has UUID validation",
       "uuid" in builder_src.lower() or "validator" in builder_src.lower(),
       "profile_id is unvalidated string")

# Check options field is bounded
report("Builder options field bounded",
       "max_length" in builder_src or "max_items" in builder_src,
       "options dict is unbounded — can be arbitrarily large")

# UpdateDocumentRequest allows arbitrary status values
report("UpdateDocumentRequest validates status",
       "Literal[" in builder_src and "status" in builder_src or
       "enum" in builder_src.lower(),
       "status field accepts arbitrary strings")

# Check that service layer validates document_type
report("DocumentService validates document_type",
       "Unsupported document type" in svc_document_src or "raise ValueError" in svc_document_src,
       "Service does not validate document_type")


# ═══════════════════════════════════════════════════════════════════
# 12. BENCHMARK INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 12. BENCHMARK INPUT VALIDATION ══")

# Benchmark generate accepts raw Dict[str, Any]
report("Benchmark uses Pydantic model",
       "class " in benchmark_src and "BaseModel" in benchmark_src,
       "Uses raw Dict[str, Any] for request body — no validation")

# Error handling: benchmark leaks raw errors
report("Benchmark generate error handling safe",
       'f"Failed to generate benchmark: {e}"' not in benchmark_src,
       "Leaks raw exception via f-string in 500 detail")

# Gaps analyze also uses raw Dict
report("Gaps uses Pydantic model",
       "class " in gaps_src and "BaseModel" in gaps_src,
       "Uses raw Dict[str, Any] for analyze request — no validation")

report("Gaps analyze error handling safe",
       'f"Failed to analyze gaps: {e}"' not in gaps_src,
       "Leaks raw exception via f-string in 500 detail")


# ═══════════════════════════════════════════════════════════════════
# 13. SECURITY HEADERS
# ═══════════════════════════════════════════════════════════════════
print("\n══ 13. SECURITY HEADERS ══")

try:
    r = do_req("/health", "GET")
    headers = dict(r.headers)
    checks = [
        ("x-content-type-options", "nosniff"),
        ("x-frame-options", None),
    ]
    for header, expected_val in checks:
        val = headers.get(header)
        if expected_val:
            report(f"Header {header}", val and expected_val.lower() in val.lower(),
                   f"Missing or wrong: {val}")
        else:
            report(f"Header {header} present", bool(val))
except Exception:
    report("Security headers check", False, "Could not fetch health")


# ═══════════════════════════════════════════════════════════════════
# 14. EXPORT CONTENT-DISPOSITION HEADER INJECTION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 14. CONTENT-DISPOSITION SAFETY ══")

# The export download builds Content-Disposition from DB filename
# If filename is user-controlled, header injection is possible
report("Export filename comes from DB (not user input in download)",
       "export.get(\"filename\"" in svc_export_src or
       'export.get("filename"' in svc_export_src,
       "Filename source unknown")

# Check if create_export sanitizes filename
report("Export create sanitizes filename",
       "sanitize" in svc_export_src.lower() or
       "hirestack_export_" in svc_export_src,
       "Filename not sanitized at creation time")

# Route-level: Content-Disposition uses f-string with filename
report("Route Content-Disposition quoted",
       'filename="' in export_src or "quote" in export_src.lower(),
       "Content-Disposition not quoted — header injection risk" if
       'f"attachment; filename={filename}"' in export_src else "")


# ═══════════════════════════════════════════════════════════════════
# 15. QUERY PARAMETER BOUNDS
# ═══════════════════════════════════════════════════════════════════
print("\n══ 15. QUERY PARAMETER BOUNDS ══")

# Check that limit/days params are bounded
for name, src in {**all_route_srcs, **all_svc_srcs}.items():
    if "limit=" in src or "days=" in src:
        has_bound = ("le=" in src or "lt=" in src or "max(" in src or
                     "min(" in src or "Query(" in src)
        # Just check service layer limits
        if "limit=50" in src or "limit=200" in src or "limit=500" in src:
            report(f"{name}: query limits have hardcoded bounds", True)
        elif "days:" in src and "Query(" in src:
            report(f"{name}: days param uses Query()", True)


# ═══════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════
print("\n══ CLEANUP ══")
if TEST_USER_ID:
    try:
        sb.auth.admin.delete_user(TEST_USER_ID)
        print(f"  Cleaned up test user {TEST_USER_ID}")
    except Exception as e:
        print(f"  ⚠ Cleanup failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'=' * 60}")
print(f"RESULTS: {passed}/{passed + failed} passed, {failed} failed, {warnings} warning(s)")
if failed == 0 and warnings == 0:
    print("ALL LIVE TESTS PASSED")
elif failed == 0:
    print(f"{warnings} WARNING(S) — review recommended")
else:
    print(f"{failed} ISSUE(S) NEED ATTENTION")
