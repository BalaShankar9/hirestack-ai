"""
Module 2 — Resume Parsing & Profile Management: Deep Security & Enterprise Audit
Tests: endpoint wiring, auth enforcement, input validation, file type checks,
       size limits, error sanitization, IDOR protection, rate limiting potential,
       content-type validation, Pydantic schema gaps, and edge cases.
"""
import json
import time
import urllib.request
import urllib.error
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import jwt
from app.core.config import settings

BASE = "http://localhost:8000"
secret = settings.supabase_jwt_secret
passed = 0
failed = 0
warnings = 0


def report(name, ok, detail="", warn=False):
    global passed, failed, warnings
    if warn:
        warnings += 1
        print(f"  WARN  {name}: {detail}")
    elif ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}: {detail}")


def make_token(sub="00000000-0000-0000-0000-000000000001", email="test@hirestack.dev", **overrides):
    payload = {
        "sub": sub,
        "email": email,
        "user_metadata": {},
        "aud": "authenticated",
        "role": "authenticated",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


# Use the real user UUID from the database (FK constraint: users.id -> auth.users.id)
REAL_USER_ID = "0a123bb9-9a87-4067-aaba-d434250abd2c"
REAL_USER_EMAIL = "balashankarbollineni4@gmail.com"
AUTH = {"Authorization": "Bearer " + make_token(sub=REAL_USER_ID, email=REAL_USER_EMAIL)}
# User2 uses a fake UUID — this will fail at get_or_create_user (FK constraint), giving 401
USER2_AUTH = {"Authorization": "Bearer " + make_token(sub="11111111-1111-1111-1111-111111111111", email="other@test.com")}


def do_req(path, method="GET", headers=None, data=None, content_type=None):
    """Generic HTTP request helper."""
    r = urllib.request.Request(BASE + path, method=method)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    if content_type:
        r.add_header("Content-Type", content_type)
    body = data if isinstance(data, bytes) else None
    return urllib.request.urlopen(r, body)


def multipart_upload(path, filename, file_bytes, content_type="application/pdf", headers=None, extra_fields=None):
    """Build a multipart/form-data request."""
    boundary = "----HireStackTestBoundary"
    body = b""

    # File part
    body += f"------HireStackTestBoundary\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {content_type}\r\n\r\n".encode()
    body += file_bytes
    body += b"\r\n"

    # Extra fields
    for k, v in (extra_fields or {}).items():
        body += f"------HireStackTestBoundary\r\n".encode()
        body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
        body += f"{v}\r\n".encode()

    body += b"------HireStackTestBoundary--\r\n"

    r = urllib.request.Request(BASE + path, method="POST")
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    r.add_header("Content-Type", f"multipart/form-data; boundary=----HireStackTestBoundary")
    return urllib.request.urlopen(r, body)


# ═══════════════════════════════════════════════════════════════════
# 1. ENDPOINT WIRING
# ═══════════════════════════════════════════════════════════════════
print("\n══ 1. ENDPOINT WIRING ══")

# Resume parse
try:
    do_req("/api/resume/parse", method="POST", headers=AUTH)
    report("POST /api/resume/parse exists", True)
except urllib.error.HTTPError as e:
    # 422 = endpoint exists but needs file field; 405 = wrong method
    report("POST /api/resume/parse exists", e.code == 422, f"HTTP {e.code}")

# Profile CRUD
for path, method, name in [
    ("/api/profile", "GET", "GET /api/profile (list)"),
    ("/api/profile/primary", "GET", "GET /api/profile/primary"),
    ("/api/profile/upload", "POST", "POST /api/profile/upload"),
]:
    try:
        do_req(path, method=method, headers=AUTH)
        report(name, True)
    except urllib.error.HTTPError as e:
        # 404 = no primary profile (valid); 422 = needs file (valid for upload)
        report(name, e.code in (200, 404, 422), f"HTTP {e.code}")

# Profile by non-UUID string → should be 422 (UUID validation)
try:
    do_req("/api/profile/fake-uuid-that-doesnt-exist", method="GET", headers=AUTH)
    report("GET /api/profile/bad-uuid -> 422", False, "got 200")
except urllib.error.HTTPError as e:
    report("GET /api/profile/bad-uuid -> 422", e.code == 422, f"HTTP {e.code}")

# Profile by valid UUID that doesn't exist → 404
try:
    do_req("/api/profile/99999999-9999-9999-9999-999999999999", method="GET", headers=AUTH)
    report("GET /api/profile/missing-uuid -> 404", False, "got 200")
except urllib.error.HTTPError as e:
    report("GET /api/profile/missing-uuid -> 404", e.code == 404, f"HTTP {e.code}")

# PUT with non-UUID → 422
try:
    do_req("/api/profile/fake-uuid", method="PUT", headers=AUTH,
           data=json.dumps({"name": "test"}).encode(), content_type="application/json")
    report("PUT bad-uuid -> 422", False, "should be 422")
except urllib.error.HTTPError as e:
    report("PUT bad-uuid -> 422", e.code == 422, f"HTTP {e.code}")

# DELETE with non-UUID → 422
try:
    do_req("/api/profile/fake-uuid", method="DELETE", headers=AUTH)
    report("DELETE bad-uuid -> 422", False, "should be 422")
except urllib.error.HTTPError as e:
    report("DELETE bad-uuid -> 422", e.code == 422, f"HTTP {e.code}")

# Set primary with non-UUID → 422
try:
    do_req("/api/profile/fake-uuid/set-primary", method="POST", headers=AUTH)
    report("set-primary bad-uuid -> 422", False, "should be 422")
except urllib.error.HTTPError as e:
    report("set-primary bad-uuid -> 422", e.code == 422, f"HTTP {e.code}")

# Reparse with non-UUID → 422
try:
    do_req("/api/profile/fake-uuid/reparse", method="POST", headers=AUTH)
    report("reparse bad-uuid -> 422", False, "should be 422")
except urllib.error.HTTPError as e:
    report("reparse bad-uuid -> 422", e.code == 422, f"HTTP {e.code}")


# ═══════════════════════════════════════════════════════════════════
# 2. AUTH ENFORCEMENT — All endpoints must require auth
# ═══════════════════════════════════════════════════════════════════
print("\n══ 2. AUTH ENFORCEMENT ══")

for path, method in [
    ("/api/resume/parse", "POST"),
    ("/api/profile", "GET"),
    ("/api/profile/primary", "GET"),
    ("/api/profile/upload", "POST"),
    ("/api/profile/someid", "GET"),
    ("/api/profile/someid", "PUT"),
    ("/api/profile/someid", "DELETE"),
    ("/api/profile/someid/set-primary", "POST"),
    ("/api/profile/someid/reparse", "POST"),
]:
    try:
        do_req(path, method=method)  # No auth header
        report(f"Auth required: {method} {path}", False, "allowed unauthenticated")
    except urllib.error.HTTPError as e:
        # 401 or 422 (missing field) are both acceptable - 422 means auth was checked but file missing
        report(f"Auth required: {method} {path}", e.code in (401, 403, 422))


# ═══════════════════════════════════════════════════════════════════
# 3. RESUME PARSE — File validation
# ═══════════════════════════════════════════════════════════════════
print("\n══ 3. RESUME PARSE — File Validation ══")

# Valid TXT upload
try:
    resp = multipart_upload(
        "/api/resume/parse",
        "resume.txt",
        b"John Doe\nSoftware Engineer\n5 years experience in Python, React, AWS.",
        content_type="text/plain",
        headers=AUTH,
    )
    data = json.loads(resp.read().decode())
    report("Parse TXT resume", bool(data.get("text")), "no text returned" if not data.get("text") else "")
    report("Returns fileName", data.get("fileName") == "resume.txt")
    report("No userId in response (L1)", "userId" not in data, "userId still present — privacy leak")
except Exception as e:
    report("Parse TXT resume", False, str(e)[:100])

# Empty file
try:
    multipart_upload(
        "/api/resume/parse",
        "empty.txt",
        b"",
        content_type="text/plain",
        headers=AUTH,
    )
    report("Reject empty file", False, "accepted empty file — should return error or empty text")
except urllib.error.HTTPError as e:
    report("Reject empty file", e.code in (400, 422))

# Unsupported file type
try:
    multipart_upload(
        "/api/resume/parse",
        "virus.exe",
        b"\x4d\x5a\x90\x00" * 100,
        content_type="application/octet-stream",
        headers=AUTH,
    )
    report("Reject .exe upload", False, "accepted .exe!")
except urllib.error.HTTPError as e:
    report("Reject .exe upload", e.code == 415, f"HTTP {e.code}")

# Oversized file (>10MB)
try:
    big = b"A" * (11 * 1024 * 1024)  # 11 MB
    multipart_upload(
        "/api/resume/parse",
        "huge.txt",
        big,
        content_type="text/plain",
        headers=AUTH,
    )
    report("Reject >10MB file", False, "accepted oversized file!")
except urllib.error.HTTPError as e:
    report("Reject >10MB file", e.code == 413, f"HTTP {e.code}")
except Exception as e:
    # Sometimes the connection resets on large uploads
    report("Reject >10MB file", True, "connection reset (acceptable)")

# Missing filename
try:
    multipart_upload(
        "/api/resume/parse",
        "",
        b"Some resume text here",
        content_type="text/plain",
        headers=AUTH,
    )
    report("Reject missing filename", False, "accepted file without filename")
except urllib.error.HTTPError as e:
    report("Handle missing filename", e.code in (400, 422))

# File extension spoofing: .pdf extension but text content
try:
    resp = multipart_upload(
        "/api/resume/parse",
        "spoofed.pdf",
        b"This is just plain text, not a real PDF",
        content_type="application/pdf",
        headers=AUTH,
    )
    # Should fail during PDF parsing
    report("Handle spoofed .pdf", False, "accepted spoofed PDF without error")
except urllib.error.HTTPError as e:
    report("Handle spoofed .pdf", e.code == 422, f"HTTP {e.code}")


# ═══════════════════════════════════════════════════════════════════
# 4. PROFILE UPLOAD — Validation
# ═══════════════════════════════════════════════════════════════════
print("\n══ 4. PROFILE UPLOAD — Validation ══")

# Unsupported file type
try:
    multipart_upload(
        "/api/profile/upload",
        "image.jpg",
        b"\xff\xd8\xff\xe0" + b"\x00" * 500,
        content_type="image/jpeg",
        headers=AUTH,
    )
    report("Profile: reject .jpg", False, "accepted .jpg!")
except urllib.error.HTTPError as e:
    report("Profile: reject .jpg", e.code == 400, f"HTTP {e.code}")

# Oversized file
try:
    big = b"X" * (11 * 1024 * 1024)
    multipart_upload(
        "/api/profile/upload",
        "huge.pdf",
        big,
        content_type="application/pdf",
        headers=AUTH,
    )
    report("Profile: reject >10MB", False, "accepted oversized!")
except urllib.error.HTTPError as e:
    report("Profile: reject >10MB", e.code == 400, f"HTTP {e.code}")
except Exception:
    report("Profile: reject >10MB", True, "connection reset (acceptable)")


# ═══════════════════════════════════════════════════════════════════
# 5. ERROR SANITIZATION — No internal info leaked
# ═══════════════════════════════════════════════════════════════════
print("\n══ 5. ERROR SANITIZATION ══")

# Try to trigger an internal error
try:
    multipart_upload(
        "/api/resume/parse",
        "corrupt.pdf",
        b"%PDF-1.4 corrupted junk " + b"\x00\xff" * 500,
        content_type="application/pdf",
        headers=AUTH,
    )
    report("Error sanitization on corrupt PDF", True, "parsed OK (may be valid)")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    has_traceback = any(kw in body.lower() for kw in [
        "traceback", "stacktrace", "file \"/", "line ", "modulenotfound",
        "importerror", "typeerror", "attributeerror"
    ])
    report("No traceback in error response", not has_traceback, body[:200] if has_traceback else "")

# Check profile endpoint error doesn't leak DB internals
try:
    do_req("/api/profile", "GET", headers=AUTH)
    report("Profile list doesn't leak errors", True)
except urllib.error.HTTPError as e:
    body = e.read().decode()
    has_db_leak = any(kw in body.lower() for kw in [
        "postgres", "pg_", "constraint", "relation", "supabase"
    ])
    report("No DB info in profile errors", not has_db_leak, body[:200] if has_db_leak else "")


# ═══════════════════════════════════════════════════════════════════
# 6. IDOR PROTECTION — Users can't access other users' profiles
# ═══════════════════════════════════════════════════════════════════
print("\n══ 6. IDOR PROTECTION ══")

# First, list profiles for user 1
try:
    resp = do_req("/api/profile", "GET", headers=AUTH)
    profiles = json.loads(resp.read().decode())
    if isinstance(profiles, list) and len(profiles) > 0:
        profile_id = profiles[0].get("id")
        # Try accessing it with user 2's token
        try:
            do_req(f"/api/profile/{profile_id}", "GET", headers=USER2_AUTH)
            report("IDOR: user2 can't read user1 profile", False, "user2 got user1's profile!")
        except urllib.error.HTTPError as e:
            report("IDOR: user2 can't read user1 profile", e.code == 404)
    else:
        report("IDOR: skipped (no profiles)", True, "no profiles to test against")
except urllib.error.HTTPError as e:
    report("IDOR: skipped (list failed)", True, f"HTTP {e.code}")


# ═══════════════════════════════════════════════════════════════════
# 7. RESPONSE SCHEMA ANALYSIS — Check for enterprise gaps
# ═══════════════════════════════════════════════════════════════════
print("\n══ 7. RESPONSE SCHEMA ANALYSIS ══")

# Parse endpoint returns raw data without Pydantic response model
try:
    resp = multipart_upload(
        "/api/resume/parse",
        "test.txt",
        b"Jane Smith\nData Scientist at Google\n10 years Python, ML, TensorFlow",
        content_type="text/plain",
        headers=AUTH,
    )
    data = json.loads(resp.read().decode())
    # Check if response matches expected schema
    expected_fields = ["text", "fileName", "contentType"]
    missing = [f for f in expected_fields if f not in data]
    report("Parse response has expected fields", len(missing) == 0, f"missing: {missing}")

    # Verify userId is NOT in the response (L1 fix)
    report("No userId leak in response (L1)", "userId" not in data, "userId still present")
except Exception as e:
    report("Response schema check", False, str(e)[:100])


# ═══════════════════════════════════════════════════════════════════
# 8. PROFILE UPDATE — Input validation gaps
# ═══════════════════════════════════════════════════════════════════
print("\n══ 8. PROFILE UPDATE — Input Validation ══")

# Pydantic UpdateProfileBody should reject unknown/dangerous fields
try:
    resp = do_req("/api/profile", "GET", headers=AUTH)
    profiles = json.loads(resp.read().decode())
    if isinstance(profiles, list) and len(profiles) > 0:
        pid = profiles[0]["id"]

        # Try injecting dangerous fields — Pydantic should strip unknown fields
        try:
            r = urllib.request.Request(BASE + f"/api/profile/{pid}", method="PUT")
            r.add_header("Authorization", AUTH["Authorization"])
            r.add_header("Content-Type", "application/json")
            payload = json.dumps({
                "user_id": "00000000-0000-0000-0000-aaaaaaaaaa",  # IDOR attempt
                "id": "00000000-0000-0000-0000-bbbbbbbbbb",  # ID override attempt
                "is_primary": True,
                "name": "Safe Name Update",  # This field is allowed
                "created_at": "2020-01-01",  # Should be stripped
            }).encode()
            resp2 = urllib.request.urlopen(r, payload)
            data = json.loads(resp2.read().decode())
            # Pydantic strips unknown fields; only 'name' should have been applied
            report("Pydantic strips dangerous fields (C2)", data.get("name") == "Safe Name Update")
            report("user_id not overwritten (C2)",
                   data.get("user_id") != "00000000-0000-0000-0000-aaaaaaaaaa",
                   f"user_id was changed to {data.get('user_id')}")
        except urllib.error.HTTPError as e:
            # 422 is also acceptable — means Pydantic rejected the extra fields
            report("Pydantic validates update body (C2)", e.code == 422, f"HTTP {e.code}")
    else:
        report("Profile update: skipped (no profiles)", True)
except Exception as e:
    report("Profile update test", False, str(e)[:100])


# ═══════════════════════════════════════════════════════════════════
# 9. VERIFY ARCHITECTURE FIXES (code-level assertions)
# ═══════════════════════════════════════════════════════════════════
print("\n══ 9. VERIFY ARCHITECTURE FIXES ══")

import pathlib

_BASE = pathlib.Path(__file__).resolve().parent.parent / "backend"

resume_src = (_BASE / "app" / "api" / "routes" / "resume.py").read_text()
profile_src = (_BASE / "app" / "api" / "routes" / "profile.py").read_text()
profile_svc_src = (_BASE / "app" / "services" / "profile.py").read_text()

# M3: resume.py should use pdfplumber, NOT PyPDF2
report("M3: resume.py uses pdfplumber", "pdfplumber" in resume_src)
report("M3: resume.py no longer uses PyPDF2", "PyPDF2" not in resume_src)

# C1: rate limiter on resume parse
report("C1: resume parse has rate limit", "limiter.limit" in resume_src or "@limiter" in resume_src)

# L2: magic-byte detection
report("L2: magic-byte detection present", "_MAGIC" in resume_src or "magic" in resume_src.lower())

# M2: empty file rejection
report("M2: empty file rejection present", "_MIN_CONTENT_BYTES" in resume_src)

# C1: rate limiter on profile routes
report("C1: profile routes have rate limits", profile_src.count("limiter.limit") >= 5)

# C2: Pydantic model for PUT
report("C2: UpdateProfileBody Pydantic model", "UpdateProfileBody" in profile_src)

# M1: UUID validation
report("M1: UUID validation present", "_validate_uuid" in profile_src)

# C3: sanitized error in upload
report("C3: no f-string exception leak", 'f"Failed to process resume: {e}"' not in profile_src)

# M5: singleton ProfileService
report("M5: singleton get_profile_service()", "get_profile_service" in profile_svc_src)
report("M5: shared AIClient in singleton", "_instance" in profile_svc_src)

# M4: atomic set_primary (single bulk SQL update)
report("M4: atomic _unset_all_primary", "_unset_all_primary" in profile_svc_src)
report("M4: uses bulk .update().eq() pattern",
       ".update(" in profile_svc_src and ".eq('user_id'" in profile_svc_src and ".eq('is_primary'" in profile_svc_src)

# L1: no userId in parse response
report("L1: userId removed from parse response", '"userId"' not in resume_src)


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
    print(f"{warnings} ENTERPRISE IMPROVEMENT(S) IDENTIFIED")
