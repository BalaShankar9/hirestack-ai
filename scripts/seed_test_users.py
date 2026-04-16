#!/usr/bin/env python3
"""
HireStack AI — Test User Seed Script

Creates multiple test user personas in Supabase for thorough manual and
automated testing.  Each persona represents a distinct user segment so that
every feature surface can be exercised.

Usage:
    # Set required env vars (or edit the defaults below)
    export SUPABASE_URL="https://your-project.supabase.co"
    export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"

    python scripts/seed_test_users.py

    # To delete the test users afterwards:
    python scripts/seed_test_users.py --cleanup
"""

import json
import os
import sys
import requests

# ── Configuration ────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SERVICE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")
    sys.exit(1)

# ── Test Personas ────────────────────────────────────────────────────────────
# Each persona gets a unique email, password, and profile data.
# Passwords follow Supabase default policy: ≥6 chars.
# This is a hardcoded test-only password — never use in production.

TEST_PASSWORD = "TestPass!2026"

PERSONAS = [
    {
        "email": "sarah.swe@hirestack.test",
        "full_name": "Sarah Chen",
        "role": "Senior Software Engineer",
        "description": "Core happy-path user — new application, generation, workspace, export",
        "profile": {
            "job_title": "Senior Software Engineer",
            "years_experience": 5,
            "skills": ["Python", "TypeScript", "React", "FastAPI", "AWS", "Docker"],
            "summary": "5 years building scalable web applications and microservices.",
        },
        "sample_jd": (
            "We are looking for a Senior Software Engineer with 5+ years of "
            "experience building scalable backend services. Must have strong "
            "experience with Python, FastAPI, PostgreSQL, and cloud platforms "
            "(AWS/GCP). Experience with AI/ML pipelines is a strong plus."
        ),
        "sample_resume": (
            "Sarah Chen — Senior Software Engineer\n"
            "5 years at TechCorp building Python microservices on AWS.\n"
            "Led migration from monolith to FastAPI-based microservices.\n"
            "Reduced API latency by 40% through async optimization.\n"
            "Built ML inference pipeline serving 10K req/s.\n"
            "BSc Computer Science, Stanford 2019.\n"
            "Skills: Python, FastAPI, PostgreSQL, AWS, Docker, Kubernetes, "
            "TensorFlow, Redis, CI/CD, Agile."
        ),
    },
    {
        "email": "marcus.career@hirestack.test",
        "full_name": "Marcus Rivera",
        "role": "Career Changer (Teacher → PM)",
        "description": "ATS scanner, evidence vault, gap analysis focus",
        "profile": {
            "job_title": "Product Manager",
            "years_experience": 2,
            "skills": ["Project Management", "Stakeholder Communication", "Data Analysis"],
            "summary": "Former high school teacher transitioning to product management.",
        },
        "sample_jd": (
            "Product Manager role at a fast-growing SaaS company. You will "
            "own the product roadmap, work with engineering and design teams, "
            "and drive user research. 3+ years PM experience preferred. "
            "Experience with agile methodologies required."
        ),
        "sample_resume": (
            "Marcus Rivera — Aspiring Product Manager\n"
            "8 years as high school math teacher, 2 years as associate PM.\n"
            "Led school-wide tech adoption project (500 students).\n"
            "Completed Google PM Certificate.\n"
            "BA Education, UC Berkeley 2014.\n"
            "Skills: Project Management, Stakeholder Communication, "
            "Data Analysis, Jira, Figma, Agile."
        ),
    },
    {
        "email": "priya.newgrad@hirestack.test",
        "full_name": "Priya Patel",
        "role": "New Graduate",
        "description": "Interview prep, learning challenges, salary coach",
        "profile": {
            "job_title": "Junior Software Developer",
            "years_experience": 0,
            "skills": ["Python", "Java", "SQL", "Git"],
            "summary": "Recent CS graduate looking for first full-time role.",
        },
        "sample_jd": (
            "Junior Software Developer position. We are looking for a recent "
            "graduate with strong fundamentals in data structures, algorithms, "
            "and web development. Knowledge of Python or Java required. "
            "Excellent mentorship program provided."
        ),
        "sample_resume": (
            "Priya Patel — Junior Developer\n"
            "BSc Computer Science, Georgia Tech 2026.\n"
            "3 internships: Google (SWE intern), Stripe (Backend), local startup.\n"
            "Built capstone project: ML-powered study planner (React + Python).\n"
            "Skills: Python, Java, SQL, Git, React, Docker."
        ),
    },
    {
        "email": "james.recruiter@hirestack.test",
        "full_name": "James O'Brien",
        "role": "Recruiter / Org Admin",
        "description": "Candidate pipeline, team management, billing, org settings",
        "profile": {
            "job_title": "Technical Recruiter",
            "years_experience": 7,
            "skills": ["Talent Acquisition", "ATS Systems", "Employer Branding"],
            "summary": "Technical recruiter managing engineering hiring pipeline.",
        },
        "sample_jd": (
            "Technical Recruiter at a Series B startup. You will source, "
            "screen, and close engineering candidates. Must have experience "
            "with ATS systems and technical phone screens. "
            "3+ years recruiting for software engineering roles."
        ),
        "sample_resume": (
            "James O'Brien — Technical Recruiter\n"
            "7 years in technical recruiting at FAANG and startups.\n"
            "Filled 200+ engineering roles across 3 companies.\n"
            "Built diversity hiring program (40% increase in URM hires).\n"
            "BA Psychology, Boston University 2017.\n"
            "Skills: Lever, Greenhouse, LinkedIn Recruiter, Boolean Search."
        ),
    },
    {
        "email": "aisha.freelancer@hirestack.test",
        "full_name": "Aisha Okafor",
        "role": "Freelance Designer",
        "description": "A/B lab, document variants, export formats",
        "profile": {
            "job_title": "UX/UI Designer",
            "years_experience": 4,
            "skills": ["Figma", "User Research", "Design Systems", "Prototyping"],
            "summary": "Freelance UX designer specializing in SaaS products.",
        },
        "sample_jd": (
            "UX Designer at a health-tech startup. You will lead user research, "
            "create wireframes and prototypes, and build our design system. "
            "4+ years experience in product design. Figma proficiency required. "
            "Portfolio showcasing SaaS or health-tech work preferred."
        ),
        "sample_resume": (
            "Aisha Okafor — UX/UI Designer\n"
            "4 years freelance design for SaaS clients.\n"
            "Designed onboarding flow that improved activation by 35%.\n"
            "Created design systems for 3 products (50+ components).\n"
            "BFA Graphic Design, Parsons 2020.\n"
            "Skills: Figma, Sketch, User Research, Prototyping, Design Systems."
        ),
    },
]

# ── Helpers ──────────────────────────────────────────────────────────────────

SB_ADMIN_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}


def create_user(email: str, password: str, full_name: str) -> dict | None:
    """Create a Supabase auth user via the Admin API."""
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=SB_ADMIN_HEADERS,
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name},
        },
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    if resp.status_code == 422 and "already been registered" in resp.text:
        print(f"  ℹ  User {email} already exists — skipping creation")
        # Look up existing user
        list_resp = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=SB_ADMIN_HEADERS,
            timeout=15,
        )
        if list_resp.status_code == 200:
            users = list_resp.json().get("users", [])
            for u in users:
                if u.get("email") == email:
                    return u
        return None
    print(f"  ✗ Failed to create {email}: {resp.status_code} — {resp.text[:200]}")
    return None


def insert_profile(user_id: str, profile_data: dict) -> bool:
    """Insert a user profile row in the profiles table (upsert)."""
    row = {
        "user_id": user_id,
        "career_summary": profile_data.get("summary", ""),
        "primary_skills": profile_data.get("skills", []),
        "years_experience": profile_data.get("years_experience", 0),
        "desired_role": profile_data.get("job_title", ""),
    }
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers={**SB_ADMIN_HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"},
        json=row,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return True
    # Profile table might not have these columns — that's okay
    if resp.status_code == 400:
        print(f"  ⚠  Profile insert skipped (schema mismatch): {resp.text[:100]}")
        return False
    print(f"  ✗ Profile insert failed: {resp.status_code} — {resp.text[:200]}")
    return False


def create_sample_application(user_id: str, persona: dict) -> str | None:
    """Create a sample application for the user."""
    row = {
        "user_id": user_id,
        "title": f"{persona['profile']['job_title']} at TestCo",
        "status": "active",
        "confirmed_facts": {
            "company": "TestCo",
            "jobTitle": persona["profile"]["job_title"],
            "jdText": persona.get("sample_jd", ""),
            "resumeText": persona.get("sample_resume", ""),
        },
    }
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/applications",
        headers={**SB_ADMIN_HEADERS, "Prefer": "return=representation"},
        json=row,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        if isinstance(data, list):
            data = data[0]
        return data.get("id")
    print(f"  ⚠  Application insert skipped: {resp.status_code} — {resp.text[:150]}")
    return None


def delete_user(email: str) -> bool:
    """Delete a Supabase auth user by email (admin API)."""
    # First look up the user
    list_resp = requests.get(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=SB_ADMIN_HEADERS,
        timeout=15,
    )
    if list_resp.status_code != 200:
        return False

    users = list_resp.json().get("users", [])
    for u in users:
        if u.get("email") == email:
            uid = u["id"]
            del_resp = requests.delete(
                f"{SUPABASE_URL}/auth/v1/admin/users/{uid}",
                headers=SB_ADMIN_HEADERS,
                timeout=15,
            )
            return del_resp.status_code in (200, 204)
    return False


# ── Main ─────────────────────────────────────────────────────────────────────

def seed():
    """Create all test personas."""
    print("=" * 60)
    print("HireStack AI — Seeding Test Users")
    print("=" * 60)
    print(f"Supabase: {SUPABASE_URL}")
    print(f"Personas: {len(PERSONAS)}\n")

    created = []
    for i, persona in enumerate(PERSONAS, 1):
        print(f"[{i}/{len(PERSONAS)}] {persona['full_name']} ({persona['role']})")
        print(f"  Email: {persona['email']}")

        user = create_user(persona["email"], TEST_PASSWORD, persona["full_name"])
        if not user:
            continue

        uid = user.get("id")
        print(f"  ✓ User ID: {uid}")

        # Insert profile
        insert_profile(uid, persona["profile"])

        # Create sample application
        app_id = create_sample_application(uid, persona)
        if app_id:
            print(f"  ✓ Sample application: {app_id}")

        created.append({
            "email": persona["email"],
            "password": TEST_PASSWORD,
            "name": persona["full_name"],
            "role": persona["role"],
            "uid": uid,
        })
        print()

    # Summary
    print("=" * 60)
    print(f"Created {len(created)}/{len(PERSONAS)} test users\n")
    print("Test Credentials:")
    print("-" * 60)
    for u in created:
        print(f"  {u['email']}")
        print(f"    Name: {u['name']} | Role: {u['role']}")
    print("-" * 60)
    print("\nAll users use the password defined in TEST_PASSWORD variable.")
    print("\nYou can now log in to HireStack AI with any of these accounts")
    print("to test different user workflows and features.")


def cleanup():
    """Delete all test personas."""
    print("=" * 60)
    print("HireStack AI — Cleaning Up Test Users")
    print("=" * 60)

    for persona in PERSONAS:
        email = persona["email"]
        ok = delete_user(email)
        status = "✓ Deleted" if ok else "✗ Not found / failed"
        print(f"  {status}: {email}")

    print("\nCleanup complete.")


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        seed()
