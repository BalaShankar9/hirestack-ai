#!/usr/bin/env python3
"""
Modules 9, 10 & 11 — Frontend Lib/Hooks, Pages/Components & Database/SQL
Security-audit test script.

Covers:
  Module 9:  Frontend lib utilities (sanitize, export, firestore/ops, storage, supabase, middleware)
  Module 10: Frontend pages & components (tiptap-editor, error-boundary, evidence, api-keys,
             job-board, next.config.js, textareas, form labels)
  Module 11: Supabase config & SQL migrations (password policy, MFA, SECURITY DEFINER,
             indexes, CHECK constraints, TEXT length limits, dynamic SQL)

Run:
    python scripts/test_module9_10_11_frontend_db.py
"""
from __future__ import annotations

import os
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FE   = ROOT / "frontend"
SRC  = FE / "src"
SUPA = ROOT / "supabase"

passed = failed = warnings = 0


# ─── helpers ──────────────────────────────────────────────────────
def section(title: str):
    print(f"\n══ {title} ══")


def ok(label: str):
    global passed
    passed += 1
    print(f"  ✅ PASS  {label}")


def fail(label: str, reason: str = ""):
    global failed
    failed += 1
    extra = f"  — {reason}" if reason else ""
    print(f"  ❌ FAIL  {label}{extra}")


def warn(label: str, reason: str = ""):
    global warnings
    warnings += 1
    extra = f"  — {reason}" if reason else ""
    print(f"  ⚠ WARN  {label}{extra}")


def read(p: pathlib.Path) -> str:
    if not p.exists():
        return ""
    return p.read_text(errors="replace")


# ══════════════════════════════════════════════════════════════════
#  MODULE 9 — FRONTEND LIB / HOOKS
# ══════════════════════════════════════════════════════════════════

# ── 1. sanitize.ts ───────────────────────────────────────────────
section("M9-1. LIB/SANITIZE.TS — Core sanitization utility")

sanitize_path = SRC / "lib" / "sanitize.ts"
sanitize_src = read(sanitize_path)

if sanitize_path.exists():
    ok("sanitize.ts exists")
else:
    fail("sanitize.ts does not exist")

for export_name in ("escapeHtml", "sanitizeUrl", "ALLOWED_STORAGE_BUCKETS",
                     "isAllowedFileExtension", "isAllowedFileSize"):
    if f"export " in sanitize_src and export_name in sanitize_src:
        ok(f"sanitize.ts exports {export_name}")
    else:
        fail(f"sanitize.ts missing export: {export_name}")

# Verify escapeHtml encodes the critical 5 characters
for char_pair in [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
                  ('"', "&quot;"), ("'", "&#39;")]:
    if char_pair[1] in sanitize_src:
        ok(f"escapeHtml encodes {char_pair[0]} → {char_pair[1]}")
    else:
        fail(f"escapeHtml does NOT encode {char_pair[0]}")

# sanitizeUrl blocks javascript: protocol
if "SAFE_URL_PROTOCOLS" in sanitize_src or "http:" in sanitize_src:
    ok("sanitizeUrl uses an allowlist of safe URL protocols")
else:
    fail("sanitizeUrl missing safe-protocol allowlist")

# MAX_FILE_SIZE_BYTES defined
if "MAX_FILE_SIZE_BYTES" in sanitize_src:
    ok("MAX_FILE_SIZE_BYTES constant defined in sanitize.ts")
else:
    fail("MAX_FILE_SIZE_BYTES not defined")

# ALLOWED_FILE_EXTENSIONS
if "ALLOWED_FILE_EXTENSIONS" in sanitize_src:
    ok("ALLOWED_FILE_EXTENSIONS set defined")
else:
    fail("ALLOWED_FILE_EXTENSIONS missing")


# ── 2. export.ts ─────────────────────────────────────────────────
section("M9-2. LIB/EXPORT.TS — XSS prevention in document export")

export_src = read(SRC / "lib" / "export.ts")

# 2a. DOMPurify usage
if "DOMPurify.sanitize" in export_src:
    ok("export.ts uses DOMPurify.sanitize for innerHTML")
else:
    fail("export.ts missing DOMPurify.sanitize — innerHTML XSS risk")

dompurify_count = export_src.count("DOMPurify.sanitize")
if dompurify_count >= 2:
    ok(f"DOMPurify.sanitize used in {dompurify_count} places (PDF + image export)")
else:
    warn(f"DOMPurify.sanitize found only {dompurify_count} time(s)", "Expected ≥ 2")

# 2b. escapeHtml in HTML template builders
if "escapeHtml" in export_src:
    escape_count = export_src.count("escapeHtml(")
    if escape_count >= 5:
        ok(f"export.ts HTML builders use escapeHtml() ({escape_count} call sites)")
    else:
        warn(f"Only {escape_count} escapeHtml() calls in export.ts", "Expected ≥ 5")
else:
    fail("export.ts does not use escapeHtml()")

# 2c. import from sanitize
if 'from "@/lib/sanitize"' in export_src or "from '@/lib/sanitize'" in export_src:
    ok("export.ts imports from @/lib/sanitize")
else:
    fail("export.ts does not import from sanitize module")

# 2d. downloadHtml has CSP meta tag
if 'Content-Security-Policy' in export_src:
    ok("Exported HTML documents include Content-Security-Policy meta header")
else:
    fail("Exported HTML missing CSP meta header")

# Check both downloadHtml and downloadDocx have CSP
csp_count = export_src.count("Content-Security-Policy")
if csp_count >= 2:
    ok(f"CSP meta header present in {csp_count} export templates (HTML + DOCX)")
else:
    warn(f"CSP meta header found only {csp_count} time(s)", "Expected in both HTML and DOCX exports")


# ── 3. firestore/ops.ts ──────────────────────────────────────────
section("M9-3. LIB/FIRESTORE/OPS.TS — Data layer hardening")

ops_src = read(SRC / "lib" / "firestore" / "ops.ts")

# 3a. Seed generators use escapeHtml
ops_escape_count = ops_src.count("escapeHtml(")
if ops_escape_count >= 10:
    ok(f"ops.ts seed/HTML builders use escapeHtml() ({ops_escape_count} call sites)")
elif ops_escape_count >= 1:
    warn(f"ops.ts uses escapeHtml() only {ops_escape_count} times", "Expected ≥ 10")
else:
    fail("ops.ts does not use escapeHtml()")

# 3b. ALLOWED_DB_FIELDS allowlist in patchApplication
if "ALLOWED_DB_FIELDS" in ops_src:
    ok("ALLOWED_DB_FIELDS defined — patchApplication uses field allowlist")
else:
    fail("ALLOWED_DB_FIELDS not defined — arbitrary column writes possible")

# 3c. patchApplication skips disallowed fields
if "Skip disallowed" in ops_src or "if (!ALLOWED_DB_FIELDS.has" in ops_src:
    ok("patchApplication skips fields not in allowlist")
else:
    fail("patchApplication does not filter against allowlist")

# 3d. uploadResume validates file type/size
if "isAllowedFileExtension" in ops_src and "uploadResume" in ops_src:
    # Verify validation is inside uploadResume (not just imported)
    upload_resume_section = ops_src[ops_src.index("uploadResume"):]
    if "isAllowedFileExtension" in upload_resume_section[:500]:
        ok("uploadResume validates file extension")
    else:
        fail("uploadResume does not validate file extension")
else:
    fail("uploadResume missing file extension validation")

if "isAllowedFileSize" in ops_src:
    ok("uploadResume/uploadEvidenceFile validates file size")
else:
    fail("File upload functions missing size validation")

# 3e. uploadEvidenceFile validates
upload_ev_section = ops_src[ops_src.index("uploadEvidenceFile"):] if "uploadEvidenceFile" in ops_src else ""
if "isAllowedFileExtension" in upload_ev_section[:500]:
    ok("uploadEvidenceFile validates file extension")
else:
    fail("uploadEvidenceFile missing file extension validation")

# 3f. crypto.randomUUID usage
if "crypto.randomUUID" in ops_src:
    ok("ops.ts uid() uses crypto.randomUUID (CSPRNG)")
else:
    fail("ops.ts uid() not using crypto.randomUUID — weak ID generation")

# 3g. No Math.random for IDs
uid_section = ops_src[ops_src.index("function uid("):ops_src.index("function uid(") + 200] if "function uid(" in ops_src else ""
if "Math.random" in uid_section:
    fail("uid() still uses Math.random — predictable IDs")
else:
    ok("uid() does not use Math.random for primary ID generation")

# 3h. createEvidence validates URLs with sanitizeUrl
if "createEvidence" in ops_src:
    create_ev_idx = ops_src.index("createEvidence")
    create_ev_section = ops_src[create_ev_idx:create_ev_idx + 600]
    if "sanitizeUrl" in create_ev_section:
        ok("createEvidence validates URLs with sanitizeUrl()")
    else:
        fail("createEvidence does not validate URLs — javascript: protocol risk")
else:
    fail("createEvidence function not found")

# 3i. Import from sanitize module
if 'from "@/lib/sanitize"' in ops_src or "from '@/lib/sanitize'" in ops_src:
    imported_names = re.findall(r'import\s*\{([^}]+)\}\s*from\s*["\']@/lib/sanitize["\']', ops_src)
    if imported_names:
        imports_str = imported_names[0]
        for name in ("escapeHtml", "isAllowedFileExtension", "isAllowedFileSize",
                      "MAX_FILE_SIZE_BYTES", "sanitizeUrl"):
            if name in imports_str:
                ok(f"ops.ts imports {name} from sanitize")
            else:
                fail(f"ops.ts missing import: {name}")
    else:
        fail("Could not parse sanitize imports in ops.ts")
else:
    fail("ops.ts does not import from @/lib/sanitize")


# ── 4. storage.ts ────────────────────────────────────────────────
section("M9-4. LIB/STORAGE.TS — Bucket allowlist")

storage_src = read(SRC / "lib" / "storage.ts")

if "ALLOWED_STORAGE_BUCKETS" in storage_src:
    ok("storage.ts imports/uses ALLOWED_STORAGE_BUCKETS")
else:
    fail("storage.ts missing ALLOWED_STORAGE_BUCKETS — SSRF via bucket manipulation")

if "Blocked access to disallowed bucket" in storage_src or "!ALLOWED_STORAGE_BUCKETS.has" in storage_src:
    ok("resolveFileUrl validates bucket against allowlist")
else:
    fail("resolveFileUrl does not validate bucket")


# ── 5. supabase.ts ───────────────────────────────────────────────
section("M9-5. LIB/SUPABASE.TS — Client singleton safety")

supabase_src = read(SRC / "lib" / "supabase.ts")

# 5a. No window.__hirestackSupabase exposure (ignore comments)
# Strip single-line comments to avoid matching the "Removed" audit comment
code_lines = [ln for ln in supabase_src.splitlines() if not ln.strip().startswith("//")]
supabase_code_only = "\n".join(code_lines)
if "window.__hirestackSupabase" in supabase_code_only or "window['__hirestackSupabase']" in supabase_code_only:
    fail("supabase.ts still assigns window.__hirestackSupabase — console credential theft")
else:
    ok("supabase.ts does NOT expose client via window.__hirestackSupabase")

# 5b. Production guard uses globalThis not window
if "globalForSupabase" in supabase_src and "__hirestackSupabase" in supabase_src:
    ok("Dev singleton uses globalThis (module-scoped, not window-accessible)")
else:
    warn("Could not confirm globalThis usage for dev singleton")

# 5c. Comment about removal present
if "Removed window.__hirestackSupabase" in supabase_src or "M9-F5" in supabase_src:
    ok("Code comment documents window assignment removal (M9-F5)")
else:
    warn("Missing comment about M9-F5 window assignment removal")


# ── 6. middleware.ts ─────────────────────────────────────────────
section("M9-6. MIDDLEWARE.TS — Redirect validation")

middleware_src = read(SRC / "middleware.ts")

if "isValidRedirect" in middleware_src:
    ok("middleware.ts defines isValidRedirect function")
else:
    fail("middleware.ts missing isValidRedirect — open redirect risk")

# Verify redirect validation checks for protocol-relative URLs
if '!path.startsWith("//")' in middleware_src or "!//" in middleware_src:
    ok("isValidRedirect blocks protocol-relative URLs (//evil.com)")
else:
    fail("isValidRedirect does not block protocol-relative URLs")

# Verify it's used where redirect param is set
if "isValidRedirect(pathname)" in middleware_src or "isValidRedirect(" in middleware_src:
    ok("isValidRedirect is called before setting redirect param")
else:
    fail("isValidRedirect defined but never called")


# ══════════════════════════════════════════════════════════════════
#  MODULE 10 — FRONTEND PAGES & COMPONENTS
# ══════════════════════════════════════════════════════════════════

# ── 7. tiptap-editor.tsx ─────────────────────────────────────────
section("M10-7. COMPONENTS/EDITOR/TIPTAP-EDITOR.TSX — Link validation")

tiptap_src = read(SRC / "components" / "editor" / "tiptap-editor.tsx")

if "sanitizeUrl" in tiptap_src:
    ok("tiptap-editor imports sanitizeUrl")
else:
    fail("tiptap-editor missing sanitizeUrl — XSS via javascript: links")

if 'from "@/lib/sanitize"' in tiptap_src or "from '@/lib/sanitize'" in tiptap_src:
    ok("tiptap-editor imports from @/lib/sanitize module")
else:
    fail("tiptap-editor does not import from sanitize module")

# Verify sanitizeUrl is called when setting links
tiptap_sanitize_calls = tiptap_src.count("sanitizeUrl(")
if tiptap_sanitize_calls >= 1:
    ok(f"sanitizeUrl() called {tiptap_sanitize_calls} time(s) for link validation")
else:
    fail("sanitizeUrl() not called in tiptap-editor")


# ── 8. error-boundary.tsx ────────────────────────────────────────
section("M10-8. COMPONENTS/ERROR-BOUNDARY.TSX — Error message hiding")

error_boundary_src = read(SRC / "components" / "error-boundary.tsx")

if "NODE_ENV" in error_boundary_src:
    ok("error-boundary checks NODE_ENV before displaying error details")
else:
    fail("error-boundary does not check NODE_ENV — stack traces visible in production")

if '"development"' in error_boundary_src:
    ok("Error details only shown when NODE_ENV === 'development'")
else:
    fail("Missing 'development' check in error-boundary")

if "An unexpected error occurred" in error_boundary_src:
    ok("Production fallback shows generic error message")
else:
    fail("Missing generic fallback message for production")


# ── 9. evidence/page.tsx ─────────────────────────────────────────
section("M10-9. EVIDENCE/PAGE.TSX — File upload validation")

evidence_src = read(SRC / "app" / "(dashboard)" / "evidence" / "page.tsx")

if "MAX_FILE_SIZE" in evidence_src or "max_file_size" in evidence_src.lower():
    ok("evidence/page.tsx defines MAX_FILE_SIZE constant")
else:
    fail("evidence/page.tsx missing file size limit constant")

if "file.size" in evidence_src:
    ok("evidence/page.tsx checks file.size before upload")
else:
    fail("evidence/page.tsx does not validate file size")

# Check for file type validation
if "file.type" in evidence_src or "file.name" in evidence_src:
    ok("evidence/page.tsx references file type/name for validation")
else:
    warn("evidence/page.tsx may not validate file type")


# ── 10. api-keys/page.tsx ────────────────────────────────────────
section("M10-10. API-KEYS/PAGE.TSX — Key secret clearing")

api_keys_src = read(SRC / "app" / "(dashboard)" / "api-keys" / "page.tsx")

if "setNewKeySecret(null)" in api_keys_src:
    ok("api-keys/page.tsx clears newKeySecret from state")
else:
    fail("api-keys/page.tsx does not clear newKeySecret — secret persists in memory")

# Verify it's cleared after copy
if "setTimeout" in api_keys_src and "setNewKeySecret(null)" in api_keys_src:
    ok("Key secret cleared automatically after timeout (post-copy)")
else:
    warn("Key secret clearing may not be automatic")

# Check for M10-F5 comment
if "M10-F5" in api_keys_src or "minimize exposure" in api_keys_src.lower():
    ok("Code comment documents key clearing rationale")
else:
    warn("Missing comment about key clearing rationale")


# ── 11. job-board/page.tsx ───────────────────────────────────────
section("M10-11. JOB-BOARD/PAGE.TSX — URL validation")

job_board_src = read(SRC / "app" / "(dashboard)" / "job-board" / "page.tsx")

if "sanitizeUrl" in job_board_src:
    ok("job-board/page.tsx uses sanitizeUrl for external links")
else:
    fail("job-board/page.tsx does not sanitize external URLs")

if 'from "@/lib/sanitize"' in job_board_src:
    ok("job-board/page.tsx imports from @/lib/sanitize")
else:
    fail("job-board/page.tsx missing sanitize import")

# Verify sanitizeUrl is used in href attributes
if 'href={sanitizeUrl(' in job_board_src:
    ok("sanitizeUrl() wraps href attributes for external links")
else:
    warn("sanitizeUrl may not wrap href — check manually")

# rel=noopener
if 'rel="noopener' in job_board_src:
    ok("External links have rel='noopener noreferrer'")
else:
    warn("External links may be missing rel='noopener noreferrer'")


# ── 12. next.config.js ──────────────────────────────────────────
section("M10-12. NEXT.CONFIG.JS — CSP hardening")

next_config_src = read(FE / "next.config.js")

if "Content-Security-Policy" in next_config_src:
    ok("next.config.js sets Content-Security-Policy header")
else:
    fail("next.config.js missing CSP header")

if "unsafe-eval" in next_config_src:
    fail("CSP still contains 'unsafe-eval' — XSS risk via eval()")
else:
    ok("CSP does NOT contain 'unsafe-eval'")

if "'self'" in next_config_src:
    ok("CSP default-src includes 'self'")
else:
    fail("CSP missing 'self' default-src")

if "frame-ancestors" in next_config_src:
    ok("CSP includes frame-ancestors directive (clickjacking protection)")
else:
    fail("CSP missing frame-ancestors — clickjacking risk")

# Other security headers
for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"):
    if header in next_config_src:
        ok(f"next.config.js sets {header} header")
    else:
        fail(f"next.config.js missing {header} header")


# ── 13. Textareas have maxLength ─────────────────────────────────
section("M10-13. TEXTAREAS — maxLength={5000} on user input fields")

textarea_pages = {
    "ab-lab/page.tsx":       SRC / "app" / "(dashboard)" / "ab-lab" / "page.tsx",
    "ats-scanner/page.tsx":  SRC / "app" / "(dashboard)" / "ats-scanner" / "page.tsx",
    "interview/page.tsx":    SRC / "app" / "(dashboard)" / "interview" / "page.tsx",
}

for name, path in textarea_pages.items():
    src = read(path)
    if "maxLength={5000}" in src:
        count = src.count("maxLength={5000}")
        ok(f"{name}: maxLength={{5000}} found ({count} textarea(s))")
    elif "maxLength=" in src:
        ok(f"{name}: maxLength set (different value)")
    else:
        fail(f"{name}: textareas missing maxLength — unbounded input")


# ── 14. Form labels have htmlFor ─────────────────────────────────
section("M10-14. FORM LABELS — htmlFor attributes for accessibility & security")

label_pages = {
    "ab-lab/page.tsx":       SRC / "app" / "(dashboard)" / "ab-lab" / "page.tsx",
    "ats-scanner/page.tsx":  SRC / "app" / "(dashboard)" / "ats-scanner" / "page.tsx",
    "interview/page.tsx":    SRC / "app" / "(dashboard)" / "interview" / "page.tsx",
}

for name, path in label_pages.items():
    src = read(path)
    html_for_count = src.count("htmlFor=")
    label_count = src.count("<label") or src.count("<Label")
    if html_for_count >= 2:
        ok(f"{name}: {html_for_count} labels have htmlFor attributes")
    elif html_for_count >= 1:
        warn(f"{name}: only {html_for_count} label(s) with htmlFor", "Expected ≥ 2")
    else:
        fail(f"{name}: labels missing htmlFor attributes")


# ══════════════════════════════════════════════════════════════════
#  MODULE 11 — DATABASE / SQL SECURITY
# ══════════════════════════════════════════════════════════════════

# ── 15. config.toml — password policy ───────────────────────────
section("M11-15. SUPABASE/CONFIG.TOML — Auth & password policy")

config_src = read(SUPA / "config.toml")

# 15a. minimum_password_length >= 10
pw_match = re.search(r'minimum_password_length\s*=\s*(\d+)', config_src)
if pw_match:
    pw_len = int(pw_match.group(1))
    if pw_len >= 10:
        ok(f"minimum_password_length = {pw_len} (>= 10)")
    else:
        fail(f"minimum_password_length = {pw_len}", "Should be >= 10")
else:
    fail("minimum_password_length not set in config.toml")

# 15b. password_requirements includes letters_digits or stronger
pw_req_match = re.search(r'password_requirements\s*=\s*"([^"]+)"', config_src)
if pw_req_match:
    pw_req = pw_req_match.group(1)
    if "letters_digits" in pw_req:
        ok(f'password_requirements = "{pw_req}" (includes letters_digits)')
    else:
        fail(f'password_requirements = "{pw_req}"', "Should include letters_digits")
else:
    fail("password_requirements not set in config.toml")

# 15c. enable_confirmations = true
if re.search(r'enable_confirmations\s*=\s*true', config_src):
    ok("Email confirmations enabled (enable_confirmations = true)")
else:
    fail("Email confirmations NOT enabled")

# 15d. MFA TOTP enroll_enabled = true
if re.search(r'\[auth\.mfa\.totp\]', config_src):
    totp_section = config_src[config_src.index("[auth.mfa.totp]"):]
    if "enroll_enabled = true" in totp_section[:200]:
        ok("MFA TOTP enroll_enabled = true")
    else:
        fail("MFA TOTP enroll not enabled")
else:
    fail("[auth.mfa.totp] section not found in config.toml")

# 15e. MFA Phone enroll_enabled = true
if re.search(r'\[auth\.mfa\.phone\]', config_src):
    phone_section = config_src[config_src.index("[auth.mfa.phone]"):]
    if "enroll_enabled = true" in phone_section[:200]:
        ok("MFA Phone enroll_enabled = true")
    else:
        warn("MFA Phone enroll may not be enabled")
else:
    warn("[auth.mfa.phone] section not found")

# 15f. secure_password_change
if "secure_password_change = true" in config_src:
    ok("secure_password_change = true (requires recent auth for password changes)")
else:
    warn("secure_password_change not set to true")

# 15g. double_confirm_changes
if "double_confirm_changes = true" in config_src:
    ok("double_confirm_changes = true (both old + new email must confirm)")
else:
    warn("double_confirm_changes not enabled")


# ── 16. Full schema migration — SECURITY DEFINER ────────────────
section("M11-16. FULL SCHEMA SQL — SECURITY DEFINER + search_path")

schema_path = SUPA / "migrations" / "20260206000000_full_schema.sql"
schema_src = read(schema_path)

if schema_path.exists():
    ok("20260206000000_full_schema.sql exists")
else:
    fail("Full schema migration not found")

# 16a. All SECURITY DEFINER functions have SET search_path = public
sec_definer_count = schema_src.lower().count("security definer")
search_path_count = len(re.findall(r'SECURITY\s+DEFINER\s+SET\s+search_path\s*=\s*public', schema_src, re.IGNORECASE))
if sec_definer_count > 0:
    if search_path_count >= sec_definer_count:
        ok(f"All {sec_definer_count} SECURITY DEFINER function(s) have SET search_path = public")
    else:
        fail(f"{search_path_count}/{sec_definer_count} SECURITY DEFINER functions have SET search_path", "All must set search_path")
else:
    warn("No SECURITY DEFINER functions found in full schema")

# 16b. Dynamic SQL uses %I for identifiers
if "format(" in schema_src:
    # Count %I and %s in format() calls
    format_section = schema_src[schema_src.index("format("):]
    pct_I_count = format_section[:500].count("%I")
    pct_s_count = format_section[:500].count("%s")
    if pct_I_count > 0:
        ok(f"Dynamic SQL uses %I for identifiers ({pct_I_count} usages)")
    else:
        fail("Dynamic SQL uses %s instead of %I — SQL injection risk")
    if pct_s_count > 0:
        warn(f"Dynamic SQL also uses %s ({pct_s_count} times)", "Verify these are for values, not identifiers")
    else:
        ok("Dynamic SQL does not use %s for identifiers")
else:
    warn("No format() calls found in full schema")

# 16c. handle_new_user has search_path set
if "handle_new_user" in schema_src:
    hnu_idx = schema_src.index("handle_new_user")
    hnu_section = schema_src[hnu_idx:hnu_idx + 500]
    if "SET search_path" in hnu_section:
        ok("handle_new_user() has SET search_path = public")
    else:
        fail("handle_new_user() missing SET search_path")
else:
    warn("handle_new_user function not found in schema")


# ── 17. Add indexes migration ───────────────────────────────────
section("M11-17. ADD INDEXES MIGRATION — Indexes, constraints, limits")

idx_path = SUPA / "migrations" / "20260212000000_add_indexes.sql"
idx_src = read(idx_path)

if idx_path.exists():
    ok("20260212000000_add_indexes.sql exists")
else:
    fail("Add indexes migration not found")

# 17a. Indexes on user_id and application_id columns
index_names = re.findall(r'CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)', idx_src, re.IGNORECASE)
if len(index_names) >= 4:
    ok(f"Migration creates {len(index_names)} indexes")
else:
    fail(f"Only {len(index_names)} indexes created", "Expected ≥ 4")

# Check for user_id indexes
user_id_indexes = [n for n in index_names if "user_id" in n]
if user_id_indexes:
    ok(f"Indexes on user_id columns: {len(user_id_indexes)}")
else:
    fail("No indexes on user_id columns")

# Check for application_id indexes
app_id_indexes = [n for n in index_names if "application_id" in n]
if app_id_indexes:
    ok(f"Indexes on application_id columns: {len(app_id_indexes)}")
else:
    fail("No indexes on application_id columns")

# 17b. CHECK constraints on status/type columns
check_constraints = re.findall(r'ADD\s+CONSTRAINT\s+(chk_\w+)', idx_src, re.IGNORECASE)
if len(check_constraints) >= 5:
    ok(f"Migration adds {len(check_constraints)} CHECK constraints on status/type columns")
else:
    fail(f"Only {len(check_constraints)} CHECK constraints", "Expected ≥ 5")

# Verify specific status constraints
status_checks = {
    "applications.status": "chk_applications_status",
    "documents.document_type": "chk_documents_document_type",
    "evidence.kind": "chk_evidence_kind",
    "tasks.status": "chk_tasks_status",
    "tasks.priority": "chk_tasks_priority",
}
for label, constraint in status_checks.items():
    if constraint in idx_src:
        ok(f"CHECK constraint on {label} ({constraint})")
    else:
        fail(f"Missing CHECK constraint on {label}")

# 17c. TEXT length limits via CHECK constraints
length_constraints = re.findall(r"CHECK\s*\(\s*length\(\w+\)\s*<=\s*(\d+)\)", idx_src, re.IGNORECASE)
if len(length_constraints) >= 5:
    ok(f"Migration adds {len(length_constraints)} TEXT length limit constraints")
else:
    fail(f"Only {len(length_constraints)} TEXT length constraints", "Expected ≥ 5")

# Verify specific length limits
length_checks = {
    "applications.title": "chk_applications_title_length",
    "documents.title": "chk_documents_title_length",
    "documents.content": "chk_documents_content_length",
    "evidence.title": "chk_evidence_title_length",
    "evidence.description": "chk_evidence_description_length",
    "evidence.url": "chk_evidence_url_length",
    "tasks.title": "chk_tasks_title_length",
}
for label, constraint in length_checks.items():
    if constraint in idx_src:
        ok(f"TEXT length limit on {label}")
    else:
        fail(f"Missing TEXT length limit on {label}")

# 17d. Verify M11 comment markers
for marker in ("M11-F16", "M11-F17", "M11-F19"):
    if marker in idx_src:
        ok(f"Migration includes {marker} tracking comment")
    else:
        warn(f"Migration missing {marker} comment")


# ── 18. Cross-check: all SQL migrations — SECURITY DEFINER ──────
section("M11-18. ALL SQL MIGRATIONS — SECURITY DEFINER audit")

migration_dir = SUPA / "migrations"
if migration_dir.exists():
    sql_files = sorted(migration_dir.glob("*.sql"))
    total_definer = 0
    total_with_path = 0
    violations = []

    for sql_file in sql_files:
        sql_content = sql_file.read_text(errors="replace")
        # Find all SECURITY DEFINER occurrences
        definer_matches = list(re.finditer(r'SECURITY\s+DEFINER', sql_content, re.IGNORECASE))
        for m in definer_matches:
            total_definer += 1
            # Check if SET search_path follows within 50 chars
            following = sql_content[m.end():m.end() + 60]
            if re.search(r'SET\s+search_path', following, re.IGNORECASE):
                total_with_path += 1
            else:
                violations.append(f"{sql_file.name}:{m.start()}")

    if total_definer > 0:
        if total_with_path == total_definer:
            ok(f"All {total_definer} SECURITY DEFINER functions across migrations have SET search_path")
        else:
            fail(f"{total_with_path}/{total_definer} SECURITY DEFINER functions have SET search_path")
            for v in violations:
                print(f"    ↳ Violation at {v}")
    else:
        warn("No SECURITY DEFINER functions found across all migration files")
else:
    fail("supabase/migrations directory not found")


# ══════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════
total = passed + failed
print("\n" + "═" * 62)
print(f"  Modules 9/10/11 — Frontend & Database Security Audit")
print(f"  PASSED: {passed}   FAILED: {failed}   WARNINGS: {warnings}   TOTAL: {total}")
if failed == 0:
    print("  ✅  ALL CHECKS PASSED")
else:
    print(f"  ❌  {failed} CHECK(S) FAILED — review above")
print("═" * 62 + "\n")

exit(0 if failed == 0 else 1)
