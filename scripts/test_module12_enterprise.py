#!/usr/bin/env python3
"""
Module 12 — Enterprise Modules: Candidates & Organizations
Smoke tests for the candidates pipeline & org management routes.
────────────────────────────────────────────────────────────────
Scope:
  Routes  : candidates, orgs
  Services: candidate, org
"""
import json, os, re, sys, time, ssl, urllib.request, urllib.error
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ROUTES  = BACKEND / "app" / "api" / "routes"
SVCS    = BACKEND / "app" / "services"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

# ── Supabase config ───────────────────────────────────────────────
SUPA_URL = os.getenv("SUPABASE_URL", "")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
API = os.getenv("API_BASE", "http://127.0.0.1:8000/api")
FAKE_UUID = "00000000-0000-0000-0000-000000000000"

# ── auth ──────────────────────────────────────────────────────────
ACCESS_TOKEN = None
AUTH = {}
try:
    ctx = ssl.create_default_context()
    body = json.dumps({"email": "e2etest@hirestack.dev", "password": "E2eTest1234!"}).encode()
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
    full_url = f"{API}{url}" if not url.startswith("http") else url
    req = urllib.request.Request(full_url, data=data, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context())
        raw = r.read()
        if not raw:
            return (r.status, {})
        try:
            return (r.status, json.loads(raw))
        except Exception:
            return (r.status, {
                "content_type": r.headers.get("Content-Type", ""),
                "raw": raw[:200].decode("utf-8", errors="ignore"),
            })
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return (e.code, json.loads(raw) if raw else {})
        except Exception:
            return (e.code, {
                "content_type": e.headers.get("Content-Type", "") if e.headers else "",
                "raw": raw[:200].decode("utf-8", errors="ignore") if raw else "",
            })
    except Exception as e:
        return (0, {"error": str(e)})


# ── load sources ──────────────────────────────────────────────────
candidates_src = src(ROUTES / "candidates.py")
orgs_src = src(ROUTES / "orgs.py")
candidates_svc_src = src(SVCS / "candidate.py")
orgs_svc_src = src(SVCS / "org.py")

candidates_endpoint_count = len(re.findall(r"@router\.(get|post|put|delete|patch)", candidates_src))
orgs_endpoint_count = len(re.findall(r"@router\.(get|post|put|delete|patch)", orgs_src))
candidates_auth_refs = candidates_src.count("get_current_user")
orgs_auth_refs = orgs_src.count("get_current_user")


# ═══════════════════════════════════════════════════════════════════
# 1. CODE STRUCTURE CHECKS
# ═══════════════════════════════════════════════════════════════════
print("\n─── 1. Code Structure ────────────────────────────────────────")

report("candidates route file exists", bool(candidates_src))
report("orgs route file exists", bool(orgs_src))
report("candidates service exists", bool(candidates_svc_src))
report("orgs service exists", bool(orgs_svc_src))

# Auth dependency checks
report("candidates: all routes require auth",
    candidates_auth_refs >= candidates_endpoint_count,
    f"Found {candidates_auth_refs} auth refs for {candidates_endpoint_count} endpoints")
report("orgs: all routes require auth",
    orgs_auth_refs >= orgs_endpoint_count,
    f"Found {orgs_auth_refs} auth refs for {orgs_endpoint_count} endpoints")

# Rate limiting
report("candidates: rate limited", "limiter.limit" in candidates_src)
report("orgs: rate limited", "limiter.limit" in orgs_src)

# Input validation
report("candidates: uses pydantic models",
       "BaseModel" in candidates_src and "CreateCandidateRequest" in candidates_src)
report("orgs: uses pydantic models",
       "BaseModel" in orgs_src and "CreateOrgRequest" in orgs_src)


# ═══════════════════════════════════════════════════════════════════
# 2. AUTH ENFORCEMENT (live)
# ═══════════════════════════════════════════════════════════════════
print("\n─── 2. Auth Enforcement ──────────────────────────────────────")

for name, path, method in [
    ("GET /candidates (no auth)", "/candidates", "GET"),
    ("POST /candidates (no auth)", "/candidates", "POST"),
    ("GET /candidates/stats (no auth)", "/candidates/stats", "GET"),
    ("GET /orgs (no auth)", "/orgs", "GET"),
    ("POST /orgs (no auth)", "/orgs", "POST"),
]:
    status_code, _ = json_req(path, method=method, body={"name": "x"} if method == "POST" else None)
    report(name, status_code in (401, 403), f"got {status_code}")


# ═══════════════════════════════════════════════════════════════════
# 3. ORGANIZATIONS CRUD (live)
# ═══════════════════════════════════════════════════════════════════
print("\n─── 3. Organizations CRUD ───────────────────────────────────")

org_id = None
created_org_id = None
run_suffix = str(int(time.time()))
org_slug = f"e2e-smoke-{run_suffix}"
if AUTH:
    # Create org
    st, data = json_req("/orgs", "POST", AUTH, {"name": f"E2E Smoke Org {run_suffix}", "slug": org_slug})
    report("create org", st in (200, 201), f"status={st}")
    if st in (200, 201):
        org_id = data.get("id")
        created_org_id = org_id

    # List orgs
    st, data = json_req("/orgs", "GET", AUTH)
    report("list orgs", st == 200 and isinstance(data, list), f"status={st}")

    if org_id:
        # Get org by ID
        st, data = json_req(f"/orgs/{org_id}", "GET", AUTH)
        report("get org by ID", st == 200 and data.get("id") == org_id, f"status={st}")

        # Update org
        st, data = json_req(f"/orgs/{org_id}", "PUT", AUTH, {"name": "E2E Updated Org"})
        report("update org name", st == 200 and data.get("name") == "E2E Updated Org", f"status={st}")

        # List members
        st, data = json_req(f"/orgs/{org_id}/members", "GET", AUTH)
        report("list org members", st == 200 and isinstance(data, list), f"status={st}")

        # Audit logs
        st, data = json_req(f"/orgs/{org_id}/audit", "GET", AUTH)
        report("get org audit logs", st == 200 and isinstance(data, list), f"status={st}")

        # Usage snapshot
        st, data = json_req(f"/orgs/{org_id}/usage", "GET", AUTH)
        report("get org usage", st == 200 and isinstance(data, dict) and "usage" in data, f"status={st}")

        # Change nonexistent member role
        st, _ = json_req(f"/orgs/{org_id}/members/{FAKE_UUID}", "PUT", AUTH, {"role": "member"})
        report("change nonexistent member role → 404", st == 404, f"got {st}")

        # Remove nonexistent member
        st, _ = json_req(f"/orgs/{org_id}/members/{FAKE_UUID}", "DELETE", AUTH)
        report("remove nonexistent member → 404", st == 404, f"got {st}")

        # Invite member on missing org
        st, _ = json_req(f"/orgs/{FAKE_UUID}/members", "POST", AUTH, {
            "email": f"invite+{run_suffix}@example.com",
            "role": "member",
        })
        report("invite member on nonexistent org → 403/404", st in (403, 404), f"got {st}")

    # Invalid invitation token
    st, _ = json_req("/orgs/invitations/accept?token=invalid-smoke-token", "POST", AUTH)
    report("accept invalid org invitation → 404", st == 404, f"got {st}")

    # 404 on fake org
    st, _ = json_req(f"/orgs/{FAKE_UUID}", "GET", AUTH)
    report("get nonexistent org → 403/404", st in (403, 404), f"got {st}")
else:
    report("org CRUD tests", False, "auth failed — skipping", warn=True)


# ═══════════════════════════════════════════════════════════════════
# 4. CANDIDATES PIPELINE (live)
# ═══════════════════════════════════════════════════════════════════
print("\n─── 4. Candidates Pipeline ──────────────────────────────────")

candidate_id = None
if AUTH and org_id:
    # Create candidate
    st, data = json_req("/candidates", "POST", AUTH, {
        "name": "Smoke Test Candidate",
        "email": f"smoke-candidate+{run_suffix}@example.com",
        "pipeline_stage": "sourced",
        "tags": ["test", "smoke"],
    })
    report("create candidate", st in (200, 201), f"status={st}")
    if st in (200, 201):
        candidate_id = data.get("id")

    # List candidates
    st, data = json_req("/candidates", "GET", AUTH)
    report("list candidates", st == 200 and isinstance(data, list), f"status={st}")

    # Pipeline stats
    st, data = json_req("/candidates/stats", "GET", AUTH)
    report("pipeline stats", st == 200 and isinstance(data, dict) and "total" in data, f"status={st}")

    if candidate_id:
        # Get candidate
        st, data = json_req(f"/candidates/{candidate_id}", "GET", AUTH)
        report("get candidate by ID", st == 200, f"status={st}")

        # Update candidate
        st, data = json_req(f"/candidates/{candidate_id}", "PUT", AUTH, {"location": "London"})
        report("update candidate", st == 200, f"status={st}")

        # Move stage
        st, data = json_req(f"/candidates/{candidate_id}/move", "POST", AUTH, {"stage": "screened"})
        report("move candidate to screened", st == 200 and data.get("pipeline_stage") == "screened", f"status={st}")

        # Delete candidate
        st, _ = json_req(f"/candidates/{candidate_id}", "DELETE", AUTH)
        report("delete candidate", st in (200, 204), f"status={st}")

    # 404 on fake candidate
    st, _ = json_req(f"/candidates/{FAKE_UUID}", "GET", AUTH)
    report("get nonexistent candidate → 404", st == 404, f"got {st}")
elif not AUTH:
    report("candidate pipeline tests", False, "auth failed — skipping", warn=True)
elif not org_id:
    report("candidate pipeline tests", False, "no org — skipping", warn=True)


# ═══════════════════════════════════════════════════════════════════
# 5. CLEANUP — Delete test org if we created it
# ═══════════════════════════════════════════════════════════════════
print("\n─── 5. Cleanup ──────────────────────────────────────────────")

if AUTH and created_org_id:
    st, _ = json_req(f"/orgs/{created_org_id}", "DELETE", AUTH)
    report("delete test org", st in (200, 204), f"status={st}")


# ═══════════════════════════════════════════════════════════════════
# 6. BONUS ROUTES (missing coverage)
# ═══════════════════════════════════════════════════════════════════
print("\n─── 6. Bonus Routes ─────────────────────────────────────────")

if AUTH:
    # Export DOCX route
    st, _ = json_req("/export/docx", "POST", AUTH, {"content": "<p>test</p>", "filename": "test"})
    report("POST /export/docx", 0 < st < 500, f"status={st}", warn=True)

    # Consultant coach route
    st, _ = json_req("/consultant/coach", "POST", AUTH, {"app_id": FAKE_UUID, "question": "test"})
    report("POST /consultant/coach", 0 < st < 500, f"status={st}", warn=True)

    # Analytics daily briefing
    st, _ = json_req("/analytics/daily-briefing", "GET", AUTH)
    report("GET /analytics/daily-briefing", 0 < st < 500, f"status={st}", warn=True)


# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'═' * 60}")
print(f" Module 12 — Enterprise Modules")
print(f" PASS={passed}  FAIL={failed}  WARN={warnings}")
print(f"{'═' * 60}")
sys.exit(1 if failed else 0)
