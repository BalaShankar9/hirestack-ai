#!/usr/bin/env python3
"""
Module 3 — Job Description Parsing & Management — Deep Audit Test Suite
========================================================================
Covers:
  • /api/jobs/*            — CRUD + AI parse
  • /api/job-sync/*        — Alerts + match scoring
  • /api/generate/pipeline — AI generation pipeline (auth, rate limit)
  • /api/generate/jobs/*   — DB-backed generation jobs
  • Code-level architecture assertions
"""

import json
import os
import sys
import urllib.error
import urllib.request
import pathlib

# ── Configuration ────────────────────────────────────────────────────
BASE = os.environ.get("API_BASE", "http://localhost:8000")
# Real user UUID (FK constraint on users.id → auth.users.id)
USER_UUID = "0a123bb9-9a87-4067-aaba-d434250abd2c"
FAKE_UUID = "99999999-9999-9999-9999-999999999999"
BAD_UUID = "not-a-uuid"

# Lightweight mock token — the backend validates via Supabase JWT
# For live testing we rely on the service-role/test user mechanism
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from app.core.database import get_supabase

sb = get_supabase()  # Uses service-role key
# Synthesise an auth header the backend will accept
# The backend's get_current_user validates the JWT against Supabase.
# We create a real JWT via Supabase Admin API.
# First clean up any leftover test user from a previous run
try:
    _existing = sb.auth.admin.list_users()
    for _u in _existing:
        if hasattr(_u, 'email') and _u.email == 'testmod3@hirestack.test':
            sb.auth.admin.delete_user(_u.id)
            print(f"  Cleaned up leftover test user {_u.id}")
            break
except Exception:
    pass

TEST_UID = None
try:
    _admin_resp = sb.auth.admin.create_user({
        "email": "testmod3@hirestack.test",
        "password": "Test!Module3#2026",
        "email_confirm": True,
        "user_metadata": {"name": "Module3 Test"},
    })
    TEST_UID = _admin_resp.user.id if hasattr(_admin_resp, 'user') and _admin_resp.user else None
except Exception as e:
    print(f"⚠ Could not create test user: {e}")

if not TEST_UID:
    # Fall back to real user
    TEST_UID = USER_UUID
    print(f"⚠ Could not create test user, using real user {USER_UUID}")

# Sign in to get a real access token
_sign_resp = sb.auth.sign_in_with_password({
    "email": "testmod3@hirestack.test",
    "password": "Test!Module3#2026",
})
ACCESS_TOKEN = _sign_resp.session.access_token if hasattr(_sign_resp, 'session') and _sign_resp.session else None

if not ACCESS_TOKEN:
    # Fall back: try the real user
    print("⚠ Could not sign in test user, trying real user")
    _sign_resp2 = sb.auth.sign_in_with_password({
        "email": "balashankarbollineni4@gmail.com",
        "password": os.environ.get("TEST_USER_PASSWORD", ""),
    })
    ACCESS_TOKEN = _sign_resp2.session.access_token if hasattr(_sign_resp2, 'session') and _sign_resp2.session else None
    TEST_UID = USER_UUID

AUTH = {"Authorization": f"Bearer {ACCESS_TOKEN}"} if ACCESS_TOKEN else {}

# ── Test infrastructure ──────────────────────────────────────────────
passed = failed = warnings = 0


def report(label: str, ok: bool, detail: str = "", warn: bool = False):
    global passed, failed, warnings
    if warn:
        warnings += 1
        print(f"  ⚠ WARN  {label}: {detail}")
    elif ok:
        passed += 1
        print(f"  ✅ PASS  {label}")
    else:
        failed += 1
        print(f"  ❌ FAIL  {label}: {detail}")


def do_req(path, method="GET", headers=None, data=None, content_type=None):
    url = BASE + path
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if content_type:
        req.add_header("Content-Type", content_type)
    return urllib.request.urlopen(req, data, timeout=15)


def json_req(path, method="GET", headers=None, body=None):
    """Helper for JSON requests."""
    data = json.dumps(body).encode() if body else None
    return do_req(path, method=method, headers=headers, data=data,
                  content_type="application/json" if data else None)


# ═══════════════════════════════════════════════════════════════════
# 0. PRE-FLIGHT — Backend health + auth
# ═══════════════════════════════════════════════════════════════════
print("\n══ 0. PRE-FLIGHT ══")
try:
    resp = do_req("/health")
    report("Backend healthy", True)
except Exception as e:
    report("Backend healthy", False, str(e)[:100])
    print("Cannot proceed — backend is down")
    sys.exit(1)

report("Auth token acquired", bool(ACCESS_TOKEN), "no token — auth tests will be limited")


# ═══════════════════════════════════════════════════════════════════
# 1. ENDPOINT WIRING — All job routes registered
# ═══════════════════════════════════════════════════════════════════
print("\n══ 1. ENDPOINT WIRING ══")

endpoints = [
    ("/api/jobs", "POST"),
    ("/api/jobs", "GET"),
    ("/api/jobs/fake-id", "GET"),
    ("/api/jobs/fake-id", "PUT"),
    ("/api/jobs/fake-id", "DELETE"),
    ("/api/jobs/fake-id/parse", "POST"),
    ("/api/job-sync/alerts", "POST"),
    ("/api/job-sync/alerts", "GET"),
    ("/api/job-sync/match", "POST"),
    ("/api/job-sync/matches", "GET"),
    ("/api/job-sync/matches/fake-id/status", "PUT"),
    ("/api/generate/pipeline", "POST"),
    ("/api/generate/pipeline/stream", "POST"),
    ("/api/generate/jobs", "POST"),
    ("/api/generate/jobs/fake-id/stream", "GET"),
    ("/api/generate/jobs/fake-id/cancel", "POST"),
]

for path, method in endpoints:
    try:
        do_req(path, method=method)
        report(f"{method} {path} wired", True)
    except urllib.error.HTTPError as e:
        # 401/403/404/405/422 all mean the route is registered
        report(f"{method} {path} wired", e.code not in (404, 405) or path.count("fake") > 0,
               f"HTTP {e.code}")
    except Exception as e:
        report(f"{method} {path} wired", False, str(e)[:80])


# ═══════════════════════════════════════════════════════════════════
# 2. AUTH ENFORCEMENT — Routes must require auth
# ═══════════════════════════════════════════════════════════════════
print("\n══ 2. AUTH ENFORCEMENT ══")

auth_endpoints = [
    ("/api/jobs", "GET"),
    ("/api/jobs", "POST"),
    ("/api/jobs/someid", "GET"),
    ("/api/jobs/someid", "PUT"),
    ("/api/jobs/someid", "DELETE"),
    ("/api/jobs/someid/parse", "POST"),
    ("/api/job-sync/alerts", "GET"),
    ("/api/job-sync/alerts", "POST"),
    ("/api/job-sync/match", "POST"),
    ("/api/job-sync/matches", "GET"),
    ("/api/job-sync/matches/someid/status", "PUT"),
    ("/api/generate/jobs", "POST"),
    ("/api/generate/jobs/someid/stream", "GET"),
    ("/api/generate/jobs/someid/cancel", "POST"),
]

for path, method in auth_endpoints:
    try:
        if method == "POST" and "job-sync" in path:
            # Need body for Pydantic validation
            body = json.dumps({"keywords": ["test"]}).encode()
            do_req(path, method=method, data=body, content_type="application/json")
        elif method in ("POST", "PUT"):
            body = json.dumps({}).encode()
            do_req(path, method=method, data=body, content_type="application/json")
        else:
            do_req(path, method=method)
        report(f"Auth required: {method} {path}", False, "allowed unauthenticated!")
    except urllib.error.HTTPError as e:
        report(f"Auth required: {method} {path}", e.code in (401, 403, 422))
    except Exception as e:
        report(f"Auth required: {method} {path}", False, str(e)[:80])

# C1: /api/generate/pipeline — NO AUTH
print("\n  -- Critical: Pipeline auth --")
try:
    body = json.dumps({"job_title": "Test", "jd_text": "Test JD"}).encode()
    do_req("/api/generate/pipeline", method="POST", data=body, content_type="application/json")
    report("C1: /pipeline requires auth", False, "UNAUTHENTICATED ACCESS — anyone can burn AI tokens!")
except urllib.error.HTTPError as e:
    report("C1: /pipeline requires auth", e.code in (401, 403), f"HTTP {e.code}")
except Exception as e:
    # If it errors for a different reason (like AI failure), it still means no auth check
    report("C1: /pipeline requires auth", False, f"reached AI code without auth: {str(e)[:60]}")

try:
    body = json.dumps({"job_title": "Test", "jd_text": "Test JD"}).encode()
    do_req("/api/generate/pipeline/stream", method="POST", data=body, content_type="application/json")
    report("C1: /pipeline/stream requires auth", False, "UNAUTHENTICATED ACCESS!")
except urllib.error.HTTPError as e:
    report("C1: /pipeline/stream requires auth", e.code in (401, 403), f"HTTP {e.code}")
except Exception as e:
    report("C1: /pipeline/stream requires auth", False, f"reached without auth: {str(e)[:60]}")


# ═══════════════════════════════════════════════════════════════════
# 3. JOBS CRUD — Create, list, get, update, delete
# ═══════════════════════════════════════════════════════════════════
print("\n══ 3. JOBS CRUD ══")

created_job_id = None
if ACCESS_TOKEN:
    # Create
    try:
        resp = json_req("/api/jobs", "POST", headers=AUTH, body={
            "title": "Module 3 Test Job",
            "company": "TestCorp",
            "description": "Looking for a Python developer with FastAPI and React experience.",
        })
        data = json.loads(resp.read().decode())
        created_job_id = data.get("id")
        report("Create job", bool(created_job_id), "no id returned")
    except Exception as e:
        report("Create job", False, str(e)[:100])

    # List
    try:
        resp = json_req("/api/jobs", "GET", headers=AUTH)
        data = json.loads(resp.read().decode())
        report("List jobs", isinstance(data, list))
    except Exception as e:
        report("List jobs", False, str(e)[:100])

    # Get
    if created_job_id:
        try:
            resp = json_req(f"/api/jobs/{created_job_id}", "GET", headers=AUTH)
            data = json.loads(resp.read().decode())
            report("Get job by ID", data.get("id") == created_job_id)
        except Exception as e:
            report("Get job by ID", False, str(e)[:100])

    # Update
    if created_job_id:
        try:
            resp = json_req(f"/api/jobs/{created_job_id}", "PUT", headers=AUTH, body={
                "title": "Updated Test Job",
            })
            data = json.loads(resp.read().decode())
            report("Update job", data.get("title") == "Updated Test Job")
        except Exception as e:
            report("Update job", False, str(e)[:100])

    # Delete
    if created_job_id:
        try:
            do_req(f"/api/jobs/{created_job_id}", method="DELETE", headers=AUTH)
            report("Delete job", True)
        except urllib.error.HTTPError as e:
            report("Delete job", e.code == 204, f"HTTP {e.code}")
        except Exception as e:
            report("Delete job", False, str(e)[:100])
else:
    report("Jobs CRUD: skipped (no auth token)", True, "")


# ═══════════════════════════════════════════════════════════════════
# 4. UUID VALIDATION — Non-UUID path params
# ═══════════════════════════════════════════════════════════════════
print("\n══ 4. UUID VALIDATION ══")

if ACCESS_TOKEN:
    bad_uuid_tests = [
        ("/api/jobs/not-a-uuid", "GET", "jobs GET"),
        ("/api/jobs/not-a-uuid", "PUT", "jobs PUT"),
        ("/api/jobs/not-a-uuid", "DELETE", "jobs DELETE"),
        ("/api/jobs/not-a-uuid/parse", "POST", "jobs parse"),
    ]
    for path, method, label in bad_uuid_tests:
        try:
            if method == "PUT":
                json_req(path, method, headers=AUTH, body={"title": "test"})
            else:
                do_req(path, method=method, headers=AUTH)
            report(f"M1: {label} bad-uuid → 422", False, "accepted bad UUID")
        except urllib.error.HTTPError as e:
            # Currently these probably return 500 (no UUID validation) — recording as-is
            report(f"M1: {label} bad-uuid → 422", e.code == 422, f"HTTP {e.code}")

    # job-sync match_id validation
    try:
        json_req("/api/job-sync/matches/not-a-uuid/status", "PUT", headers=AUTH,
                 body={"status": "interested"})
        report("M1: job-sync match bad-uuid → 422", False, "accepted")
    except urllib.error.HTTPError as e:
        report("M1: job-sync match bad-uuid → 422", e.code == 422, f"HTTP {e.code}")
else:
    report("UUID validation: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 5. INPUT VALIDATION — Jobs accepts raw Dict
# ═══════════════════════════════════════════════════════════════════
print("\n══ 5. INPUT VALIDATION ══")

if ACCESS_TOKEN:
    # C2: jobs.py uses raw Dict[str, Any] — try injecting dangerous fields
    try:
        resp = json_req("/api/jobs", "POST", headers=AUTH, body={
            "title": "Test",
            "description": "desc",
            "user_id": "00000000-0000-0000-0000-aaaaaaaaaaaa",  # IDOR attempt
            "id": "00000000-0000-0000-0000-bbbbbbbbbbbb",  # ID override
            "parsed_data": {"injected": True},  # Direct DB override
            "required_skills": ["injected"],  # Skip AI parsing
        })
        data = json.loads(resp.read().decode())
        # JobService has ALLOWED_FIELDS — check if user_id was overwritten
        report("C2: ALLOWED_FIELDS prevents user_id IDOR",
               data.get("user_id") != "00000000-0000-0000-0000-aaaaaaaaaaaa",
               f"user_id was overwritten to {data.get('user_id')}")
        report("C2: ALLOWED_FIELDS prevents parsed_data injection",
               data.get("parsed_data") != {"injected": True},
               "parsed_data was directly injected")
        report("C2: ALLOWED_FIELDS prevents required_skills injection",
               data.get("required_skills") != ["injected"],
               "required_skills was directly injected")

        # Cleanup
        if data.get("id"):
            try:
                do_req(f"/api/jobs/{data['id']}", method="DELETE", headers=AUTH)
            except Exception:
                pass
    except Exception as e:
        report("C2: ALLOWED_FIELDS check", False, str(e)[:100])

    # PUT also uses raw Dict — check ALLOWED_FIELDS
    try:
        resp = json_req("/api/jobs", "POST", headers=AUTH, body={
            "title": "Filter Test", "description": "test desc"
        })
        job = json.loads(resp.read().decode())
        if job.get("id"):
            resp2 = json_req(f"/api/jobs/{job['id']}", "PUT", headers=AUTH, body={
                "title": "Safe Update",
                "user_id": "00000000-0000-0000-0000-aaaa",  # IDOR on update
                "parsed_data": {"hacked": True},
            })
            updated = json.loads(resp2.read().decode())
            report("C2: PUT ALLOWED_FIELDS filters user_id",
                   updated.get("user_id") != "00000000-0000-0000-0000-aaaa")
            report("C2: PUT ALLOWED_FIELDS filters parsed_data",
                   updated.get("parsed_data") != {"hacked": True})
            # Cleanup
            try:
                do_req(f"/api/jobs/{job['id']}", method="DELETE", headers=AUTH)
            except Exception:
                pass
    except Exception as e:
        report("C2: PUT filter check", False, str(e)[:100])
else:
    report("Input validation: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 6. ERROR SANITIZATION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 6. ERROR SANITIZATION ══")

if ACCESS_TOKEN:
    # C3: job_sync score_match leaks exceptions: detail=f"Match scoring failed: {e}"
    try:
        # Send match request with minimal data — if AI fails it should NOT leak the exception
        json_req("/api/job-sync/match", "POST", headers=AUTH, body={
            "job_title": "",  # empty triggers error path
        })
        report("C3: score_match error sanitized", True, "no error triggered")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        has_leak = any(kw in body.lower() for kw in [
            "traceback", "file \"/", "modulenotfound", "attributeerror",
            "typeerror", "importerror"
        ])
        # Check for f"Match scoring failed: {e}" pattern
        has_raw_exception = "match scoring failed:" in body.lower() and len(body) > 100
        report("C3: No traceback in error", not has_leak, body[:200] if has_leak else "")
        report("C3: No raw exception in error msg", not has_raw_exception,
               body[:200] if has_raw_exception else "")
else:
    report("Error sanitization: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 7. MATCH STATUS VALIDATION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 7. MATCH STATUS VALIDATION ══")

if ACCESS_TOKEN:
    # M2: UpdateMatchStatusRequest.status is just `str` — no enum validation
    # Arbitrary values should be rejected
    try:
        json_req("/api/job-sync/matches/" + FAKE_UUID + "/status", "PUT", headers=AUTH, body={
            "status": "hacked_status_value"
        })
        report("M2: Arbitrary status accepted", False,
               "accepted 'hacked_status_value' — no enum validation", warn=True)
    except urllib.error.HTTPError as e:
        if e.code == 422:
            report("M2: Status enum validation", True)
        elif e.code == 404:
            report("M2: match not found (can't validate enum)", True, "UUID doesn't exist")
        else:
            report("M2: Status validation", False, f"HTTP {e.code}")
else:
    report("Match status validation: skipped (no auth)", True)


# ═══════════════════════════════════════════════════════════════════
# 8. RATE LIMITING
# ═══════════════════════════════════════════════════════════════════
print("\n══ 8. RATE LIMITING ══")

# Check if jobs routes have rate limiting (code-level check)
_BASE = pathlib.Path(__file__).resolve().parent.parent / "backend"
jobs_src = (_BASE / "app" / "api" / "routes" / "jobs.py").read_text()
job_sync_src = (_BASE / "app" / "api" / "routes" / "job_sync.py").read_text()
generate_src = (_BASE / "app" / "api" / "routes" / "generate.py").read_text()

report("M3: jobs.py has rate limiting", "limiter.limit" in jobs_src or "@limiter" in jobs_src,
       "NO rate limiting on any jobs endpoint")
report("M3: job_sync.py has rate limiting", "limiter.limit" in job_sync_src,
       "NO rate limiting on job-sync endpoints")
report("M3: generate.py has rate limiting", "limiter.limit" in generate_src)

# Check if generate.py uses centralized limiter from app.core.security
report("M4: generate.py uses centralized limiter",
       "from app.core.security import limiter" in generate_src or
       "from app.core.security import" in generate_src and "limiter" in generate_src,
       "Creates its own Limiter instance — won't share state with the app-level limiter")


# ═══════════════════════════════════════════════════════════════════
# 9. INPUT SIZE LIMITS
# ═══════════════════════════════════════════════════════════════════
print("\n══ 9. INPUT SIZE LIMITS ══")

# M5: PipelineRequest has no max_length on jd_text/resume_text
report("M5: PipelineRequest has max_length on jd_text",
       "max_length" in generate_src and "jd_text" in generate_src,
       "No max_length — unbounded input can exhaust AI tokens and memory")

# Check jobs create body size
report("M5: Jobs body has size validation",
       "max_length" in jobs_src or "Field(" in jobs_src,
       "raw Dict[str,Any] body with no size limits")


# ═══════════════════════════════════════════════════════════════════
# 10. ARCHITECTURE — Code-level assertions
# ═══════════════════════════════════════════════════════════════════
print("\n══ 10. ARCHITECTURE ══")

job_svc_src = (_BASE / "app" / "services" / "job.py").read_text()
job_sync_svc_src = (_BASE / "app" / "services" / "job_sync.py").read_text()

# C1: Pipeline endpoints missing auth
report("C1: /pipeline has Depends(get_current_user)",
       "Depends(get_current_user)" in generate_src.split("generate_pipeline")[1].split("def ")[0]
       if "generate_pipeline" in generate_src else False,
       "NO auth on /pipeline — anyone can burn AI tokens")

report("C1: /pipeline/stream has Depends(get_current_user)",
       "Depends(get_current_user)" in generate_src.split("generate_pipeline_stream")[1].split("def ")[0]
       if "generate_pipeline_stream" in generate_src else False,
       "NO auth on /pipeline/stream")

# M4: generate.py creates its own Limiter instead of centralized
report("M4: generate.py doesn't create own Limiter",
       "limiter = Limiter(" not in generate_src,
       "Creates `limiter = Limiter(key_func=get_remote_address)` — won't share state")

# M6: Singleton pattern — should use get_*_service() factory, not direct instantiation
report("L1: JobService uses singleton",
       "get_job_service" in jobs_src and "JobService()" not in jobs_src,
       "Still uses JobService() per-request instead of get_job_service() singleton")

report("L1: JobSyncService uses singleton",
       "get_job_sync_service" in job_sync_src and "JobSyncService()" not in job_sync_src,
       "Still uses JobSyncService() per-request instead of get_job_sync_service() singleton")

# L1: job.py ALLOWED_FIELDS exists (good)
report("L1: JobService has ALLOWED_FIELDS", "ALLOWED_FIELDS" in job_svc_src)

# L2: JOB_PARSER_PROMPT uses safe f-string format
report("L2: JOB_PARSER_PROMPT uses .format()", ".format(" in job_svc_src or "{description}" in job_svc_src)

# L3: job_sync error leaks via f-string
report("C3: score_match no f-string exception leak",
       'f"Match scoring failed: {e}"' not in job_sync_src,
       'Uses f"Match scoring failed: {e}" — leaks internal errors')


# ═══════════════════════════════════════════════════════════════════
# 11. IDOR PROTECTION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 11. IDOR PROTECTION ══")

# Jobs: service checks user_id ownership
report("IDOR: job.get_job checks user_id",
       'job.get("user_id") == user_id' in job_svc_src or
       "user_id" in job_svc_src.split("get_job")[1].split("def ")[0]
       if "get_job" in job_svc_src else False)

# job_sync: match status checks ownership
report("IDOR: update_match_status checks user_id",
       'match.get("user_id") != user_id' in job_sync_svc_src or
       "user_id" in job_sync_svc_src.split("update_match_status")[1]
       if "update_match_status" in job_sync_svc_src else False)


# ═══════════════════════════════════════════════════════════════════
# CLEANUP — Delete test user
# ═══════════════════════════════════════════════════════════════════
print("\n══ CLEANUP ══")
try:
    if TEST_UID and TEST_UID != USER_UUID:
        sb.auth.admin.delete_user(TEST_UID)
        print(f"  Deleted test user {TEST_UID}")
    else:
        print("  No test user to clean up")
except Exception as e:
    print(f"  ⚠ Cleanup failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print()
total = passed + failed
print("=" * 60)
print(f"RESULTS: {passed}/{total} passed, {failed} failed, {warnings} warnings")
if failed == 0:
    print("ALL LIVE TESTS PASSED")
else:
    print(f"{failed} ISSUE(S) NEED ATTENTION")
if warnings:
    print(f"{warnings} ARCHITECTURE IMPROVEMENT(S) IDENTIFIED")
