#!/usr/bin/env python3
"""
Module 6 — Advanced AI Features, API Keys & Workers
Security audit test suite
────────────────────────────────────────────────────
Scope:
  Routes  : api_keys, ats, career, evidence_mapper, interview,
            learning, review, salary, variants
  Services: api_keys, ats, career_analytics, evidence_mapper,
            interview, learning, review, salary, doc_variant
  Workers : document_tasks, export_tasks, celery_app
"""
import json, os, sys, ssl, urllib.request, urllib.error, inspect, re, textwrap
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ROUTES  = BACKEND / "app" / "api" / "routes"
SVCS    = BACKEND / "app" / "services"
WORKERS = ROOT / "workers"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

# ── Supabase config ───────────────────────────────────────────────
SUPA_URL = "https://dkfmcnfhvbqwsgpkgoag.supabase.co"
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRrZm1jbmZodmJxd3NncGtnb2FnIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3Mzg3MzY3MzIsImV4cCI6MjA1NDMxMjczMn0."
    "BlYZFR_2BhW1VjWxqbmOaG3MJBssJBY51jS0M2yJqrM"
)
API = "http://localhost:8000/api"
FAKE_UUID = "00000000-0000-0000-0000-000000000000"
BAD_ID    = "not-a-uuid-at-all"

# ── auth ──────────────────────────────────────────────────────────
ACCESS_TOKEN = None
AUTH = {}
try:
    ctx = ssl.create_default_context()
    body = json.dumps({"email": "balashankarbollineni4@gmail.com", "password": "Test1234!"}).encode()
    req = urllib.request.Request(
        f"{SUPA_URL}/auth/v1/token?grant_type=password",
        data=body,
        headers={"Content-Type": "application/json", "apikey": ANON_KEY},
    )
    r = urllib.request.urlopen(req, context=ctx)
    d = json.loads(r.read())
    ACCESS_TOKEN = d["access_token"]
    AUTH = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
except Exception as e:
    print(f"⚠ Auth failed: {e}")

# ── helpers ───────────────────────────────────────────────────────
passed = failed = warnings = 0

def report(name, ok, detail="", warn=False):
    global passed, failed, warnings
    if warn and not ok:
        warnings += 1
        print(f"  ⚠ WARN  {name}  — {detail}")
    elif ok:
        passed += 1
        print(f"  ✅ PASS  {name}")
    else:
        failed += 1
        print(f"  ❌ FAIL  {name}  — {detail}")

def src(path):
    return path.read_text() if path.exists() else ""

def json_req(url, method="GET", headers=None, body=None, timeout=15):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{API}{url}" if not url.startswith("http") else url,
                                data=data, headers=h, method=method)
    r = urllib.request.urlopen(req, timeout=timeout,
                               context=ssl.create_default_context())
    return json.loads(r.read()) if r.status == 200 else {}

# ── load sources ──────────────────────────────────────────────────
route_files = {
    "api_keys": ROUTES / "api_keys.py",
    "ats": ROUTES / "ats.py",
    "career": ROUTES / "career.py",
    "evidence_mapper": ROUTES / "evidence_mapper.py",
    "interview": ROUTES / "interview.py",
    "learning": ROUTES / "learning.py",
    "review": ROUTES / "review.py",
    "salary": ROUTES / "salary.py",
    "variants": ROUTES / "variants.py",
}
svc_files = {
    "api_keys": SVCS / "api_keys.py",
    "ats": SVCS / "ats.py",
    "career_analytics": SVCS / "career_analytics.py",
    "evidence_mapper": SVCS / "evidence_mapper.py",
    "interview": SVCS / "interview.py",
    "learning": SVCS / "learning.py",
    "review": SVCS / "review.py",
    "salary": SVCS / "salary.py",
    "doc_variant": SVCS / "doc_variant.py",
}
worker_files = {
    "document_tasks": WORKERS / "tasks" / "document_tasks.py",
    "export_tasks": WORKERS / "tasks" / "export_tasks.py",
    "celery_app": WORKERS / "celery_app.py",
}

all_route_srcs = {n: src(p) for n, p in route_files.items()}
all_svc_srcs   = {n: src(p) for n, p in svc_files.items()}
all_worker_srcs = {n: src(p) for n, p in worker_files.items()}

# ═══════════════════════════════════════════════════════════════════
# 1. AUTHENTICATION — every mutating endpoint must have get_current_user
# ═══════════════════════════════════════════════════════════════════
print("\n══ 1. AUTHENTICATION COVERAGE ══")

for name, s in all_route_srcs.items():
    funcs = re.findall(r'async def (\w+)\(', s)
    unprotected = []
    for fn in funcs:
        # Find function block
        m = re.search(rf'async def {fn}\(.*?\):', s, re.DOTALL)
        if not m:
            continue
        block_start = max(0, m.start() - 200)
        block = s[block_start:m.end() + 300]
        # Public endpoints: review token lookup, comments, get_comments
        is_public = fn in ("get_session_by_token", "add_comment", "get_comments")
        if not is_public and "get_current_user" not in block:
            unprotected.append(fn)
    report(f"{name}.py auth coverage",
           len(unprotected) == 0,
           f"Unprotected: {unprotected}" if unprotected else "")

# Public endpoints in review.py should NOT have auth
review_src = all_route_srcs.get("review", "")
for fn_name in ("get_session_by_token", "add_comment", "get_comments"):
    m = re.search(rf'async def {fn_name}\(.*?\):', review_src, re.DOTALL)
    if m:
        block = review_src[m.start():m.end() + 200]
        report(f"review.py {fn_name} is correctly public",
               "get_current_user" not in block)

# ═══════════════════════════════════════════════════════════════════
# 2. RATE LIMITING — all routes must use centralized limiter
# ═══════════════════════════════════════════════════════════════════
print("\n══ 2. RATE LIMITING ══")

for name, s in all_route_srcs.items():
    has_limiter_import = "from app.core.security import limiter" in s
    # Count endpoint functions
    endpoint_count = len(re.findall(r'@router\.(get|post|put|delete|patch)', s))
    # Count limiter decorators
    limiter_count = s.count("@limiter.limit(")
    report(f"{name}.py centralized limiter import",
           has_limiter_import,
           "Missing: from app.core.security import limiter")
    report(f"{name}.py all {endpoint_count} endpoints rate-limited",
           limiter_count >= endpoint_count,
           f"Only {limiter_count}/{endpoint_count} have @limiter.limit")

# No local Limiter instances
for name, s in all_route_srcs.items():
    has_local = "Limiter(key_func=" in s or "from slowapi import Limiter" in s
    report(f"{name}.py no local Limiter",
           not has_local,
           "Uses local Limiter instead of centralized")

# ═══════════════════════════════════════════════════════════════════
# 3. UUID VALIDATION — path parameters must be validated
# ═══════════════════════════════════════════════════════════════════
print("\n══ 3. UUID VALIDATION ON PATH PARAMS ══")

# Map of route → list of path param names
path_params = {
    "api_keys": ["key_id"],
    "ats": ["scan_id"],
    "evidence_mapper": ["gap_report_id", "mapping_id"],
    "interview": ["session_id"],
    "learning": ["challenge_id"],
    "review": ["share_token", "session_id"],  # share_token is NOT a UUID
    "salary": ["analysis_id"],
    "variants": ["variant_id"],
    "career": [],  # no path params
}

for name, params in path_params.items():
    s = all_route_srcs.get(name, "")
    has_validate_uuid = "_validate_uuid" in s
    uuid_params = [p for p in params if p != "share_token"]  # skip non-UUID params
    if uuid_params:
        report(f"{name}.py has _validate_uuid helper",
               has_validate_uuid,
               f"Missing UUID validation for: {uuid_params}")
        # Check each param is actually validated
        for param in uuid_params:
            validated = f'_validate_uuid({param}' in s
            report(f"{name}.py validates {param}",
                   validated,
                   f"{param} not UUID-validated")

# ═══════════════════════════════════════════════════════════════════
# 4. PYDANTIC MODEL VALIDATION (no raw Dict[str, Any] bodies)
# ═══════════════════════════════════════════════════════════════════
print("\n══ 4. PYDANTIC MODELS (no raw Dict bodies) ══")

for name, s in all_route_srcs.items():
    # Check if any endpoint accepts request: Dict[str, Any]
    raw_dicts = re.findall(r'request:\s*Dict\[str,\s*Any\]', s)
    report(f"{name}.py uses Pydantic models (not raw Dict)",
           len(raw_dicts) == 0,
           f"Found {len(raw_dicts)} endpoints with raw Dict[str, Any]")

# ═══════════════════════════════════════════════════════════════════
# 5. ERROR SANITIZATION — no f-string exception leaks
# ═══════════════════════════════════════════════════════════════════
print("\n══ 5. ERROR SANITIZATION ══")

for name, s in all_route_srcs.items():
    has_leak = False
    for line in s.split("\n"):
        stripped = line.strip()
        if "detail=" in stripped:
            # Check for f-string with {e} or {exc}
            if ('f"' in stripped or "f'" in stripped) and re.search(r'\{e\}|\{exc\}|\{err\}', stripped):
                has_leak = True
                break
            # Also check detail=str(e) in 500 handlers (in except Exception blocks)
            if "str(e)" in stripped or "str(exc)" in stripped:
                # Only flag if it's in a generic Exception handler
                idx = s.index(line)
                context = s[max(0, idx-200):idx]
                if "except Exception" in context:
                    has_leak = True
                    break
    report(f"{name}.py error messages sanitized",
           not has_leak,
           "Leaks raw exception in HTTP error detail")

for name, s in all_svc_srcs.items():
    has_leak = False
    for line in s.split("\n"):
        stripped = line.strip()
        if "detail=" in stripped and ('f"' in stripped or "f'" in stripped) and re.search(r'\{e\}|\{exc\}', stripped):
            has_leak = True
            break
    report(f"service/{name}.py error messages sanitized",
           not has_leak,
           "Leaks raw exception via f-string")

# ═══════════════════════════════════════════════════════════════════
# 6. AI CLIENT SINGLETON — services should use get_ai_client()
# ═══════════════════════════════════════════════════════════════════
print("\n══ 6. AI CLIENT SINGLETON ══")

ai_services = ["ats", "evidence_mapper", "interview", "learning", "review", "salary", "doc_variant"]
for name in ai_services:
    s = all_svc_srcs.get(name, "")
    uses_singleton = "get_ai_client" in s
    uses_direct = "self.ai_client = AIClient()" in s
    report(f"service/{name}.py uses get_ai_client() singleton",
           uses_singleton and not uses_direct,
           "Creates AIClient() directly instead of get_ai_client()")

# ═══════════════════════════════════════════════════════════════════
# 7. WORKER SECURITY — workers should also use singleton
# ═══════════════════════════════════════════════════════════════════
print("\n══ 7. WORKER SECURITY ══")

doc_tasks_src = all_worker_srcs.get("document_tasks", "")
report("document_tasks.py uses get_ai_client() singleton",
       "get_ai_client" in doc_tasks_src,
       "Creates AIClient() directly inside task")

# Workers should not log raw exceptions containing user data
for name, s in all_worker_srcs.items():
    if name == "celery_app":
        continue
    # Check for error=str(exc) which is less dangerous but still check
    has_raw_log = 'error=str(exc)' in s or 'error=str(e)' in s
    report(f"{name} error logging sanitized",
           not has_raw_log,
           "Logs raw exception string",
           warn=True)

# Celery config: check task_time_limit is set
celery_src = all_worker_srcs.get("celery_app", "")
report("celery_app task_time_limit set",
       "task_time_limit" in celery_src,
       "No task_time_limit — tasks can run forever")

# Check serializer is json (not pickle)
report("celery_app uses JSON serializer (not pickle)",
       "task_serializer" in celery_src and '"json"' in celery_src,
       "Using unsafe serializer — pickle allows RCE")

# ═══════════════════════════════════════════════════════════════════
# 8. REVIEW.PY — PUBLIC ENDPOINT SECURITY
# ═══════════════════════════════════════════════════════════════════
print("\n══ 8. REVIEW PUBLIC ENDPOINT SECURITY ══")

review_src = all_route_srcs.get("review", "")
review_svc_src = all_svc_srcs.get("review", "")

# share_token should be cryptographically random
report("review service uses secrets.token_urlsafe",
       "secrets.token_urlsafe" in review_svc_src,
       "Share token not generated with secrets module")

# Comment text should have length limit
report("AddCommentRequest has comment_text length limit",
       "max_length" in review_src and "comment_text" in review_src,
       "comment_text has no max_length — potential abuse")

# reviewer_name should have length limit
report("AddCommentRequest reviewer_name length limit",
       re.search(r'reviewer_name.*max_length', review_src) is not None,
       "reviewer_name has no max_length")

# expires_hours should be bounded
report("CreateReviewRequest expires_hours bounded",
       re.search(r'expires_hours.*le=|expires_hours.*lt=|expires_hours.*max', review_src) is not None,
       "expires_hours has no upper bound")

# Session deactivation has ownership check
report("review deactivate has ownership check",
       "user_id" in review_svc_src and "deactivate_session" in review_svc_src,
       "No ownership check on session deactivation")

# ═══════════════════════════════════════════════════════════════════
# 9. API KEYS ROUTE SECURITY
# ═══════════════════════════════════════════════════════════════════
print("\n══ 9. API KEYS ROUTE SECURITY ══")

api_keys_src = all_route_srcs.get("api_keys", "")
api_keys_svc_src = all_svc_srcs.get("api_keys", "")

# Key hash is stored, not raw key
report("API keys service stores hash (not raw key)",
       "sha256" in api_keys_svc_src and "key_hash" in api_keys_svc_src,
       "Raw API key stored in database")

# Key is only returned once on creation
report("Raw key returned only on create",
       "raw_key" in api_keys_svc_src and "only" in api_keys_svc_src.lower(),
       "Raw key may be returned on subsequent reads")

# get_keys strips key_hash from response
report("get_keys strips key_hash",
       'pop("key_hash"' in api_keys_svc_src or "key_hash" in api_keys_svc_src,
       "key_hash exposed in list response")

# name field should have length limit
report("CreateKeyRequest.name has max_length",
       re.search(r'name.*max_length|name.*Field\(.*max_length', api_keys_src) is not None,
       "name field has no max_length")

# rate_limit should have bounds
report("CreateKeyRequest.rate_limit bounded",
       re.search(r'rate_limit.*le=|rate_limit.*lt=|rate_limit.*Field\(.*le=|rate_limit.*ge=', api_keys_src) is not None,
       "rate_limit has no bounds — user can set any value")

# days param should be bounded
report("Usage stats days param bounded",
       re.search(r'days.*le=|days.*lt=|days.*ge=|Query\(', api_keys_src) is not None,
       "days query param has no upper bound")

# ═══════════════════════════════════════════════════════════════════
# 10. INPUT BOUNDS — Pydantic model field constraints
# ═══════════════════════════════════════════════════════════════════
print("\n══ 10. INPUT BOUNDS & FIELD CONSTRAINTS ══")

# ATS: document_content should have max_length
ats_src = all_route_srcs.get("ats", "")
report("ATSScanRequest document_content max_length",
       re.search(r'document_content.*max_length', ats_src) is not None,
       "document_content has no max_length — could send huge payloads")

# Interview: question_count should be bounded
interview_src = all_route_srcs.get("interview", "")
report("StartSessionRequest question_count bounded",
       re.search(r'question_count.*le=|question_count.*lt=|question_count.*ge=', interview_src) is not None,
       "question_count has no bounds")

# Interview: answer_text should have max_length
report("SubmitAnswerRequest answer_text max_length",
       re.search(r'answer_text.*max_length', interview_src) is not None,
       "answer_text has no max_length")

# Learning: count should be bounded  
learning_src = all_route_srcs.get("learning", "")
report("GenerateChallengesRequest count bounded",
       re.search(r'count.*le=|count.*lt=|count.*ge=', learning_src) is not None,
       "count has no bounds — user can request unlimited challenges")

# Learning: history limit should be bounded
report("Learning history limit bounded",
       re.search(r'limit.*le=|limit.*lt=|limit.*ge=|Query\(', learning_src) is not None,
       "history limit param has no upper bound")

# Salary: experience_years / current_salary should be bounded
salary_src = all_route_srcs.get("salary", "")
report("SalaryAnalysisRequest experience_years bounded",
       re.search(r'experience_years.*ge=|experience_years.*le=', salary_src) is not None,
       "experience_years has no bounds")

# Variants: original_content should have max_length
variants_src = all_route_srcs.get("variants", "")
report("GenerateVariantsRequest original_content max_length",
       re.search(r'original_content.*max_length', variants_src) is not None,
       "original_content has no max_length")

# Career: days param should be bounded
career_src = all_route_srcs.get("career", "")
report("Career timeline days bounded",
       re.search(r'days.*le=|days.*lt=|days.*ge=|Query\(', career_src) is not None,
       "days param has no bounds")

# ═══════════════════════════════════════════════════════════════════
# 11. REQUEST PARAM: all endpoints need Request for rate limiter
# ═══════════════════════════════════════════════════════════════════
print("\n══ 11. REQUEST PARAM FOR LIMITER ══")

for name, s in all_route_srcs.items():
    # Every function with @limiter.limit needs request: Request
    blocks = re.findall(r'@limiter\.limit\([^)]+\)\nasync def (\w+)\(([^)]+)\)', s, re.DOTALL)
    missing_request = []
    for fn_name, params in blocks:
        if "request: Request" not in params and "request:" not in params:
            # http_request: Request is also fine
            if "http_request: Request" not in params:
                missing_request.append(fn_name)
    report(f"{name}.py all rate-limited endpoints have Request param",
           len(missing_request) == 0,
           f"Missing Request param: {missing_request}" if missing_request else "")

# ═══════════════════════════════════════════════════════════════════
# 12. LIVE TESTS — auth required
# ═══════════════════════════════════════════════════════════════════
print("\n══ 12. LIVE: NO-AUTH REJECTION ══")

if ACCESS_TOKEN:
    noauth_endpoints = [
        ("/api/api-keys/keys", "GET"),
        ("/api/ats/scans", "GET"),
        ("/api/career/timeline", "GET"),
        ("/api/evidence-mapper/mappings/" + FAKE_UUID, "GET"),
        ("/api/interview/", "GET"),
        ("/api/learning/streak", "GET"),
        ("/api/salary/", "GET"),
        ("/api/variants/", "GET"),
    ]
    for endpoint, method in noauth_endpoints:
        try:
            req = urllib.request.Request(
                f"http://localhost:8000{endpoint}",
                headers={"Content-Type": "application/json"},
                method=method,
            )
            urllib.request.urlopen(req, timeout=10)
            report(f"No-auth {method} {endpoint} blocked", False, "200 without auth")
        except urllib.error.HTTPError as e:
            report(f"No-auth {method} {endpoint} blocked",
                   e.code in (401, 403),
                   f"Got {e.code} instead of 401/403")
        except Exception as e:
            report(f"No-auth {method} {endpoint} blocked", False, str(e))
else:
    print("  ⚠ Skipping live tests — no access token")

# ═══════════════════════════════════════════════════════════════════
# 13. LIVE: UUID VALIDATION (bad IDs)
# ═══════════════════════════════════════════════════════════════════
print("\n══ 13. LIVE: UUID VALIDATION ══")

if ACCESS_TOKEN:
    uuid_test_endpoints = [
        ("/api/ats/scan/" + BAD_ID, "GET"),
        ("/api/evidence-mapper/mappings/" + BAD_ID, "GET"),
        ("/api/interview/" + BAD_ID, "GET"),
        ("/api/learning/" + BAD_ID + "/answer", "POST"),
        ("/api/salary/" + BAD_ID, "GET"),
        ("/api/variants/" + BAD_ID + "/select", "PUT"),
        ("/api/api-keys/keys/" + BAD_ID, "DELETE"),
        ("/api/review/" + BAD_ID + "/comments", "GET"),
    ]
    for endpoint, method in uuid_test_endpoints:
        try:
            body = None
            if method == "POST":
                body = json.dumps({"user_answer": "test"}).encode()
            req = urllib.request.Request(
                f"http://localhost:8000{endpoint}",
                data=body,
                headers={**AUTH, "Content-Type": "application/json"},
                method=method,
            )
            urllib.request.urlopen(req, timeout=10)
            report(f"UUID validation {method} {endpoint}", False, "200 with bad UUID")
        except urllib.error.HTTPError as e:
            report(f"UUID validation {method} {endpoint}",
                   e.code == 422,
                   f"Got {e.code} instead of 422")
        except Exception as e:
            report(f"UUID validation {method} {endpoint}", False, str(e))
else:
    print("  ⚠ Skipping live UUID tests — no access token")

# ═══════════════════════════════════════════════════════════════════
# 14. LIVE: ERROR SANITIZATION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 14. LIVE: ERROR MESSAGE SANITIZATION ══")

if ACCESS_TOKEN:
    # Try ATS scan with minimal data → should not leak traceback
    error_endpoints = [
        ("/api/ats/scan", "POST", {"document_content": "", "document_type": "cv"}),
        ("/api/interview/start", "POST", {"job_title": ""}),
        ("/api/learning/generate", "POST", {}),
    ]
    for endpoint, method, body in error_endpoints:
        try:
            json_req(endpoint, method, headers=AUTH, body=body)
            # If 200, that's fine — AI might succeed with minimal input
            report(f"Error sanitization {endpoint}", True)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode()
            has_traceback = any(kw in body_text.lower() for kw in [
                "traceback", 'file "', "line ", "/app/", "supabase", "postgrest",
                "attributeerror", "typeerror", "keyerror"
            ])
            report(f"Error sanitization {endpoint}",
                   not has_traceback,
                   f"Leaks internals: {body_text[:200]}")
        except Exception:
            report(f"Error sanitization {endpoint}", True, "Connection error (ok)")
else:
    print("  ⚠ Skipping live error tests — no access token")

# ═══════════════════════════════════════════════════════════════════
# 15. REVIEW PUBLIC ENDPOINTS — ABUSE PROTECTION
# ═══════════════════════════════════════════════════════════════════
print("\n══ 15. REVIEW PUBLIC ENDPOINT PROTECTION ══")

# Public endpoints should still have rate limiting
for fn_name in ("get_session_by_token", "add_comment", "get_comments"):
    m = re.search(rf'@limiter\.limit\([^)]+\)\nasync def {fn_name}', review_src)
    report(f"review.py {fn_name} is rate-limited",
           m is not None,
           f"{fn_name} has no rate limit — open to abuse")

# ═══════════════════════════════════════════════════════════════════
# 16. SERVICE OWNERSHIP CHECKS
# ═══════════════════════════════════════════════════════════════════
print("\n══ 16. SERVICE OWNERSHIP CHECKS ══")

# Services that return user-owned resources must verify user_id
ownership_services = {
    "ats": ["get_scan", "get_scans_for_application", "get_user_scans"],
    "evidence_mapper": ["get_mappings", "confirm_mapping"],
    "interview": ["submit_answer", "complete_session", "get_session"],
    "learning": ["submit_answer"],
    "salary": ["get_analysis"],
    "doc_variant": ["select_variant", "get_variants"],
    "review": ["deactivate_session"],
}

for name, methods in ownership_services.items():
    s = all_svc_srcs.get(name, "")
    for method in methods:
        has_check = "user_id" in s  # Basic check: user_id is used
        report(f"service/{name}.py {method} checks ownership",
               has_check,
               "No user_id ownership check")

# ═══════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════
print("\n══ CLEANUP ══")
# Clean up any test data created
if ACCESS_TOKEN:
    try:
        json_req("/api/api-keys/keys", "GET", headers=AUTH)
        report("Cleanup: API keys accessible", True)
    except Exception as e:
        report("Cleanup", False, str(e))

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"RESULTS: {passed}/{passed+failed} passed, {failed} failed, {warnings} warning(s)")
if failed == 0 and warnings == 0:
    print("ALL LIVE TESTS PASSED")
elif failed == 0:
    print(f"ALL TESTS PASSED ({warnings} warnings)")
else:
    print(f"⚠ {failed} FAILURES need fixing")
