"""Smoke test: auth, endpoints, generation pipeline."""
import requests, json, time, sys

SUPABASE_URL = "https://dkfmcnfhvbqwsgpkgoag.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRrZm1jbmZodmJxd3NncGtnb2FnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0OTY0MjEsImV4cCI6MjA4NzA3MjQyMX0._kUDmWamD-77Pkf817W08EfRz3UxQ_Mwygpi18uEUWc"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRrZm1jbmZodmJxd3NncGtnb2FnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTQ5NjQyMSwiZXhwIjoyMDg3MDcyNDIxfQ.DEa-TJ-c-oD918I_6BA68WjoMn6_kg5g2HmrYXwSths"
BASE = "http://127.0.0.1:8000"
email = "e2etest@hirestack.dev"

# Sign in
r = requests.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
    headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
    json={"email": email, "password": "E2eTest1234!"})
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
