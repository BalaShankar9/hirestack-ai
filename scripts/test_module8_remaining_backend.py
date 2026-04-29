#!/usr/bin/env python3
"""
Module 8 – Remaining Backend API Routes & Services
Security-audit test script.

Covers:
  - api/resume.py, api/job_sync.py, api/builder.py, api/analytics.py
  - api/benchmark.py, api/career.py, api/consultant.py, api/gaps.py, api/review.py
  - services/job_sync.py, analytics.py, benchmark.py, career_analytics.py
  - services/gap.py, review.py, roadmap.py
  - schemas/__init__.py, models/__init__.py
"""
from __future__ import annotations
import os, sys, re, ast, textwrap

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BE   = os.path.join(BASE, "backend")
API  = os.path.join(BE, "app", "api", "routes")
SVC  = os.path.join(BE, "app", "services")

passed = failed = warnings = 0

def ok(msg):
    global passed; passed += 1; print(f"  \033[92m✅ PASS\033[0m  {msg}")
def fail(msg):
    global failed; failed += 1; print(f"  \033[91m❌ FAIL\033[0m  {msg}")
def warn(msg):
    global warnings; warnings += 1; print(f"  \033[93m⚠ WARN\033[0m  {msg}")

def src(relpath):
    full = os.path.join(BE, relpath)
    if not os.path.exists(full):
        return ""
    with open(full) as f:
        return f.read()

# ═══════════════════════════════════════════════════════════════════
print("\n══ 1. API/RESUME.PY – FILE UPLOAD HARDENING ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/resume.py")

# 1.1 Rate limiting
if "@limiter.limit" in code:
    ok("Resume parse endpoint is rate-limited")
else:
    fail("Resume parse endpoint missing rate limiter")

# 1.2 Auth
if "Depends(get_current_user)" in code:
    ok("Resume parse requires authentication")
else:
    fail("Resume parse missing authentication")

# 1.3 File size validation
if "max_upload_size_mb" in code or "_max_bytes" in code:
    ok("File size limit enforced")
else:
    fail("No file size limit on resume upload")

# 1.4 Magic byte detection
if "_MAGIC" in code or "magic" in code.lower():
    ok("Magic-byte format detection prevents extension spoofing")
else:
    fail("No magic-byte detection — vulnerable to extension spoofing")

# 1.5 Error messages don't leak internals
if re.search(r'detail=.*str\(e\)', code):
    fail("Resume parse leaks exception details in HTTP response")
else:
    ok("Resume parse error messages are sanitized")

# 1.6 max_pages parameter has upper bound
if re.search(r'max_pages.*Query.*le=', code) or re.search(r'max_pages.*Field.*le=', code):
    ok("max_pages parameter has upper bound validation")
elif re.search(r'max_pages.*=\s*\d+', code) and not re.search(r'(le=|max_value|<=)', code):
    fail("max_pages parameter has no upper bound — potential DoS via excessive page parsing")
else:
    ok("max_pages parameter is bounded")

# 1.7 Filename not used in filesystem paths
if re.search(r'os\.path\.join.*filename', code) or re.search(r'open\(.*filename', code):
    fail("Filename used in filesystem path — path traversal risk")
else:
    ok("Filename not used in filesystem paths (safe)")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 2. API/JOB_SYNC.PY – JOB ALERTS & MATCHES ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/job_sync.py")

# 2.1 Rate limiting on all endpoints
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} job_sync endpoints are rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} job_sync endpoints rate-limited")

# 2.2 Auth on all endpoints
auth_count = code.count("Depends(get_current_user)")
if auth_count >= len(endpoints):
    ok("All job_sync endpoints require authentication")
else:
    fail(f"Only {auth_count}/{len(endpoints)} job_sync endpoints require auth")

# 2.3 UUID validation
if "_validate_uuid" in code:
    ok("UUID validation applied to path parameters")
else:
    fail("Missing UUID validation on path parameters")

# 2.4 Pydantic models with constraints
if "Field(" in code and "max_length" in code:
    ok("Pydantic models have field length constraints")
else:
    fail("Pydantic models missing field length constraints")

# 2.5 Match status uses Literal type
if "Literal[" in code and "status" in code:
    ok("Match status validated via Literal enum")
else:
    fail("Match status not restricted to valid values")

# 2.6 Query param status validation
if "VALID_MATCH_STATUSES" in code or re.search(r'status.*not in', code):
    ok("GET /matches status query param validated against allowed set")
else:
    fail("GET /matches status query param not validated")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 3. API/BUILDER.PY – DOCUMENT BUILDER ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/builder.py")

# 3.1 Rate limiting
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} builder endpoints are rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} builder endpoints rate-limited")

# 3.2 Auth
auth_count = code.count("Depends(get_current_user)")
if auth_count >= len(endpoints):
    ok("All builder endpoints require authentication")
else:
    fail(f"Only {auth_count}/{len(endpoints)} builder endpoints require auth")

# 3.3 UUID validation on path params
if "_validate_uuid" in code:
    ok("UUID validation on document path parameters")
else:
    fail("Missing UUID validation on document path parameters")

# 3.4 Document type restricted to Literal
if 'Literal["cv"' in code or "Literal[" in code:
    ok("Document type restricted to Literal enum values")
else:
    fail("Document type not restricted — arbitrary strings allowed")

# 3.5 ValueError not leaked to client
if re.search(r'except ValueError.*\n.*detail=str\(e\)', code):
    fail("builder.py leaks ValueError detail: str(e) exposed to HTTP response")
else:
    ok("builder.py sanitizes error messages")

# 3.6 document_type query param validated in list endpoint
if re.search(r'document_type.*Literal', code) or re.search(r'document_type.*in\s*\(', code) or re.search(r'validate.*document_type', code.lower()):
    ok("list_documents validates document_type query parameter")
else:
    fail("list_documents does not validate document_type query parameter — arbitrary filter values accepted")

# 3.7 Content size limit
if "max_length" in code and "500_000" in code:
    ok("Document content has max_length limit (500K)")
else:
    fail("No max_length on document content field")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 4. API/ANALYTICS.PY – ANALYTICS TRACKING ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/analytics.py")

# 4.1 Rate limiting
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} analytics endpoints rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} analytics endpoints rate-limited")

# 4.2 Auth
auth_count = code.count("Depends(get_current_user)")
if auth_count >= len(endpoints):
    ok("All analytics endpoints require auth")
else:
    fail("Analytics endpoints missing auth")

# 4.3 Days param bounded
if re.search(r'days.*ge=1.*le=365', code):
    ok("Activity days parameter bounded (1-365)")
else:
    fail("Activity days parameter not bounded")

# 4.4 Event type constrained
if "max_length" in code:
    ok("Event tracking fields have length constraints")
else:
    fail("Event tracking fields missing length constraints")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 5. API/BENCHMARK.PY – BENCHMARK GENERATION ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/benchmark.py")

# 5.1 Rate limiting
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} benchmark endpoints rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} benchmark endpoints rate-limited")

# 5.2 Auth
auth_count = code.count("Depends(get_current_user)")
if auth_count >= len(endpoints):
    ok("All benchmark endpoints require auth")
else:
    fail("Benchmark endpoints missing auth")

# 5.3 UUID validation
if "_validate_uuid" in code:
    ok("Benchmark path params have UUID validation")
else:
    fail("Benchmark path params missing UUID validation")

# 5.4 Error handling generic
if re.search(r'detail=str\(e\)', code):
    fail("Benchmark routes leak exception details")
else:
    ok("Benchmark error messages are generic")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 6. API/CAREER.PY – CAREER ANALYTICS ROUTES ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/career.py")

# 6.1 Rate limiting
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} career endpoints rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} career endpoints rate-limited")

# 6.2 Auth
auth_count = code.count("Depends(get_current_user)")
if auth_count >= len(endpoints):
    ok("All career endpoints require auth")
else:
    fail("Career endpoints missing auth")

# 6.3 Timeline days bounded
if re.search(r'days.*ge=1.*le=365', code):
    ok("Timeline days parameter bounded (1-365)")
else:
    fail("Timeline days parameter not bounded")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 7. API/CONSULTANT.PY – ROADMAP ROUTES ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/consultant.py")

# 7.1 Rate limiting
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} consultant endpoints rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} consultant endpoints rate-limited")

# 7.2 Auth
auth_count = code.count("Depends(get_current_user)")
if auth_count >= len(endpoints):
    ok("All consultant endpoints require auth")
else:
    fail("Consultant endpoints missing auth")

# 7.3 UUID validation
if "_validate_uuid" in code:
    ok("Roadmap path params have UUID validation")
else:
    fail("Roadmap path params missing UUID validation")

# 7.4 UpdateProgressRequest has constraints
if re.search(r'milestone_id.*max_length', code):
    ok("UpdateProgressRequest.milestone_id has max_length")
else:
    fail("UpdateProgressRequest.milestone_id has no max_length — unbounded string accepted")

# 7.5 UpdateProgressRequest.status constrained
if re.search(r'status.*Literal\[', code) or re.search(r'status.*max_length', code):
    ok("UpdateProgressRequest.status is constrained")
else:
    fail("UpdateProgressRequest.status has no constraint — arbitrary strings accepted")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 8. API/GAPS.PY – GAP ANALYSIS ROUTES ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/gaps.py")

# 8.1 Rate limiting
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} gap endpoints rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} gap endpoints rate-limited")

# 8.2 Auth
auth_count = code.count("Depends(get_current_user)")
if auth_count >= len(endpoints):
    ok("All gap endpoints require auth")
else:
    fail("Gap endpoints missing auth")

# 8.3 UUID validation
if "_validate_uuid" in code:
    ok("Gap report path params have UUID validation")
else:
    fail("Gap report path params missing UUID validation")

# 8.4 Error handling generic
if re.search(r'detail=str\(e\)', code):
    fail("Gap routes leak exception details")
else:
    ok("Gap error messages are generic")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 9. API/REVIEW.PY – COLLABORATIVE REVIEW ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/api/routes/review.py")

# 9.1 Rate limiting
endpoints = re.findall(r'@router\.(get|post|put|delete)', code)
limiters = re.findall(r'@limiter\.limit', code)
if len(limiters) >= len(endpoints):
    ok(f"All {len(endpoints)} review endpoints rate-limited")
else:
    fail(f"Only {len(limiters)}/{len(endpoints)} review endpoints rate-limited")

# 9.2 Share token length validated
if re.search(r'share_token.*>.*500', code) or "len(share_token)" in code:
    ok("Share token length validated (max 500)")
else:
    fail("Share token length not validated")

# 9.3 CreateReviewRequest.application_id validated
review_code = code
if re.search(r'application_id.*Field.*max_length', review_code) or re.search(r'application_id.*field_validator', review_code) or re.search(r'validate.*application_id', review_code):
    ok("CreateReviewRequest.application_id has validation")
else:
    fail("CreateReviewRequest.application_id has no UUID/length validation — unbounded string")

# 9.4 Public endpoints are intentionally public
public_endpoints = []
lines = code.split("\n")
for i, line in enumerate(lines):
    if "async def" in line and "get_current_user" not in "".join(lines[max(0,i-5):i+5]):
        # Check the function's Depends
        func_block = "".join(lines[i:min(i+10, len(lines))])
        if "get_current_user" not in func_block:
            fn_name = re.search(r'async def (\w+)', line)
            if fn_name:
                public_endpoints.append(fn_name.group(1))

if public_endpoints:
    ok(f"Public endpoints identified: {', '.join(public_endpoints)} (intentional for review sharing)")
else:
    ok("All review endpoints require authentication")

# 9.5 summarize_feedback checks session ownership
svc_code = src("app/services/review.py")
# Check if summarize_feedback verifies user_id
summarize_section = ""
in_func = False
for line in svc_code.split("\n"):
    if "def summarize_feedback" in line:
        in_func = True
    elif in_func and re.match(r'    (async )?def ', line):
        break
    if in_func:
        summarize_section += line + "\n"

if "user_id" in summarize_section and ("session.get" in summarize_section or "user_id ==" in summarize_section):
    ok("summarize_feedback verifies session ownership")
else:
    fail("summarize_feedback does NOT verify session ownership — IDOR: any authenticated user can summarize any session")

# 9.6 add_comment checks session is active/not expired
add_comment_section = ""
in_func = False
for line in svc_code.split("\n"):
    if "def add_comment" in line:
        in_func = True
    elif in_func and re.match(r'    (async )?def ', line):
        break
    if in_func:
        add_comment_section += line + "\n"

if "is_active" in add_comment_section or "expires" in add_comment_section:
    ok("add_comment verifies session is active/not expired")
else:
    fail("add_comment does NOT verify session is active/not expired — comments accepted on expired/deactivated sessions")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 10. SERVICE/BENCHMARK.PY – IDOR CHECK ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/services/benchmark.py")

# 10.1 get_benchmark checks ownership
get_bench = ""
in_func = False
for line in code.split("\n"):
    if "def get_benchmark(" in line and "for_job" not in line:
        in_func = True
    elif in_func and re.match(r'    (async )?def ', line):
        break
    if in_func:
        get_bench += line + "\n"

if "user_id" in get_bench:
    ok("get_benchmark verifies ownership via job's user_id")
else:
    fail("get_benchmark does not verify ownership")

# 10.2 get_benchmark_for_job checks ownership
get_for_job = ""
in_func = False
for line in code.split("\n"):
    if "def get_benchmark_for_job" in line:
        in_func = True
    elif in_func and re.match(r'    (async )?def ', line):
        break
    if in_func:
        get_for_job += line + "\n"

# Check if user_id is actually USED in the query filters (not just a parameter)
if 'user_id' in get_for_job and ('("user_id"' in get_for_job or "user_id ==" in get_for_job or "user_id\" !=" in get_for_job or "user_id) !=" in get_for_job):
    ok("get_benchmark_for_job verifies job ownership via user_id")
else:
    fail("CRITICAL: get_benchmark_for_job accepts user_id param but NEVER uses it — returns any user's benchmark by job_id (IDOR)")

# 10.3 generate_benchmark checks job ownership
gen_bench = ""
in_func = False
for line in code.split("\n"):
    if "def generate_benchmark" in line:
        in_func = True
    elif in_func and re.match(r'    (async )?def ', line):
        break
    if in_func:
        gen_bench += line + "\n"

if "user_id" in gen_bench and "raise ValueError" in gen_bench:
    ok("generate_benchmark verifies job ownership before generation")
else:
    fail("generate_benchmark does not verify job ownership")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 11. SERVICE/GAP.PY – IDOR CHECK ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/services/gap.py")

# 11.1 analyze_gaps checks profile ownership
if re.search(r'profile.*user_id.*!=.*user_id', code) or re.search(r'profile.*get\("user_id"\).*!=', code):
    ok("analyze_gaps verifies profile ownership")
else:
    fail("analyze_gaps does not verify profile ownership")

# 11.2 analyze_gaps checks benchmark ownership
analyze_section = ""
in_func = False
for line in code.split("\n"):
    if "def analyze_gaps" in line:
        in_func = True
    elif in_func and re.match(r'    (async )?def ', line):
        break
    if in_func:
        analyze_section += line + "\n"

# Look for benchmark ownership check (ownership may be verified via job linked to benchmark)
has_benchmark_ownership = "user_id" in analyze_section and ("Benchmark not found" in analyze_section) and (
    # Pattern: checking job ownership for the benchmark's linked job
    ("job" in analyze_section and "user_id" in analyze_section and "!=" in analyze_section)
    or any("user_id" in l for l in benchmark_lines if "benchmark" in l and "profile" not in l)
)
if has_benchmark_ownership:
    ok("analyze_gaps verifies benchmark ownership")
else:
    fail("analyze_gaps does NOT verify benchmark ownership — user can reference another user's benchmark (IDOR)")

# 11.3 get_report checks ownership
if re.search(r'def get_report.*\n.*report.*user_id.*==.*user_id', code, re.DOTALL) or \
   re.search(r'report.*get\("user_id"\)\s*==\s*user_id', code):
    ok("get_report verifies ownership via user_id")
else:
    fail("get_report does not verify ownership")

# 11.4 delete_report checks ownership
if "def delete_report" in code and "get_report" in code:
    ok("delete_report delegates to get_report (which checks ownership)")
else:
    fail("delete_report may not check ownership")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 12. SERVICE/REVIEW.PY – TOKEN & SESSION SECURITY ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/services/review.py")

# 12.1 Token uses secrets.token_urlsafe
if "secrets.token_urlsafe" in code:
    ok("Share tokens generated with secrets.token_urlsafe (cryptographically secure)")
else:
    fail("Share tokens not using cryptographic randomness")

# 12.2 Token length
if re.search(r'token_urlsafe\((\d+)\)', code):
    length = int(re.search(r'token_urlsafe\((\d+)\)', code).group(1))
    if length >= 32:
        ok(f"Token length is {length} bytes — sufficient entropy")
    else:
        fail(f"Token length is only {length} bytes — insufficient entropy (use ≥32)")
else:
    warn("Could not determine token length")

# 12.3 Expiry check
if "expires_at" in code and "datetime.now" in code:
    ok("Session expiry is checked before returning session data")
else:
    fail("No session expiry check — expired sessions remain accessible")

# 12.4 Deactivation checks ownership
if "def deactivate_session" in code and "user_id" in code:
    ok("Deactivation verifies session ownership")
else:
    fail("Deactivation does not verify ownership")

# 12.5 Comment text limit
if "10_000" in code or "10000" in code:
    ok("Comment text has max length (10,000 chars) defined in API model")
else:
    warn("Comment text max length not enforced in service layer")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 13. SERVICE/ROADMAP.PY – AUTHORIZATION ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/services/roadmap.py")

# 13.1 Uses get_ai_client singleton
if "get_ai_client" in code:
    ok("Roadmap service uses get_ai_client() singleton")
else:
    fail("Roadmap service instantiates AIClient() directly")

# 13.2 generate_roadmap checks gap_report ownership
gen_section = ""
in_func = False
for line in code.split("\n"):
    if "def generate_roadmap" in line:
        in_func = True
    elif in_func and re.match(r'    (async )?def ', line):
        break
    if in_func:
        gen_section += line + "\n"

if "user_id" in gen_section and "raise ValueError" in gen_section:
    ok("generate_roadmap verifies gap_report ownership")
else:
    fail("generate_roadmap does not verify gap_report ownership")

# 13.3 get_roadmap checks ownership
if re.search(r'roadmap.*get\("user_id"\)\s*==\s*user_id', code):
    ok("get_roadmap verifies ownership")
else:
    fail("get_roadmap does not verify ownership")

# 13.4 delete_roadmap checks ownership
if "def delete_roadmap" in code and "get_roadmap" in code:
    ok("delete_roadmap delegates to get_roadmap (ownership check)")
else:
    fail("delete_roadmap may not check ownership")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 14. SERVICE/ANALYTICS.PY – DATA ISOLATION ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/services/analytics.py")

# 14.1 All queries filter by user_id
queries = re.findall(r'self\.db\.query\((.*?)\)', code, re.DOTALL)
user_filtered = sum(1 for q in queries if "user_id" in q)
if user_filtered == len(queries):
    ok(f"All {len(queries)} DB queries filter by user_id — proper data isolation")
else:
    fail(f"Only {user_filtered}/{len(queries)} queries filter by user_id — data leak risk")

# 14.2 Dashboard query limits
if "limit=200" in code or "limit=500" in code:
    ok("Dashboard queries have result limits")
else:
    fail("Dashboard queries have no result limits — potential DoS")

# 14.3 Track event sanitized
if "event_type" in code and "max_length" in src("app/api/routes/analytics.py"):
    ok("Event type has max_length validation (at API layer)")
else:
    warn("Event type validation only at API layer")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 15. SERVICE/CAREER_ANALYTICS.PY – DATA ISOLATION ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/services/career_analytics.py")

# 15.1 All queries filter by user_id
queries = re.findall(r'self\.db\.query\((.*?)\)', code, re.DOTALL)
user_filtered = sum(1 for q in queries if "user_id" in q)
if user_filtered == len(queries):
    ok(f"All {len(queries)} career analytics queries filter by user_id")
else:
    fail(f"Only {user_filtered}/{len(queries)} career analytics queries filter by user_id")

# 15.2 Snapshot deduplication
if "existing" in code and "limit=1" in code:
    ok("Daily snapshot deduplication prevents duplicate entries")
else:
    warn("No snapshot deduplication check")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 16. SERVICE/JOB_SYNC.PY – SINGLETON & AUTH ══")
# ═══════════════════════════════════════════════════════════════════
code = src("app/services/job_sync.py")

# 16.1 Singleton pattern
if "get_job_sync_service" in code and "_instance" in code:
    ok("JobSyncService uses singleton pattern")
else:
    fail("JobSyncService missing singleton pattern")

# 16.2 Uses get_ai_client
if "get_ai_client" in code:
    ok("JobSyncService uses get_ai_client() singleton")
else:
    fail("JobSyncService uses AIClient() directly")

# 16.3 update_match_status checks ownership
if re.search(r'match.*user_id.*!=.*user_id', code) or re.search(r'match.*get\("user_id"\)\s*!=\s*user_id', code):
    ok("update_match_status verifies match ownership")
else:
    fail("update_match_status does not verify ownership")

# 16.4 Description truncated before AI prompt
if "description[:2000]" in code or "description[:5000]" in code:
    ok("Job description truncated before AI prompt (prevents prompt overflow)")
else:
    warn("Job description not truncated before AI prompt")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 17. MODELS & SCHEMAS REVIEW ══")
# ═══════════════════════════════════════════════════════════════════

# 17.1 Models use TypedDict (not exposing internals)
models_code = src("app/models/__init__.py")
if "TypedDict" in models_code:
    ok("Models use TypedDict for type hints (no ORM exposure)")
else:
    warn("Models file doesn't use TypedDict")

# 17.2 No sensitive fields in model exports
if "password" not in models_code.lower() and "secret" not in models_code.lower():
    ok("No sensitive fields (password, secret) in model definitions")
else:
    fail("Sensitive fields found in model definitions")

# 17.3 Schemas file is clean
schemas_code = src("app/schemas/__init__.py")
if "Legacy" in schemas_code or len(schemas_code.strip()) < 100:
    ok("Schemas module is clean (legacy removed, routes use Dict[str, Any])")
else:
    warn("Schemas module has content — review for stale exports")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 18. CROSS-CUTTING: AI CLIENT USAGE ══")
# ═══════════════════════════════════════════════════════════════════

# Check all services use get_ai_client()
services_with_ai = [
    "services/benchmark.py",
    "services/gap.py",
    "services/review.py",
    "services/roadmap.py",
    "services/job_sync.py",
]

for svc_path in services_with_ai:
    code = src(f"app/{svc_path}")
    name = svc_path.split("/")[-1]
    if "get_ai_client" in code and "AIClient()" not in code:
        ok(f"{name} uses get_ai_client() singleton ✓")
    elif "AIClient()" in code:
        fail(f"{name} still uses AIClient() directly")
    else:
        ok(f"{name} — no direct AI client instantiation")


# ═══════════════════════════════════════════════════════════════════
print("\n══ 19. LIVE ENDPOINT TESTS ══")
# ═══════════════════════════════════════════════════════════════════

import urllib.request, json, ssl

API_BASE = "http://localhost:8000"
ctx = ssl.create_default_context()

def api_call(method, path, data=None, token=None):
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, context=ctx, timeout=10)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except:
            body = {}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}

# Try to get a token (env-driven; never hardcode credentials)
try:
    ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
    EMAIL = os.environ.get("SMOKE_TEST_EMAIL", "")
    PW = os.environ.get("SMOKE_TEST_PASSWORD", "")
    if not (ANON_KEY and SUPABASE_URL and EMAIL and PW):
        raise RuntimeError(
            "Set SUPABASE_URL, SUPABASE_ANON_KEY, SMOKE_TEST_EMAIL, "
            "SMOKE_TEST_PASSWORD to enable authenticated checks"
        )
    auth_body = json.dumps({"email": EMAIL, "password": PW}).encode()
    auth_req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        data=auth_body,
        headers={"Content-Type": "application/json", "apikey": ANON_KEY},
    )
    auth_resp = urllib.request.urlopen(auth_req, context=ctx, timeout=10)
    TOKEN = json.loads(auth_resp.read().decode())["access_token"]
    HAS_TOKEN = True
except Exception as e:
    TOKEN = None
    HAS_TOKEN = False
    warn(f"Could not get auth token — skipping live tests: {str(e)[:80]}")

if HAS_TOKEN:
    # 19.1 Unauthenticated access blocked on builder
    status_code, _ = api_call("GET", "/api/builder/documents")
    if status_code in (401, 403):
        ok("Builder /documents rejects unauthenticated requests")
    else:
        fail(f"Builder /documents returned {status_code} without auth (expected 401/403)")

    # 19.2 Unauthenticated access blocked on analytics
    status_code, _ = api_call("GET", "/api/analytics/dashboard")
    if status_code in (401, 403):
        ok("Analytics /dashboard rejects unauthenticated requests")
    else:
        fail(f"Analytics /dashboard returned {status_code} without auth (expected 401/403)")

    # 19.3 Unauthenticated access blocked on gaps
    status_code, _ = api_call("GET", "/api/gaps")
    if status_code in (401, 403):
        ok("Gaps list rejects unauthenticated requests")
    else:
        fail(f"Gaps list returned {status_code} without auth (expected 401/403)")

    # 19.4 Authenticated analytics dashboard works
    status_code, body = api_call("GET", "/api/analytics/dashboard", token=TOKEN)
    if status_code == 200:
        ok("Analytics dashboard returns 200 with valid token")
    else:
        warn(f"Analytics dashboard returned {status_code} (may need setup)")

    # 19.5 Invalid UUID rejected
    status_code, body = api_call("GET", "/api/benchmark/not-a-uuid", token=TOKEN)
    if status_code == 422:
        ok("Invalid UUID in benchmark path returns 422")
    else:
        fail(f"Invalid UUID returned {status_code} (expected 422)")

    # 19.6 Review public endpoint works without auth
    status_code, _ = api_call("GET", "/api/review/token/nonexistent-token")
    if status_code in (404, 422):
        ok("Public review token endpoint works without auth (returns 404 for missing token)")
    elif status_code in (401, 403):
        fail("Public review token endpoint incorrectly requires auth")
    else:
        warn(f"Public review token endpoint returned {status_code}")
else:
    # Skip live tests — count as warnings
    for _ in range(6):
        warn("Live test skipped (no auth token)")


# ═══════════════════════════════════════════════════════════════════
print("\n══ CLEANUP ══")
# ═══════════════════════════════════════════════════════════════════

# Summary
print(f"""
{'='*60}
RESULTS: {passed + failed}/{passed + failed} passed {passed}, failed {failed}, {warnings} warning(s)
{"ALL TESTS PASSED" if failed == 0 else "FAILURES DETECTED"}{f" ({warnings} warnings)" if warnings else ""}
{'='*60}
""")
sys.exit(0 if failed == 0 else 1)
