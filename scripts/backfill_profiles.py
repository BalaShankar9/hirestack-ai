#!/usr/bin/env python3
"""
HireStack AI — Profile Backfill Script
Upgrades existing profile rows to include:
  - profile_version (set to 1 if missing)
  - universal_docs_version (set to 0 if missing)
  - social_links (normalised from contact_info if missing)
  - completeness_score (recomputed)

Usage:
  python scripts/backfill_profiles.py [--dry-run]
"""
import os, sys, json, argparse

# Allow importing from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SERVICE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars before running.")
    sys.exit(1)

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Mirror of backend COMPLETENESS_WEIGHTS
COMPLETENESS_WEIGHTS = {
    "personal_info": 15,
    "experience": 25,
    "education": 15,
    "skills": 20,
    "certifications": 10,
    "projects": 10,
    "social_links": 5,
}


def compute_completeness(profile: dict) -> int:
    """Recompute completeness score (mirrors ProfileService.compute_completeness)."""
    score = 0
    if profile.get("name") and profile.get("title"):
        score += COMPLETENESS_WEIGHTS["personal_info"]
    elif profile.get("name") or profile.get("title"):
        score += COMPLETENESS_WEIGHTS["personal_info"] // 2

    exp = profile.get("experience") or []
    if isinstance(exp, list) and len(exp) > 0:
        score += COMPLETENESS_WEIGHTS["experience"]
    edu = profile.get("education") or []
    if isinstance(edu, list) and len(edu) > 0:
        score += COMPLETENESS_WEIGHTS["education"]
    skills = profile.get("skills") or []
    if isinstance(skills, list) and len(skills) > 0:
        score += COMPLETENESS_WEIGHTS["skills"]
    certs = profile.get("certifications") or []
    if isinstance(certs, list) and len(certs) > 0:
        score += COMPLETENESS_WEIGHTS["certifications"]
    projects = profile.get("projects") or []
    if isinstance(projects, list) and len(projects) > 0:
        score += COMPLETENESS_WEIGHTS["projects"]
    sl = profile.get("social_links") or {}
    if isinstance(sl, dict) and any(
        (v.get("url") if isinstance(v, dict) else v)
        for v in sl.values()
    ):
        score += COMPLETENESS_WEIGHTS["social_links"]
    return min(score, 100)


def extract_social_links(profile: dict) -> dict:
    """Build normalised social_links from contact_info fallback."""
    existing = profile.get("social_links")
    if existing and isinstance(existing, dict) and any(existing.values()):
        return existing  # already populated

    contact = profile.get("contact_info") or {}
    links: dict = {}
    for key in ("linkedin", "github", "website", "twitter"):
        url = contact.get(key, "")
        if url:
            links[key] = url
    # Also check legacy social_connections
    conns = contact.get("social_connections") or {}
    for key, data in conns.items():
        if key not in links:
            url_val = data.get("url", "") if isinstance(data, dict) else ""
            if url_val:
                links[key] = {
                    "url": url_val,
                    "status": data.get("status", "connected") if isinstance(data, dict) else "none",
                    "data": data.get("data", {}) if isinstance(data, dict) else {},
                    "connected_at": data.get("connected_at") if isinstance(data, dict) else None,
                }
    return links


def fetch_all_profiles() -> list:
    """Fetch all profiles from Supabase."""
    profiles = []
    offset = 0
    batch = 100
    while True:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles?select=*&order=created_at.asc&offset={offset}&limit={batch}",
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        profiles.extend(page)
        offset += batch
        if len(page) < batch:
            break
    return profiles


def update_profile(profile_id: str, patch: dict, dry_run: bool) -> bool:
    if dry_run:
        return True
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{profile_id}",
        headers=HEADERS,
        json=patch,
        timeout=15,
    )
    return resp.status_code < 300


def main():
    parser = argparse.ArgumentParser(description="Backfill profiles with nexus fields")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without applying")
    args = parser.parse_args()

    print(f"Fetching all profiles from {SUPABASE_URL}...")
    profiles = fetch_all_profiles()
    print(f"Found {len(profiles)} profiles")

    updated = 0
    skipped = 0

    for p in profiles:
        pid = p["id"]
        patch: dict = {}

        # 1. profile_version
        if not p.get("profile_version"):
            patch["profile_version"] = 1

        # 2. universal_docs_version
        if p.get("universal_docs_version") is None:
            has_docs = bool(p.get("universal_documents"))
            patch["universal_docs_version"] = p.get("profile_version", 1) if has_docs else 0

        # 3. social_links
        current_sl = p.get("social_links")
        if not current_sl or (isinstance(current_sl, dict) and not any(current_sl.values())):
            new_sl = extract_social_links(p)
            if new_sl:
                patch["social_links"] = new_sl

        # 4. completeness_score
        merged = {**p, **patch}  # apply pending patch for accurate scoring
        new_score = compute_completeness(merged)
        old_score = p.get("completeness_score")
        if old_score is None or abs(new_score - (old_score or 0)) > 2:
            patch["completeness_score"] = new_score

        if not patch:
            skipped += 1
            continue

        label = f"  [{pid[:8]}] {p.get('name', 'unnamed')}"
        if args.dry_run:
            print(f"{label} → WOULD UPDATE: {json.dumps(patch, default=str)}")
        else:
            ok = update_profile(pid, patch, dry_run=False)
            status = "OK" if ok else "FAIL"
            print(f"{label} → {status}: {list(patch.keys())}")

        updated += 1

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"\nDone ({mode}). Updated: {updated}, Skipped (already current): {skipped}")


if __name__ == "__main__":
    main()
