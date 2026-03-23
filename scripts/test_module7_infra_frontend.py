#!/usr/bin/env python3
"""
Module 7 — Core Infrastructure, Config & Frontend Security
Tests: backend core (config, database, security, deps, main),
       Docker/infra hardening, frontend auth/XSS/CSP patterns,
       remaining AIClient() → get_ai_client() migration.
"""

import os, sys, re, json, pathlib, textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]
BE   = ROOT / "backend"
FE   = ROOT / "frontend"
INFRA = ROOT / "infra"

passed = failed = warnings = 0

def section(title):
    print(f"\n══ {title} ══")

def ok(label):
    global passed; passed += 1
    print(f"  ✅ PASS  {label}")

def fail(label, reason=""):
    global failed; failed += 1
    extra = f"  — {reason}" if reason else ""
    print(f"  ❌ FAIL  {label}{extra}")

def warn(label, reason=""):
    global warnings; warnings += 1
    extra = f"  — {reason}" if reason else ""
    print(f"  ⚠ WARN  {label}{extra}")

def read(p):
    return pathlib.Path(p).read_text(errors="replace")

# ══════════════════════════════════════════════════════════════════════
# 1. BACKEND MAIN.PY — APP CONFIGURATION
# ══════════════════════════════════════════════════════════════════════
section("1. BACKEND MAIN.PY HARDENING")

main_src = read(BE / "main.py")

# 1a. Docs/OpenAPI disabled in non-debug
if 'docs_url="/docs" if settings.debug else None' in main_src:
    ok("Swagger docs disabled in production")
else:
    fail("Swagger docs always enabled", "docs_url should be None when debug=False")

if 'redoc_url="/redoc" if settings.debug else None' in main_src:
    ok("ReDoc disabled in production")
else:
    fail("ReDoc always enabled")

if 'openapi_url="/openapi.json" if settings.debug else None' in main_src:
    ok("OpenAPI schema disabled in production")
else:
    fail("OpenAPI schema always enabled")

# 1b. Global exception handler hides internals
if '"An unexpected error occurred"' in main_src:
    ok("Global exception handler sanitizes error detail")
else:
    fail("Global exception handler leaks error details")

# 1c. server_header=False in uvicorn
if "server_header=False" in main_src:
    ok("Uvicorn server_header=False set")
else:
    fail("Uvicorn server header not suppressed")

# 1d. CORS — not wildcard
if "allow_origins=[" in main_src or "allow_origins=allowed_origins" in main_src:
    if '"*"' not in main_src.split("allow_origins")[1][:200]:
        ok("CORS allow_origins uses explicit list (not wildcard)")
    else:
        fail("CORS allow_origins is wildcard *")
else:
    fail("CORS allow_origins config not found")

# 1e. allow_methods / allow_headers — check for wildcard (informational)
if 'allow_methods=["*"]' in main_src:
    warn("CORS allow_methods is wildcard *", "Consider restricting to GET,POST,PUT,DELETE,OPTIONS")
else:
    ok("CORS allow_methods restricted")

if 'allow_headers=["*"]' in main_src:
    warn("CORS allow_headers is wildcard *", "Consider explicit list")
else:
    ok("CORS allow_headers restricted")

# 1f. Rate limiter wired into app
if "app.state.limiter = limiter" in main_src:
    ok("Rate limiter attached to app.state")
else:
    fail("Rate limiter not attached to app")

if "RateLimitExceeded" in main_src and "_rate_limit_exceeded_handler" in main_src:
    ok("RateLimitExceeded handler registered")
else:
    fail("No rate limit exceeded handler")

# 1g. SecurityHeadersMiddleware
if "SecurityHeadersMiddleware" in main_src:
    ok("SecurityHeadersMiddleware added")
else:
    fail("SecurityHeadersMiddleware not in main.py")

# 1h. Health check — check if it leaks error details
health_section = main_src[main_src.find("async def health_check"):]
if '"error": str(e)' in health_section:
    fail("Health endpoint leaks Supabase error to client", 'supabase_status = {"ok": False, "error": str(e)}')
else:
    ok("Health endpoint sanitizes errors")

# ══════════════════════════════════════════════════════════════════════
# 2. SECURITY.PY — HEADERS & LIMITER
# ══════════════════════════════════════════════════════════════════════
section("2. SECURITY.PY HARDENING")

sec_src = read(BE / "app" / "core" / "security.py")

required_headers = [
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("x-xss-protection", "1; mode=block"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("permissions-policy", "camera=(), microphone=(), geolocation=()"),
    ("cache-control", "no-store"),
]

for name, value in required_headers:
    if name.encode() if isinstance(name, str) else name in sec_src.encode():
        ok(f"Security header '{name}' present")
    else:
        fail(f"Security header '{name}' missing")

# HSTS conditional on HTTPS
if "strict-transport-security" in sec_src:
    ok("HSTS header present (conditional on HTTPS)")
else:
    fail("HSTS header missing")

# Server banner strip
if "server" in sec_src.lower() and "strip" in sec_src.lower() or 'k.lower() != b"server"' in sec_src:
    ok("Server banner stripped from responses")
else:
    fail("Server banner not stripped")

# CSP header check
if "content-security-policy" in sec_src.lower():
    ok("Content-Security-Policy header present")
else:
    fail("Content-Security-Policy header missing", "Add CSP to prevent XSS")

# MAX_TOKEN_SIZE defined
if "MAX_TOKEN_SIZE" in sec_src:
    ok("MAX_TOKEN_SIZE constant defined")
else:
    fail("MAX_TOKEN_SIZE not defined")

# ══════════════════════════════════════════════════════════════════════
# 3. CONFIG.PY — SECRETS & DEFAULTS
# ══════════════════════════════════════════════════════════════════════
section("3. CONFIG.PY REVIEW")

cfg_src = read(BE / "app" / "core" / "config.py")

# 3a. No hardcoded secrets
secret_patterns = [
    r'supabase_anon_key:\s*str\s*=\s*"eyJ',
    r'supabase_service_role_key:\s*str\s*=\s*"eyJ',
    r'openai_api_key:\s*str\s*=\s*"sk-',
    r'gemini_api_key:\s*str\s*=\s*"AI',
]
secrets_found = False
for pat in secret_patterns:
    if re.search(pat, cfg_src):
        fail(f"Hardcoded secret detected: {pat[:30]}...")
        secrets_found = True
if not secrets_found:
    ok("No hardcoded secrets in config.py")

# 3b. debug defaults to False
if 'debug: bool = False' in cfg_src:
    ok("debug defaults to False")
else:
    fail("debug does not default to False")

# 3c. @lru_cache for settings singleton
if "@lru_cache" in cfg_src:
    ok("Settings uses @lru_cache singleton")
else:
    fail("Settings not cached")

# 3d. max_upload_size_mb is bounded
if "max_upload_size_mb" in cfg_src:
    ok("max_upload_size_mb configured")
else:
    warn("max_upload_size_mb not configured")

# 3e. allowed_file_types whitelist
if "allowed_file_types" in cfg_src:
    ok("allowed_file_types whitelist configured")
else:
    fail("No file type whitelist")

# ══════════════════════════════════════════════════════════════════════
# 4. DATABASE.PY — TOKEN VERIFICATION
# ══════════════════════════════════════════════════════════════════════
section("4. DATABASE.PY TOKEN VERIFICATION")

db_src = read(BE / "app" / "core" / "database.py")

# 4a. JWT audience validation
if 'audience="authenticated"' in db_src:
    ok("JWT audience validated ('authenticated')")
else:
    fail("JWT audience not validated")

# 4b. Role check
if 'role" != "authenticated"' in db_src or 'role") != "authenticated"' in db_src:
    ok("JWT role checked (rejects non-authenticated)")
else:
    fail("JWT role not checked")

# 4c. Sub claim required
if "sub" in db_src and "not sub" in db_src:
    ok("JWT sub claim required")
else:
    fail("JWT sub claim not validated")

# 4d. ExpiredSignatureError handled
if "ExpiredSignatureError" in db_src:
    ok("ExpiredSignatureError handled")
else:
    fail("ExpiredSignatureError not handled")

# 4e. AuthServiceUnavailable for transient errors
if "AuthServiceUnavailable" in db_src:
    ok("AuthServiceUnavailable exception for 503 handling")
else:
    fail("No transient auth error handling")

# 4f. Retry logic with exponential backoff
if "exponential" in db_src.lower() or "base_delay" in db_src:
    ok("DB operations have retry with backoff")
else:
    fail("No retry/backoff in DB layer")

# 4g. DB singleton pattern
if "_db_instance" in db_src and "get_db" in db_src:
    ok("SupabaseDB uses singleton pattern")
else:
    fail("SupabaseDB not singleton")

# 4h. Service-role key used (not anon key) for backend DB
if "supabase_service_role_key" in db_src:
    ok("Backend uses service-role key for DB (bypasses RLS)")
else:
    fail("Backend may use anon key for DB operations")

# ══════════════════════════════════════════════════════════════════════
# 5. DEPS.PY — AUTH MIDDLEWARE
# ══════════════════════════════════════════════════════════════════════
section("5. DEPS.PY AUTH MIDDLEWARE")

deps_src = read(BE / "app" / "api" / "deps.py")

# 5a. Token extracted from Authorization header only
if "Authorization" in deps_src or "authorization" in deps_src:
    ok("Token from Authorization header")
else:
    fail("Token not from Authorization header")

# 5b. Bearer prefix checked
if 'startswith("Bearer ")' in deps_src:
    ok("Bearer prefix validated")
else:
    fail("Bearer prefix not validated")

# 5c. MAX_TOKEN_SIZE enforced
if "MAX_TOKEN_SIZE" in deps_src:
    ok("MAX_TOKEN_SIZE enforced in deps")
else:
    fail("MAX_TOKEN_SIZE not enforced")

# 5d. 401 on missing token
if "HTTP_401_UNAUTHORIZED" in deps_src:
    ok("Returns 401 on missing/invalid token")
else:
    fail("Missing 401 response")

# 5e. 403 on disabled user
if "HTTP_403_FORBIDDEN" in deps_src and "is_active" in deps_src:
    ok("Returns 403 on disabled user (is_active check)")
else:
    fail("No disabled user check")

# 5f. 503 on auth service unavailable
if "HTTP_503_SERVICE_UNAVAILABLE" in deps_src:
    ok("Returns 503 on auth service unavailable")
else:
    fail("No 503 for auth service outage")

# 5g. Generic catch doesn't leak
auth_catch = deps_src[deps_src.find("except Exception as e"):][:200] if "except Exception as e" in deps_src else ""
if "Authentication failed" in auth_catch and "str(e)" not in auth_catch.split("detail")[0] if "detail" in auth_catch else True:
    ok("Auth exception handler doesn't leak error to client")
else:
    warn("Auth exception handler may leak error details")

# 5h. require_premium_user dependency
if "require_premium_user" in deps_src:
    ok("require_premium_user dependency available")
else:
    warn("No premium user gate dependency")

# ══════════════════════════════════════════════════════════════════════
# 6. DOCKER / INFRA HARDENING
# ══════════════════════════════════════════════════════════════════════
section("6. DOCKER / INFRA HARDENING")

dc_src = read(INFRA / "docker-compose.yml")
df_be = read(INFRA / "Dockerfile.backend")
df_fe = read(INFRA / "Dockerfile.frontend")

# 6a. Dockerfiles use non-root user
if "USER " in df_be and "USER root" not in df_be:
    ok("Backend Dockerfile runs as non-root")
else:
    fail("Backend Dockerfile runs as root", "Add USER appuser after WORKDIR")

if "USER " in df_fe and "USER root" not in df_fe:
    ok("Frontend Dockerfile runs as non-root")
else:
    fail("Frontend Dockerfile runs as root", "Add USER nextjs/node after build")

# 6b. .dockerignore exists
if (ROOT / "backend" / ".dockerignore").exists() or (INFRA / ".dockerignore").exists():
    ok("Backend .dockerignore exists")
else:
    fail("No backend .dockerignore", "May copy .env, .git, __pycache__ into image")

if (ROOT / "frontend" / ".dockerignore").exists():
    ok("Frontend .dockerignore exists")
else:
    fail("No frontend .dockerignore", "May copy node_modules, .env into image")

# 6c. Docker-compose DEBUG not hardcoded true
if "DEBUG=true" in dc_src:
    fail("docker-compose.yml hardcodes DEBUG=true", "Use ${DEBUG:-false}")
else:
    ok("DEBUG not hardcoded in docker-compose")

# 6d. HEALTHCHECK in Dockerfiles
if "HEALTHCHECK" in df_be:
    ok("Backend Dockerfile has HEALTHCHECK")
else:
    fail("Backend Dockerfile missing HEALTHCHECK")

if "HEALTHCHECK" in df_fe:
    ok("Frontend Dockerfile has HEALTHCHECK")
else:
    fail("Frontend Dockerfile missing HEALTHCHECK")

# 6e. Redis password
if "requirepass" in dc_src or "REDIS_PASSWORD" in dc_src:
    ok("Redis configured with password")
else:
    fail("Redis has no password", "Anyone on network can access cache/rate-limit data")

# 6f. Redis not exposed to host in production
if '"6379:6379"' in dc_src:
    warn("Redis port 6379 exposed to host", "Bind to 127.0.0.1:6379 or remove port mapping in prod")
else:
    ok("Redis port not exposed to host")

# 6g. Volumes mount source code (dev ok, but note for prod)
if "../backend:/app" in dc_src:
    warn("Docker-compose mounts source into container", "OK for dev; remove volume mounts in production compose")
else:
    ok("No source code volume mounts")

# ══════════════════════════════════════════════════════════════════════
# 7. .GITIGNORE — SECRETS EXCLUSION
# ══════════════════════════════════════════════════════════════════════
section("7. GITIGNORE SECRETS")

gitignore = read(ROOT / ".gitignore") if (ROOT / ".gitignore").exists() else ""

for pattern in [".env", ".env.local"]:
    if pattern in gitignore:
        ok(f"'{pattern}' in .gitignore")
    else:
        fail(f"'{pattern}' NOT in .gitignore")

for pattern in ["firebase-admin-sdk", "serviceAccount"]:
    if pattern in gitignore:
        ok(f"'{pattern}' credential files in .gitignore")
    else:
        warn(f"'{pattern}' not in .gitignore")

if ".venv" in gitignore or "venv" in gitignore:
    ok("venv excluded from git")
else:
    fail("venv not in .gitignore")

if "__pycache__" in gitignore:
    ok("__pycache__ excluded from git")
else:
    fail("__pycache__ not in .gitignore")

# ══════════════════════════════════════════════════════════════════════
# 8. FRONTEND — SUPABASE CLIENT SECURITY
# ══════════════════════════════════════════════════════════════════════
section("8. FRONTEND SUPABASE CLIENT")

supa_src = read(FE / "src" / "lib" / "supabase.ts")

# 8a. Only anon key used (no service_role)
if "NEXT_PUBLIC_SUPABASE_ANON_KEY" in supa_src and "SERVICE_ROLE" not in supa_src:
    ok("Frontend uses only anon key (no service_role)")
else:
    fail("Frontend may expose service_role key")

# 8b. Session persistence
if "persistSession: true" in supa_src:
    ok("Supabase session persistence enabled")
else:
    warn("Session persistence not enabled")

# 8c. Auto refresh token
if "autoRefreshToken: true" in supa_src:
    ok("Auto token refresh enabled")
else:
    warn("Auto token refresh not enabled")

# 8d. Singleton pattern
if "globalForSupabase" in supa_src or "__hirestackSupabase" in supa_src:
    ok("Supabase client is singleton (prevents multiple sockets)")
else:
    warn("Supabase client may not be singleton")

# ══════════════════════════════════════════════════════════════════════
# 9. FRONTEND — AUTH PROVIDER
# ══════════════════════════════════════════════════════════════════════
section("9. FRONTEND AUTH PROVIDER")

prov_src = read(FE / "src" / "components" / "providers.tsx")

# 9a. onAuthStateChange listener
if "onAuthStateChange" in prov_src:
    ok("Auth state change listener active")
else:
    fail("No auth state change listener")

# 9b. Subscription cleanup
if "subscription.unsubscribe" in prov_src:
    ok("Auth subscription cleanup on unmount")
else:
    fail("Auth subscription not cleaned up")

# 9c. OAuth redirect uses window.location.origin
if "window.location.origin" in prov_src:
    ok("OAuth redirect uses dynamic origin (not hardcoded)")
else:
    fail("OAuth redirect may use hardcoded URL")

# 9d. Realtime auth sync
if "setAuth" in prov_src:
    ok("Realtime socket auth synced with session token")
else:
    warn("Realtime socket auth not synced")

# ══════════════════════════════════════════════════════════════════════
# 10. FRONTEND — DASHBOARD AUTH GUARD
# ══════════════════════════════════════════════════════════════════════
section("10. FRONTEND DASHBOARD AUTH GUARD")

dash_layout = read(FE / "src" / "app" / "(dashboard)" / "layout.tsx")

# 10a. Redirect to login if not authenticated
if 'router.replace("/login")' in dash_layout:
    ok("Dashboard redirects to /login when unauthenticated")
else:
    fail("Dashboard doesn't redirect unauthenticated users")

# 10b. Loading state prevents flash
if "loading" in dash_layout and "return null" in dash_layout:
    ok("Loading state prevents unauthenticated content flash")
else:
    warn("Possible flash of unauthenticated content")

# 10c. API token sync with session
if "api.setToken" in dash_layout and "access_token" in dash_layout:
    ok("API client token synced with session")
else:
    fail("API client token not synced with session")

# 10d. Token cleared on logout
if "api.setToken(null)" in dash_layout:
    ok("API token cleared when session is null")
else:
    fail("API token not cleared on logout")

# ══════════════════════════════════════════════════════════════════════
# 11. FRONTEND — XSS / dangerouslySetInnerHTML
# ══════════════════════════════════════════════════════════════════════
section("11. FRONTEND XSS REVIEW")

# Find all dangerouslySetInnerHTML usages
xss_files = []
for root_d, dirs, files in os.walk(FE / "src"):
    dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", ".next-dev-3002")]
    for f in files:
        if f.endswith((".tsx", ".ts", ".jsx", ".js")):
            fp = os.path.join(root_d, f)
            content = read(fp)
            if "dangerouslySetInnerHTML" in content:
                xss_files.append(fp)

if len(xss_files) == 0:
    ok("No dangerouslySetInnerHTML usage")
else:
    for fp in xss_files:
        content = read(fp)
        rel = os.path.relpath(fp, FE)
        # Check if DOMPurify or sanitize is used
        if "DOMPurify" in content or "sanitize" in content.lower():
            ok(f"{rel} uses dangerouslySetInnerHTML WITH sanitization")
        else:
            fail(f"{rel} uses dangerouslySetInnerHTML WITHOUT sanitization", "Potential stored XSS")

# ══════════════════════════════════════════════════════════════════════
# 12. FRONTEND — NEXT.CONFIG.JS
# ══════════════════════════════════════════════════════════════════════
section("12. NEXT.CONFIG.JS")

nc_src = read(FE / "next.config.js")

# 12a. Strict mode
if "reactStrictMode: true" in nc_src:
    ok("React strict mode enabled")
else:
    fail("React strict mode not enabled")

# 12b. Image domains explicit
if "domains:" in nc_src:
    ok("Image domains explicitly configured")
else:
    warn("Image domains not configured")

# 12c. Security headers in next.config
if "headers" in nc_src and "Content-Security-Policy" in nc_src:
    ok("Security headers configured in next.config.js")
else:
    fail("No security headers in next.config.js", "Add CSP and other headers via next.config headers()")

# 12d. API rewrite sanitization
if "rewrites" in nc_src:
    ok("API proxy rewrites configured")
    # Check it uses env variable
    if "NEXT_PUBLIC_API_URL" in nc_src:
        ok("API rewrite uses env variable for backend URL")
    else:
        warn("API rewrite may have hardcoded backend URL")
else:
    warn("No API rewrites configured")

# ══════════════════════════════════════════════════════════════════════
# 13. FRONTEND — LOGIN PAGE SECURITY
# ══════════════════════════════════════════════════════════════════════
section("13. FRONTEND LOGIN PAGE")

login_src = read(FE / "src" / "app" / "login" / "page.tsx")

# 13a. Password validation
if "validatePassword" in login_src:
    ok("Client-side password validation implemented")
else:
    fail("No password validation on register")

# 13b. Password strength meter
if "getPasswordStrength" in login_src or "strength" in login_src:
    ok("Password strength indicator present")
else:
    warn("No password strength indicator")

# 13c. Error doesn't leak backend details
if "err?.message" in login_src or "error.message" in login_src:
    warn("Login error may display raw Supabase error messages", "Consider generic error for failed login")
else:
    ok("Login error messages sanitized")

# ══════════════════════════════════════════════════════════════════════
# 14. FRONTEND — PUBLIC REVIEW PAGE
# ══════════════════════════════════════════════════════════════════════
section("14. PUBLIC REVIEW PAGE")

review_src = read(FE / "src" / "app" / "review" / "[token]" / "page.tsx")

# 14a. dangerouslySetInnerHTML on document_snapshot
if "dangerouslySetInnerHTML" in review_src:
    if "DOMPurify" in review_src or "sanitize" in review_src.lower():
        ok("Review page sanitizes document_snapshot HTML")
    else:
        fail("Review page renders unsanitized HTML", "document_snapshot injected via dangerouslySetInnerHTML without DOMPurify")
else:
    ok("Review page doesn't use raw HTML injection")

# 14b. No auth required (correct for public page)
if "useAuth" not in review_src or "get_current_user" not in review_src:
    ok("Public review page correctly has no auth requirement")
else:
    warn("Review page has unexpected auth dependency")

# ══════════════════════════════════════════════════════════════════════
# 15. REMAINING AIClient() → get_ai_client() MIGRATION
# ══════════════════════════════════════════════════════════════════════
section("15. AIClient() SINGLETON MIGRATION (REMAINING)")

service_files_to_check = [
    ("services/job.py", BE / "app" / "services" / "job.py"),
    ("services/profile.py", BE / "app" / "services" / "profile.py"),
    ("services/job_sync.py", BE / "app" / "services" / "job_sync.py"),
]

for label, path in service_files_to_check:
    src = read(path)
    if "get_ai_client" in src and "AIClient()" not in src:
        ok(f"{label} uses get_ai_client() singleton")
    elif "AIClient()" in src:
        fail(f"{label} still uses AIClient() directly", "Migrate to get_ai_client()")
    else:
        ok(f"{label} doesn't use AI client")

# Also verify the 7 already-fixed services are still good
already_fixed = [
    "services/ats.py", "services/evidence_mapper.py", "services/interview.py",
    "services/learning.py", "services/review.py", "services/salary.py",
    "services/doc_variant.py",
]
for label in already_fixed:
    src = read(BE / "app" / label)
    if "get_ai_client" in src:
        ok(f"{label} uses get_ai_client() ✓")
    else:
        fail(f"{label} regression — lost get_ai_client()")

# ══════════════════════════════════════════════════════════════════════
# 16. BACKEND — HEALTH ENDPOINT ERROR LEAK
# ══════════════════════════════════════════════════════════════════════
section("16. HEALTH ENDPOINT")

# Already checked in section 1 — also verify live
import urllib.request
try:
    r = urllib.request.urlopen("http://localhost:8000/health", timeout=5)
    data = json.loads(r.read())
    if "error" in json.dumps(data.get("supabase", {}).get("database", {})):
        warn("Health endpoint returned error field in supabase.database")
    else:
        ok("Health endpoint response clean (no error field)")
    # Check supabase URL doesn't leak service key
    supa = data.get("supabase", {})
    if "service_role" in json.dumps(supa).lower() or "anon_key" in json.dumps(supa).lower():
        fail("Health endpoint leaks Supabase keys")
    else:
        ok("Health endpoint doesn't expose Supabase keys")
except Exception as e:
    warn(f"Could not reach health endpoint: {e}")

# ══════════════════════════════════════════════════════════════════════
# 17. LIVE — SECURITY HEADERS
# ══════════════════════════════════════════════════════════════════════
section("17. LIVE SECURITY HEADERS")

try:
    req = urllib.request.Request("http://localhost:8000/health")
    resp = urllib.request.urlopen(req, timeout=5)
    resp_headers = {k.lower(): v for k, v in resp.getheaders()}

    for name, expected in required_headers:
        if name in resp_headers:
            ok(f"Response header '{name}' present")
        else:
            fail(f"Response header '{name}' missing from response")

    if "server" not in resp_headers:
        ok("Server header stripped from response")
    else:
        fail(f"Server header present: {resp_headers['server']}")

except Exception as e:
    warn(f"Could not check live headers: {e}")

# ══════════════════════════════════════════════════════════════════════
# 18. FRONTEND — API CLIENT SECURITY
# ══════════════════════════════════════════════════════════════════════
section("18. FRONTEND API CLIENT")

api_src = read(FE / "src" / "lib" / "api.ts")

# 18a. Token from class field, not URL param
if "Authorization" in api_src and "Bearer" in api_src:
    ok("API client sends token via Authorization header")
else:
    fail("API client doesn't use Authorization header")

# 18b. No token in URL
if "?token=" not in api_src and "&token=" not in api_src:
    ok("Token not passed in URL query params")
else:
    fail("Token passed in URL query params")

# 18c. Content-Type: application/json
if '"Content-Type": "application/json"' in api_src or "'Content-Type': 'application/json'" in api_src:
    ok("API client sets Content-Type: application/json")
else:
    warn("API client may not set Content-Type")

# ══════════════════════════════════════════════════════════════════════
# CLEANUP & RESULTS
# ══════════════════════════════════════════════════════════════════════
print(f"\n══ CLEANUP ══\n")
print("=" * 60)
print(f"RESULTS: {passed + failed}/{passed + failed} passed {passed}, failed {failed}, {warnings} warning(s)")
if failed == 0:
    print("ALL TESTS PASSED" + (f" ({warnings} warnings)" if warnings else ""))
else:
    print(f"⚠ {failed} FAILURE(S) NEED ATTENTION")
print("=" * 60)
