"""Quick auth security test - no rate-limit wait."""
import jwt, json, time, urllib.request, urllib.error, sys, os

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
        print("  PASS  " + name)
    else:
        failed += 1
        print("  FAIL  " + name + ": " + detail)


def do_req(path, method="GET", headers=None):
    r = urllib.request.Request(BASE + path, method=method)
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


print("C1: Audience/Role Validation")
try:
    t = make_token(aud="service_role", role="service_role")
    do_req("/api/auth/verify", headers={"Authorization": "Bearer " + t})
    report("Reject service_role", False, "accepted")
except urllib.error.HTTPError as e:
    report("Reject service_role", e.code in (401, 422))

print("C2: Missing sub")
t2 = jwt.encode({"email": "x@x.com", "user_metadata": {}, "aud": "authenticated", "role": "authenticated", "iat": int(time.time()), "exp": int(time.time()) + 3600}, secret, algorithm="HS256")
try:
    do_req("/api/auth/verify", headers={"Authorization": "Bearer " + t2})
    report("Reject no-sub", False, "accepted")
except urllib.error.HTTPError as e:
    report("Reject no-sub", e.code == 401)

print("C3: Error leakage")
try:
    do_req("/api/auth/me", headers={"Authorization": "Bearer " + make_token(sub="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")})
    report("Sanitized errors", False, "unexpected 200")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    has_leak = "foreign key" in body.lower() or "constraint" in body.lower()
    report("No internal info leaked", not has_leak, body[:120] if has_leak else "")

print("C7: Oversized token")
big = make_token(email="x" * 10000 + "@t.com", user_metadata={"n": "A" * 50000})
try:
    do_req("/api/auth/verify", headers={"Authorization": "Bearer " + big})
    report("Reject big token", False, "accepted")
except urllib.error.HTTPError as e:
    report("Reject big token", e.code in (400, 401))

print("M1: Security Headers")
resp = urllib.request.urlopen(BASE + "/health")
for h in ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"]:
    report(h, resp.headers.get(h) is not None, "missing")
report("No Server banner", not resp.headers.get("Server", ""), resp.headers.get("Server", ""))

print("Basic Auth Checks")
try:
    do_req("/api/auth/verify")
    report("No header", False, "200")
except urllib.error.HTTPError as e:
    report("No header -> error", e.code in (401, 422))

try:
    do_req("/api/auth/verify", headers={"Authorization": "Bearer garbage"})
    report("Garbage token", False, "200")
except urllib.error.HTTPError as e:
    report("Garbage -> 401", e.code == 401)

expired = jwt.encode({"sub": "00000000-0000-0000-0000-000000000001", "email": "t@t.com", "user_metadata": {}, "aud": "authenticated", "role": "authenticated", "iat": int(time.time()) - 3700, "exp": int(time.time()) - 100}, secret, algorithm="HS256")
try:
    do_req("/api/auth/verify", headers={"Authorization": "Bearer " + expired})
    report("Expired", False, "200")
except urllib.error.HTTPError as e:
    report("Expired -> 401", e.code == 401)

wrong = jwt.encode({"sub": "00000000-0000-0000-0000-000000000001", "email": "t@t.com", "user_metadata": {}, "aud": "authenticated", "role": "authenticated", "iat": int(time.time()), "exp": int(time.time()) + 3600}, "wrong-secret", algorithm="HS256")
try:
    do_req("/api/auth/verify", headers={"Authorization": "Bearer " + wrong})
    report("Wrong secret", False, "200")
except urllib.error.HTTPError as e:
    report("Wrong secret -> 401", e.code == 401)

print("CORS")
for origin, should_pass in [("http://localhost:3002", True), ("https://evil.com", False)]:
    r = urllib.request.Request(BASE + "/api/auth/verify", method="OPTIONS")
    r.add_header("Origin", origin)
    r.add_header("Access-Control-Request-Method", "GET")
    r.add_header("Access-Control-Request-Headers", "authorization")
    try:
        resp = urllib.request.urlopen(r)
        acao = resp.headers.get("access-control-allow-origin", "")
        report("CORS " + origin, (origin in acao) == should_pass)
    except urllib.error.HTTPError as e:
        report("CORS " + origin, not should_pass)

print()
total = passed + failed
print("=" * 50)
print("RESULTS: %d/%d passed, %d failed" % (passed, total, failed))
if failed == 0:
    print("ALL SECURITY CHECKS PASSED")
else:
    print("%d ISSUE(S) NEED ATTENTION" % failed)
