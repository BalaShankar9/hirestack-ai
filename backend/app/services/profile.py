"""
Profile Service
Handles resume upload, parsing, profile management, universal documents, and career intelligence.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import structlog

from app.core.database import get_db, TABLES, SupabaseDB
from app.services.file_parser import FileParser
from ai_engine.client import AIClient
from ai_engine.chains.role_profiler import RoleProfilerChain

logger = structlog.get_logger()

MAX_RESUME_SIZE = 50 * 1024  # 50 KB of UTF-8 encoded text

# Completeness weights per section (must sum to 100)
COMPLETENESS_WEIGHTS = {
    "personal_info": 15,
    "experience": 25,
    "education": 15,
    "skills": 20,
    "certifications": 10,
    "projects": 10,
    "social_links": 5,
}


class ProfileService:
    """Service for profile operations."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.file_parser = FileParser()
        self.ai_client = AIClient()

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def create_from_upload(
        self,
        user_id: str,
        file_contents: bytes,
        file_name: str,
        file_type: str,
        is_primary: bool = False,
    ) -> Dict[str, Any]:
        """Create a profile from uploaded resume file."""
        raw_text = await self.file_parser.extract_text(file_contents, file_type)

        if not raw_text.strip():
            raise ValueError("Resume text cannot be empty")
        if len(raw_text.encode("utf-8")) > MAX_RESUME_SIZE:
            raise ValueError(f"Resume text exceeds maximum size of {MAX_RESUME_SIZE // 1024}KB")

        profiler = RoleProfilerChain(self.ai_client)
        parsed_data = await profiler.parse_resume(raw_text)

        if is_primary:
            existing_profiles = await self.get_user_profiles(user_id)
            for profile in existing_profiles:
                if profile.get("is_primary"):
                    await self.db.update(TABLES["profiles"], profile["id"], {"is_primary": False})

        has_profiles = await self._has_profiles(user_id)

        # Extract social links from contact info
        contact = parsed_data.get("contact_info") or {}
        social_links = {
            "linkedin": contact.get("linkedin", ""),
            "github": contact.get("github", ""),
            "website": contact.get("website", ""),
        }

        profile_data = {
            "user_id": user_id,
            "name": parsed_data.get("name"),
            "title": parsed_data.get("title"),
            "summary": parsed_data.get("summary"),
            "raw_resume_text": raw_text,
            "file_type": file_type,
            "parsed_data": parsed_data,
            "contact_info": contact,
            "skills": parsed_data.get("skills", []),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "certifications": parsed_data.get("certifications", []),
            "projects": parsed_data.get("projects", []),
            "languages": parsed_data.get("languages", []),
            "achievements": parsed_data.get("achievements", []),
            "is_primary": is_primary or not has_profiles,
            "social_links": social_links,
            "profile_version": 1,
            "universal_docs_version": 0,
        }

        doc_id = await self.db.create(TABLES["profiles"], profile_data)
        profile = await self.db.get(TABLES["profiles"], doc_id)

        # Compute and persist completeness score
        completeness = self.compute_completeness(profile)
        await self.db.update(TABLES["profiles"], doc_id, {"completeness_score": completeness["score"]})
        profile["completeness_score"] = completeness["score"]

        return profile

    async def _has_profiles(self, user_id: str) -> bool:
        profiles = await self.db.query(TABLES["profiles"], filters=[("user_id", "==", user_id)], limit=1)
        return len(profiles) > 0

    async def get_user_profiles(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.db.query(
            TABLES["profiles"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )

    async def get_primary_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        profiles = await self.db.query(
            TABLES["profiles"],
            filters=[("user_id", "==", user_id), ("is_primary", "==", True)],
            limit=1,
        )
        return profiles[0] if profiles else None

    async def get_profile(self, profile_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        profile = await self.db.get(TABLES["profiles"], profile_id)
        if profile and profile.get("user_id") == user_id:
            return profile
        return None

    async def update_profile(
        self, profile_id: str, user_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return None

        # Increment profile version on every edit
        current_version = profile.get("profile_version") or 1
        update_data["profile_version"] = current_version + 1

        await self.db.update(TABLES["profiles"], profile_id, update_data)
        updated = await self.db.get(TABLES["profiles"], profile_id)

        # Recompute and persist completeness score
        completeness = self.compute_completeness(updated)
        await self.db.update(TABLES["profiles"], profile_id, {"completeness_score": completeness["score"]})
        updated["completeness_score"] = completeness["score"]

        return updated

    async def delete_profile(self, profile_id: str, user_id: str) -> bool:
        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return False
        await self.db.delete(TABLES["profiles"], profile_id)
        return True

    async def set_primary(self, profile_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        existing_profiles = await self.get_user_profiles(user_id)
        for profile in existing_profiles:
            if profile.get("is_primary"):
                await self.db.update(TABLES["profiles"], profile["id"], {"is_primary": False})

        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return None

        await self.db.update(TABLES["profiles"], profile_id, {"is_primary": True})
        return await self.db.get(TABLES["profiles"], profile_id)

    async def reparse_profile(self, profile_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        profile = await self.get_profile(profile_id, user_id)
        if not profile or not profile.get("raw_resume_text"):
            return None

        raw_text = profile["raw_resume_text"]
        if not raw_text.strip():
            raise ValueError("Resume text cannot be empty")

        profiler = RoleProfilerChain(self.ai_client)
        parsed_data = await profiler.parse_resume(raw_text)

        contact = parsed_data.get("contact_info") or {}
        social_links = {
            "linkedin": contact.get("linkedin", ""),
            "github": contact.get("github", ""),
            "website": contact.get("website", ""),
        }

        update_data = {
            "name": parsed_data.get("name"),
            "title": parsed_data.get("title"),
            "summary": parsed_data.get("summary"),
            "parsed_data": parsed_data,
            "contact_info": contact,
            "skills": parsed_data.get("skills", []),
            "experience": parsed_data.get("experience", []),
            "education": parsed_data.get("education", []),
            "certifications": parsed_data.get("certifications", []),
            "projects": parsed_data.get("projects", []),
            "languages": parsed_data.get("languages", []),
            "achievements": parsed_data.get("achievements", []),
            "social_links": social_links,
        }

        return await self.update_profile(profile_id, user_id, update_data)

    # ── Completeness ──────────────────────────────────────────────────────

    def compute_completeness(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Compute profile completeness score (0-100) with per-section breakdown."""
        sections: Dict[str, float] = {}

        # Personal info: name, title, summary, contact email/phone
        personal_fields = [
            bool(profile.get("name")),
            bool(profile.get("title")),
            bool(profile.get("summary")),
            bool((profile.get("contact_info") or {}).get("email")),
            bool((profile.get("contact_info") or {}).get("phone")),
        ]
        sections["personal_info"] = sum(personal_fields) / len(personal_fields) * 100

        # Experience
        exp = profile.get("experience") or []
        sections["experience"] = min(100, len(exp) * 33) if exp else 0

        # Education
        edu = profile.get("education") or []
        sections["education"] = min(100, len(edu) * 50) if edu else 0

        # Skills
        skills = profile.get("skills") or []
        sections["skills"] = min(100, len(skills) * 10) if skills else 0

        # Certifications
        certs = profile.get("certifications") or []
        sections["certifications"] = min(100, len(certs) * 33) if certs else 0

        # Projects
        projects = profile.get("projects") or []
        sections["projects"] = min(100, len(projects) * 25) if projects else 0

        # Social links
        social = profile.get("social_links") or {}
        social_count = sum(1 for v in social.values() if v)
        sections["social_links"] = min(100, social_count * 33) if social_count else 0

        # Weighted total
        score = sum(sections[k] * COMPLETENESS_WEIGHTS[k] / 100 for k in COMPLETENESS_WEIGHTS)
        score = round(min(100, max(0, score)))

        # Suggestions
        suggestions = []
        if sections["personal_info"] < 100:
            suggestions.append("Complete your personal information (name, title, summary, email, phone)")
        if sections["experience"] < 50:
            suggestions.append("Add your work experience")
        if sections["education"] < 50:
            suggestions.append("Add your education details")
        if sections["skills"] < 50:
            suggestions.append("Add more skills to showcase your expertise")
        if sections["certifications"] == 0:
            suggestions.append("Add certifications to strengthen your profile")
        if sections["projects"] == 0:
            suggestions.append("Add projects to demonstrate your capabilities")
        if sections["social_links"] < 50:
            suggestions.append("Add your LinkedIn and GitHub profiles")

        return {"score": score, "sections": sections, "suggestions": suggestions}

    # ── Resume Worth Score ────────────────────────────────────────────────

    async def compute_resume_worth(self, user_id: str) -> Dict[str, Any]:
        """Compute a resume worth score (0-100) based on profile strength."""
        profile = await self.get_primary_profile(user_id)
        if not profile:
            return {"score": 0, "breakdown": {}, "label": "No Profile", "suggestions": []}

        skills = profile.get("skills") or []
        experience = profile.get("experience") or []
        certs = profile.get("certifications") or []
        projects = profile.get("projects") or []
        education = profile.get("education") or []

        # Skills depth: expert/advanced skills worth more
        level_scores = {"expert": 4, "advanced": 3, "intermediate": 2, "beginner": 1}
        skill_points = sum(level_scores.get((s.get("level") or "intermediate").lower(), 2) for s in skills if isinstance(s, dict))
        skills_depth = min(100, skill_points * 3)

        # Experience breadth
        total_years = 0
        for exp in experience:
            if isinstance(exp, dict) and exp.get("start_date"):
                try:
                    start_year = int(str(exp["start_date"])[:4])
                    end_year = int(str(exp.get("end_date", "2026"))[:4]) if exp.get("end_date") else 2026
                    total_years += max(0, end_year - start_year)
                except (ValueError, TypeError):
                    total_years += 1
        experience_breadth = min(100, total_years * 8)

        # Certifications
        cert_score = min(100, len(certs) * 25)

        # Projects
        project_score = min(100, len(projects) * 20)

        # Education
        edu_score = min(100, len(education) * 40)

        # Evidence from vault
        evidence = await self.db.query(TABLES["evidence"], filters=[("user_id", "==", user_id)])
        evidence_score = min(100, len(evidence) * 15)

        # Weighted total
        breakdown = {
            "skills_depth": round(skills_depth),
            "experience_breadth": round(experience_breadth),
            "certifications": round(cert_score),
            "projects": round(project_score),
            "education": round(edu_score),
            "evidence_strength": round(evidence_score),
        }

        score = round(
            skills_depth * 0.25
            + experience_breadth * 0.25
            + cert_score * 0.15
            + project_score * 0.15
            + edu_score * 0.10
            + evidence_score * 0.10
        )
        score = min(100, max(0, score))

        if score >= 85:
            label = "Exceptional"
        elif score >= 65:
            label = "Strong"
        elif score >= 40:
            label = "Developing"
        else:
            label = "Getting Started"

        # Update cached score
        try:
            await self.db.update(TABLES["profiles"], profile["id"], {"resume_worth_score": score})
        except Exception:
            pass

        return {"score": score, "breakdown": breakdown, "label": label}

    # ── Aggregate Gap Analysis ────────────────────────────────────────────

    async def aggregate_gap_analysis(self, user_id: str) -> Dict[str, Any]:
        """Aggregate gap analysis across all user applications."""
        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
        )

        skill_freq: Dict[str, Dict[str, Any]] = {}
        strength_freq: Dict[str, int] = {}

        for app in applications:
            gaps = app.get("gaps") or {}

            # Count missing skills
            for gap in gaps.get("skill_gaps") or gaps.get("missingKeywords") or []:
                if isinstance(gap, dict):
                    skill = gap.get("skill") or gap.get("keyword") or ""
                    if skill:
                        if skill not in skill_freq:
                            skill_freq[skill] = {"frequency": 0, "severities": []}
                        skill_freq[skill]["frequency"] += 1
                        severity = gap.get("gap_severity") or gap.get("importance") or "medium"
                        skill_freq[skill]["severities"].append(severity)

            # Count strengths
            for s in gaps.get("strengths") or []:
                if isinstance(s, dict):
                    area = s.get("area", "")
                    if area:
                        strength_freq[area] = strength_freq.get(area, 0) + 1

        # Sort by frequency
        most_missing = sorted(
            [
                {"skill": k, "frequency": v["frequency"], "avg_severity": max(set(v["severities"]), key=v["severities"].count) if v["severities"] else "medium"}
                for k, v in skill_freq.items()
            ],
            key=lambda x: x["frequency"],
            reverse=True,
        )[:15]

        strongest = sorted(
            [{"area": k, "frequency": v} for k, v in strength_freq.items()],
            key=lambda x: x["frequency"],
            reverse=True,
        )[:10]

        # Trending skills (most demanded across applications)
        trending = most_missing[:8]

        # Learning recommendations
        total_apps = len(applications) or 1
        recommended_learning = [
            {
                "skill": item["skill"],
                "appears_in_jobs": item["frequency"],
                "total_jobs": total_apps,
                "priority": "high" if item["frequency"] / total_apps > 0.5 else "medium",
            }
            for item in most_missing[:10]
        ]

        return {
            "most_missing_skills": most_missing,
            "strongest_areas": strongest,
            "recommended_learning": recommended_learning,
            "trending_skills": trending,
            "total_applications_analyzed": len(applications),
        }

    # ── Skills Augmentation ─────────────────────────────────────────────

    # Common aliases for language/skill name normalization
    _LANG_ALIASES = {
        "js": "JavaScript", "ts": "TypeScript", "py": "Python",
        "rb": "Ruby", "cs": "C#", "cpp": "C++", "rs": "Rust",
        "kt": "Kotlin", "objective-c": "Objective-C",
    }

    async def augment_skills_from_connections(self, profile_id: str, user_id: str) -> Dict[str, Any]:
        """Merge skills from GitHub connections into the profile skills array."""
        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return {"added": 0, "skills": []}

        existing_skills = profile.get("skills") or []
        # Build a set of normalized existing skill names
        existing_names = set()
        for s in existing_skills:
            if isinstance(s, dict):
                existing_names.add(s.get("name", "").lower().strip())

        # Tag existing skills with source if not tagged
        for s in existing_skills:
            if isinstance(s, dict) and not s.get("source"):
                s["source"] = "resume"

        added = 0
        # Get GitHub connection data
        contact = profile.get("contact_info") or {}
        connections = contact.get("social_connections") or {}
        github_data = (connections.get("github") or {}).get("data") or {}

        for lang in github_data.get("top_languages") or []:
            normalized = self._LANG_ALIASES.get(lang.lower(), lang)
            if normalized.lower().strip() not in existing_names:
                existing_skills.append({
                    "name": normalized,
                    "level": "intermediate",
                    "category": "Programming Languages",
                    "source": "github",
                })
                existing_names.add(normalized.lower().strip())
                added += 1

        # Add notable repos as project-related skills
        for repo in (github_data.get("top_repos") or [])[:3]:
            if isinstance(repo, dict) and repo.get("language"):
                lang = repo["language"]
                normalized = self._LANG_ALIASES.get(lang.lower(), lang)
                if normalized.lower().strip() not in existing_names:
                    existing_skills.append({
                        "name": normalized,
                        "level": "intermediate",
                        "category": "Programming Languages",
                        "source": "github",
                    })
                    existing_names.add(normalized.lower().strip())
                    added += 1

        if added > 0:
            await self.update_profile(profile_id, user_id, {"skills": existing_skills})

        return {"added": added, "skills": existing_skills}

    # ── Market Intelligence ─────────────────────────────────────────────

    async def compute_market_intelligence(self, user_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Generate market intelligence based on user's location, skills, and title."""
        profile = await self.get_primary_profile(user_id)
        if not profile:
            return {"error": "No profile found. Upload a resume first."}

        contact = profile.get("contact_info") or {}
        location = contact.get("location") or ""
        if not location:
            return {"error": "No location set. Add your location in the Profile tab."}

        # Check cache (stored in contact_info.market_intelligence)
        if not force_refresh:
            cached = contact.get("market_intelligence")
            if cached and isinstance(cached, dict):
                cached_at = cached.get("generated_at", "")
                if cached_at:
                    try:
                        gen_time = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                        age_hours = (datetime.now(timezone.utc) - gen_time).total_seconds() / 3600
                        if age_hours < 24:
                            cached["from_cache"] = True
                            return cached
                    except Exception:
                        pass

        skills = profile.get("skills") or []
        skill_names = [s.get("name", "") for s in skills if isinstance(s, dict)][:20]
        title = profile.get("title") or ""

        # Estimate years of experience
        years = 0
        for exp in profile.get("experience") or []:
            if isinstance(exp, dict) and exp.get("start_date"):
                try:
                    start = int(str(exp["start_date"])[:4])
                    end = int(str(exp.get("end_date", "2026"))[:4]) if exp.get("end_date") else 2026
                    years += max(0, end - start)
                except (ValueError, TypeError):
                    years += 1

        from ai_engine.chains.market_intelligence import MarketIntelligenceChain
        chain = MarketIntelligenceChain(self.ai_client)
        result = await chain.analyze(
            location=location,
            title=title,
            skills=skill_names,
            years_experience=years,
        )

        # Cache in contact_info
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["from_cache"] = False
        contact["market_intelligence"] = result
        try:
            await self.db.update(TABLES["profiles"], profile["id"], {"contact_info": contact})
        except Exception:
            pass

        return result

    # ── Universal Documents ───────────────────────────────────────────────

    async def generate_universal_documents(self, profile_id: str, user_id: str) -> Dict[str, Any]:
        """Generate all four universal documents from profile data."""
        from ai_engine.chains.universal_doc_generator import UniversalDocGeneratorChain

        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            raise ValueError("Profile not found")

        # Sync evidence into profile before generating docs
        await self.sync_evidence_to_profile(profile_id, user_id)
        # Re-read profile with merged evidence
        profile = await self.get_profile(profile_id, user_id)

        # Get evidence items for portfolio
        evidence = await self.db.query(
            TABLES["evidence"],
            filters=[("user_id", "==", user_id)],
        )

        chain = UniversalDocGeneratorChain(self.ai_client)
        docs = await chain.generate_all(profile, evidence)

        # Store results and lock docs_version to current profile_version
        docs["generated_at"] = datetime.now(timezone.utc).isoformat()
        profile_version = profile.get("profile_version") or 1
        try:
            await self.db.update(TABLES["profiles"], profile_id, {
                "universal_documents": docs,
                "universal_docs_version": profile_version,
            })
        except Exception:
            logger.warning("universal_docs_store_failed", profile_id=profile_id)

        return docs

    # ── Evidence Sync ─────────────────────────────────────────────────────

    async def get_synced_evidence(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get evidence vault items organized by type for profile sync."""
        evidence = await self.db.query(
            TABLES["evidence"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )

        organized: Dict[str, List[Dict[str, Any]]] = {
            "certifications": [],
            "projects": [],
            "courses": [],
            "awards": [],
            "publications": [],
            "other": [],
        }
        for item in evidence:
            item_type = item.get("type", "other")
            bucket = "certifications" if item_type == "cert" else organized.get(item_type, "other")
            if isinstance(bucket, str):
                organized.setdefault(bucket, []).append(item)
            else:
                bucket.append(item)

        return organized

    async def sync_evidence_to_profile(self, profile_id: str, user_id: str) -> Dict[str, Any]:
        """Merge evidence vault items (certs, projects) into profile without duplication."""
        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return {"merged_certs": 0, "merged_projects": 0}

        evidence = await self.get_synced_evidence(user_id)
        changes = False
        merged_certs = 0
        merged_projects = 0

        # Merge certifications
        existing_certs = profile.get("certifications") or []
        cert_names = {c.get("name", "").lower().strip() for c in existing_certs if isinstance(c, dict)}
        for ev_cert in evidence.get("certifications", []):
            title = (ev_cert.get("title") or "").strip()
            if title and title.lower() not in cert_names:
                existing_certs.append({
                    "name": title,
                    "issuer": ev_cert.get("issuer", ""),
                    "date": ev_cert.get("date", ""),
                    "url": ev_cert.get("url", ""),
                    "source": "evidence",
                })
                cert_names.add(title.lower())
                merged_certs += 1
                changes = True

        # Merge projects
        existing_projects = profile.get("projects") or []
        project_names = {p.get("name", "").lower().strip() for p in existing_projects if isinstance(p, dict)}
        for ev_proj in evidence.get("projects", []):
            title = (ev_proj.get("title") or "").strip()
            if title and title.lower() not in project_names:
                existing_projects.append({
                    "name": title,
                    "description": ev_proj.get("description", ""),
                    "technologies": ev_proj.get("skills", []),
                    "url": ev_proj.get("url", ""),
                    "source": "evidence",
                })
                project_names.add(title.lower())
                merged_projects += 1
                changes = True

        if changes:
            await self.update_profile(profile_id, user_id, {
                "certifications": existing_certs,
                "projects": existing_projects,
            })

        return {"merged_certs": merged_certs, "merged_projects": merged_projects}
