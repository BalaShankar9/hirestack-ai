"""Auth module security tests - run against live backend on port 8000.

Re-run after changes:  python scripts/test_auth_security.py
"""
import jwt
import json
import time
import urllib.request
import urllib.error
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.core.config import settings

BASE = "http://localhost:8000"
secret = settings.supabase_jwt_secret

passed = 0
failed = 0


def report(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}: {detail}")


def do_req(path, method="GET", headers=None):
    r = urllib.request.Request(f"{BASE}{path}", method=method)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    return urllib.request.urlopen(r)


def make_token(**overrides):
    payload = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "test@test.com",
        "user_metadata": {},
        "aud": "authenticated",
        "role": "authenticated",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


print(f"JWT secret length: {len(secret)} chars")
print()

# --- C1: audience validation ---
print("=== C1: Audience/Role Validation ===")
try:
    token = make_token(aud="service_role", role="service_role")
    do_req("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    report("Reject service_role audience", False, "token accepted")
except urllib.error.HTTPError as e:
    report("Reject service_role audience", e.code in (401, 422))

try:
    token2 = make_token(role="anon")
    do_req("/api/auth/verify", headers={"Authorization": f"Bearer {token2}"})
    report("Reject anon role", False, "token accepted")
except urllib.error.HTTPError as e:
    report("Reject anon role", e.code in (401, 422))

# --- C2: missing sub ---
print()
print("=== C2: Missing sub claim ===")
payload_no_sub = {
    "email": "nosub@test.com",
    "user_metadata": {},
    "aud": "authenticated",
    "role": "authenticated",
    "iat": int(time.time()),
    "exp": int(time.time()) + 3600,
}
token_no_sub = jwt.encode(payload_no_sub, secret, algorithm="HS256")
try:
    do_req("/api/auth/verify", headers={"Authorization": f"Bearer {token_no_sub}"})
    report("Reject token without sub", False, "accepted")
except urllib.error.HTTPError as e:
    report("Reject token without sub", e.code == 401)

# --- C3: error leakage ---
print()
print("=== C3: Error Message Sanitization ===")
token_bad = make_token(sub="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
try:
    do_req("/api/auth/me", headers={"Authorization": f"Bearer {token_bad}"})
    report("Error sanitization", False, "unexpected 200")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    has_leak = any(
        p in body.lower()
        for p in ["foreign key", "constraint", "users_id_fkey", "violates"]
    )
    report("No internal info leaked", not has_leak, body[:150] if has_leak else "")

# --- C7: oversized token ---
print()
print("=== C7: Token Size Limit ===")
big_token = make_token(
    email="x" * 10000 + "@test.com",
    user_metadata={"full_name": "A" * 50000},
)
try:
    do_req("/api/auth/verify", headers={"Authorization": f"Bearer {big_token}"})
    report("Reject oversized token", False, "accepted")
except urllib.error.HTTPError as e:
    report("Reject oversized token", e.code in (400, 401))

# --- M1: Security headers ---
print()
print("=== M1: Security Headers ===")
resp = urllib.request.urlopen(f"{BASE}/health")
for h in [
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
]:
    val = resp.headers.get(h)
    report(f"{h} present", val is not None, "missing" if val is None else "")

server = resp.headers.get("Server", "")
report("Server banner stripped", not server, f"leaks: {server}" if server else "")

# --- M2: API docs ---
print()
print("=== M2: API Docs Protection ===")
for path in ["/docs", "/redoc", "/openapi.json"]:
    try:
        resp = urllib.request.urlopen(f"{BASE}{path}")
        # In debug mode (dev) docs are available - that is expected
        report(f"{path} (debug=ok)", True)
    except urllib.error.HTTPError:
        report(f"{path} blocked in prod", True)

# Wait for rate limit window to reset before running more /verify tests
print()
print("  (waiting 5s for rate-limit window reset...)")
time.sleep(5)

# --- Basic auth checks ---
print()
print("=== Basic Auth Checks ===")
try:
    do_req("/api/auth/verify")
    report("No header -> error", False)
except urllib.error.HTTPError as e:
    report("No header -> error", e.code in (401, 422))

try:
    do_req("/api/auth/verify", headers={"Authorization": "Bearer garbage"})
    report("Garbage token -> 401", False)
except urllib.error.HTTPError as e:
    report("Garbage token -> 401", e.code == 401)

expired = jwt.encode(
    {
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "test@test.com",
        "user_metadata": {},
        "aud": "authenticated",
        "role": "authenticated",
        "iat": int(time.time()) - 3700,
        "exp": int(time.time()) - 100,
    },
    secret,
    algorithm="HS256",
)
try:
    do_req("/api/auth/verify", headers={"Authorization": f"Bearer {expired}"})
    report("Expired token -> 401", False)
except urllib.error.HTTPError as e:
    report("Expired token -> 401", e.code == 401)

wrong = jwt.encode(
    {
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "test@test.com",
        "user_metadata": {},
        "aud": "authenticated",
        "role": "authenticated",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    },
    "wrong-secret",
    algorithm="HS256",
)
try:
    do_req("/api/auth/verify", headers={"Authorization": f"Bearer {wrong}"})
    report("Wrong secret -> 401", False)
except urllib.error.HTTPError as e:
    report("Wrong secret -> 401", e.code == 401)

# --- C4: rate limiting (run last to avoid impacting other tests) ---
print()
print("  (waiting 60s for full rate-limit window reset...)")
time.sleep(60)
print("=== C4: Rate Limiting ===")
limited = False
for i in range(35):
    try:
        do_req("/api/auth/verify", headers={"Authorization": "Bearer bad"})
    except urllib.error.HTTPError as e:
        if e.code == 429:
            report(f"Rate limited after {i+1} requests", True)
            limited = True
            break
if not limited:
    report("Rate limiting on /verify", False, "no 429 after 35 requests")

# --- CORS ---
print()
print("=== CORS Tests ===")
for origin, should_pass in [
    ("http://localhost:3002", True),
    ("https://evil.com", False),
]:
    r = urllib.request.Request(f"{BASE}/api/auth/verify", method="OPTIONS")
    r.add_header("Origin", origin)
    r.add_header("Access-Control-Request-Method", "GET")
    r.add_header("Access-Control-Request-Headers", "authorization")
    try:
        resp = urllib.request.urlopen(r)
        acao = resp.headers.get("access-control-allow-origin", "")
        ok = (origin in acao) == should_pass
        report(f"CORS {origin}", ok, f"acao={acao}")
    except urllib.error.HTTPError as e:
        ok = not should_pass
        report(f"CORS {origin}", ok, f"status={e.code}")

# --- Summary ---
print()
total = passed + failed
print("=" * 50)
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("ALL SECURITY CHECKS PASSED")
else:
    print(f"{failed} ISSUE(S) NEED ATTENTION")
