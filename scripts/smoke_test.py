"""Smoke test: auth, endpoints, generation pipeline.

Reads ALL credentials from environment — nothing about the target
project is hardcoded. Required env vars (script exits 2 with a clear
message if any are missing):

    SUPABASE_URL                 e.g. https://<ref>.supabase.co
    SUPABASE_ANON_KEY            anon JWT for sign-in
    SUPABASE_SERVICE_ROLE_KEY    service-role JWT for direct REST writes
    SMOKE_TEST_EMAIL             test account email
    SMOKE_TEST_PASSWORD          test account password

Optional:
    SMOKE_TEST_BASE_URL          backend base URL (default http://127.0.0.1:8000)

Security: never commit real credentials here. The CI secret-scanner
(see tests/test_no_hardcoded_secrets.py) blocks any JWT-shaped string
in tracked source files.
"""
import os
import requests, json, time, sys

_REQUIRED = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SMOKE_TEST_EMAIL",
    "SMOKE_TEST_PASSWORD",
)
_missing = [k for k in _REQUIRED if not os.environ.get(k)]
if _missing:
    print("ERROR: smoke_test.py requires the following env vars:", file=sys.stderr)
    for k in _missing:
        print(f"  - {k}", file=sys.stderr)
    print("\nDo NOT add credentials to this file — set them in your shell", file=sys.stderr)
    print("or via a .env file outside source control.", file=sys.stderr)
    sys.exit(2)

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BASE = os.environ.get("SMOKE_TEST_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
email = os.environ["SMOKE_TEST_EMAIL"]
_password = os.environ["SMOKE_TEST_PASSWORD"]

# Sign in
r = requests.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
    headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
    json={"email": email, "password": _password})
if r.status_code != 200:
    print(f"Sign-in failed: {r.status_code}")
    sys.exit(1)
token = r.json()["access_token"]
uid = r.json()["user"]["id"]
h = {"Authorization": f"Bearer {token}"}
print(f"✓ Authenticated as {email} (uid={uid[:12]}...)")

# 1) Quick endpoint tests
print("\n=== Endpoint Smoke Test ===")
tests = []
def test(method, path, data=None):
    try:
        resp = requests.request(method, f"{BASE}{path}", headers=h, json=data, timeout=15)
        ok = resp.status_code < 500
        sym = "✓" if ok else "✗"
        tests.append((ok, f"{method} {path}", resp.status_code))
        print(f"  {sym} {method} {path}: {resp.status_code}")
    except Exception as e:
        tests.append((False, f"{method} {path}", 0))
        print(f"  ✗ {method} {path}: {e}")

test("GET", "/api/auth/me")
test("GET", "/api/profile/primary")
test("GET", "/api/jobs")
test("GET", "/api/billing/status")
test("GET", "/api/analytics/activity")

passed = sum(1 for ok, *_ in tests if ok)
print(f"\nEndpoints: {passed}/{len(tests)} passed")

# 2) Create application directly via Supabase (like the frontend does)
print("\n=== Generation Pipeline Test ===")
print("Creating test application via Supabase...")

sb_headers = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}
app_row = {
    "user_id": uid,
    "title": "Backend Engineer at SmokeTestCo",
    "status": "active",
    "confirmed_facts": {
        "company": "SmokeTestCo",
        "jobTitle": "Backend Engineer",
        "jdText": "We are looking for a Backend Engineer with experience in Python, FastAPI, and PostgreSQL. Must have experience with cloud services (AWS/GCP), CI/CD pipelines, and strong problem-solving skills. 3+ years experience required.",
    },
}
app_r = requests.post(
    f"{SUPABASE_URL}/rest/v1/applications",
    headers=sb_headers, json=app_row)
if app_r.status_code not in (200, 201):
    print(f"✗ Create application failed: {app_r.status_code} {app_r.text[:200]}")
    sys.exit(1)
app = app_r.json()
if isinstance(app, list):
    app = app[0]
app_id = app["id"]
print(f"  ✓ Application created: {app_id}")

# 3) Start generation job
print("\nStarting generation job...")
job_r = requests.post(f"{BASE}/api/generate/jobs",
    headers=h,
    json={"application_id": app_id},
    timeout=15)
if job_r.status_code not in (200, 201):
    print(f"✗ Job creation failed: {job_r.status_code} {job_r.text[:200]}")
    sys.exit(1)
job = job_r.json()
job_id = job.get("job_id") or job.get("id")
print(f"  ✓ Job created: {job_id}")

# 4) Poll job status via Supabase directly (backend only exposes SSE stream)
print("\nPolling job progress via Supabase (max 5 min)...")
start = time.time()
last_phase = ""
last_pct = -1
while time.time() - start < 300:
    time.sleep(5)
    try:
        poll_r = requests.get(
            f"{SUPABASE_URL}/rest/v1/generation_jobs?id=eq.{job_id}&select=*",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            timeout=10)
        if poll_r.status_code != 200 or not poll_r.json():
            print(f"  ✗ Poll failed: {poll_r.status_code}")
            continue
        j = poll_r.json()[0]
        status = j.get("status", "unknown")
        phase = j.get("current_phase", "?")
        pct = j.get("progress", 0)

        if phase != last_phase or abs(pct - last_pct) >= 5:
            elapsed = int(time.time() - start)
            print(f"  [{elapsed}s] {status} | {phase} | {pct}%")
            last_phase = phase
            last_pct = pct

        if status in ("succeeded", "completed", "failed", "cancelled"):
            break
    except Exception as e:
        print(f"  ✗ Poll error: {e}")

elapsed = int(time.time() - start)
final_r = requests.get(
    f"{SUPABASE_URL}/rest/v1/generation_jobs?id=eq.{job_id}&select=*",
    headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
    timeout=10)
final = final_r.json()[0] if final_r.json() else {}
final_status = final.get("status", "unknown")
print(f"\n{'='*50}")
print(f"FINAL: status={final_status}, phase={final.get('current_phase')}, progress={final.get('progress')}%")
print(f"Time: {elapsed}s")

# 5) Check events
events_r = requests.get(
    f"{SUPABASE_URL}/rest/v1/generation_job_events?job_id=eq.{job_id}&select=*&order=sequence_no",
    headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
    timeout=10)
if events_r.status_code == 200:
    evts = events_r.json()
    print(f"Events: {len(evts)} total")
    for ev in evts[-5:]:
        payload = ev.get("payload") or {}
        print(f"  - {ev.get('event_name','?')}: {payload.get('message','')[:80]}")

if final_status in ("succeeded", "completed"):
    print("\n✓✓✓ GENERATION PIPELINE FULLY COMPLETED ✓✓✓")
elif final_status == "failed":
    print(f"\n✗ Generation FAILED: {final.get('error','unknown')}")
else:
    print(f"\n⏳ Still running after {elapsed}s — may need more time")
