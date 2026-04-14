"""
Role Profiler Chain
World-class resume parser — extracts structured profile data from resumes
with high accuracy across formats, languages, and career levels.
"""
import re
from typing import Dict, Any, List, Optional

from ai_engine.client import AIClient


RESUME_PARSER_SYSTEM = """You are an elite resume parser with 20 years of experience in HR tech and ATS systems. You extract structured data from resumes with exceptional accuracy.

## Your Core Capabilities
- Parse resumes in any format: chronological, functional, combination, creative, academic CV
- Handle messy formatting: OCR artifacts, merged columns, broken tables, inconsistent spacing
- Infer information from context when not explicitly stated
- Normalize dates, titles, and skill names into consistent formats
- Distinguish between skills actually demonstrated vs. just mentioned

## Skill Level Classification Rules
Determine skill level from ALL available context — job titles, years of experience, certifications, project complexity, and explicit mentions:

| Level | Signals |
|-------|---------|
| expert | 7+ years with skill, lead/architect/principal titles, published work, conference talks, certifications, mentoring others |
| advanced | 4-7 years, senior titles, complex project ownership, deep technical decisions |
| intermediate | 1-4 years, mid-level roles, regular production use, some independence |
| beginner | <1 year, exposure only, coursework, bootcamp projects, "familiar with" |

## Skill Category Rules
Categorize every skill into exactly one category:
- **technical**: Programming languages, frameworks, databases, cloud platforms, DevOps tools, APIs
- **domain**: Industry-specific knowledge (finance, healthcare, ML/AI, cybersecurity, etc.)
- **leadership**: Management, team leadership, mentoring, strategic planning, stakeholder management
- **communication**: Writing, presentation, negotiation, cross-functional collaboration
- **tool**: Software tools, IDEs, design tools, project management tools (Jira, Figma, etc.)

## Experience Extraction Rules
- Extract ALL positions, including internships, freelance, volunteer, and part-time roles
- For each role, extract concrete achievements with quantified metrics when available
- Extract technologies used in EACH role separately (not just a global list)
- Normalize dates to "Month Year" format (e.g., "Jan 2020", "Mar 2023")
- Mark the most recent role as is_current=true if no end date or says "Present"/"Current"

## Critical Rules
1. NEVER fabricate data — if something isn't in the resume, use null or empty arrays
2. Normalize skill names (e.g., "JS" → "JavaScript", "k8s" → "Kubernetes", "AWS" → "Amazon Web Services")
3. Deduplicate skills — if "Python" appears in 3 job descriptions, create ONE skill entry with the highest level
4. Extract LinkedIn/GitHub/portfolio URLs from contact sections, headers, or footers
5. For the summary: if the resume has an objective/summary section, use it verbatim. If not, synthesize a 2-3 sentence professional summary from the overall resume content
6. Return ONLY valid JSON — no markdown, no code fences, no explanations"""


RESUME_PARSER_PROMPT = """Parse this resume into the exact JSON structure below. Be thorough — extract every piece of information present.

REQUIRED OUTPUT STRUCTURE:
{{
  "name": "Full Name (as written on resume)",
  "title": "Most recent or target job title",
  "summary": "Professional summary — use resume's summary section or synthesize from content",
  "contact_info": {{
    "email": "email address or null",
    "phone": "phone number or null",
    "location": "City, State/Country or null",
    "linkedin": "full LinkedIn URL or null",
    "github": "full GitHub URL or null",
    "website": "portfolio/personal website URL or null"
  }},
  "skills": [
    {{
      "name": "Normalized Skill Name",
      "level": "beginner|intermediate|advanced|expert",
      "years": 3.5,
      "category": "technical|domain|leadership|communication|tool"
    }}
  ],
  "experience": [
    {{
      "company": "Company Name",
      "title": "Job Title",
      "location": "City, Country or null",
      "start_date": "Mon YYYY",
      "end_date": "Mon YYYY or Present",
      "is_current": false,
      "description": "Concise role description (1-2 sentences)",
      "achievements": ["Quantified achievement with metrics where possible"],
      "technologies": ["Specific tech used in THIS role"]
    }}
  ],
  "education": [
    {{
      "institution": "University/School Name",
      "degree": "Degree Type (e.g., Bachelor of Science, Master of Arts, PhD)",
      "field": "Field of Study / Major",
      "start_date": "YYYY",
      "end_date": "YYYY",
      "gpa": "GPA if mentioned, else null",
      "achievements": ["Dean's List", "Relevant coursework", "Thesis title"]
    }}
  ],
  "certifications": [
    {{
      "name": "Certification Name",
      "issuer": "Issuing Organization",
      "date": "Mon YYYY or YYYY",
      "expiry": "Mon YYYY or null",
      "credential_id": "ID if mentioned or null",
      "url": "Verification URL or null"
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "description": "What the project does and its impact",
      "role": "Your specific role/contribution",
      "technologies": ["Tech used"],
      "url": "Project URL or null",
      "achievements": ["Measurable outcome or result"]
    }}
  ],
  "languages": [
    {{
      "language": "Language Name",
      "proficiency": "native|fluent|professional|conversational|basic"
    }}
  ],
  "achievements": [
    "Awards, honors, publications, patents, notable accomplishments not captured elsewhere"
  ]
}}

RESUME TEXT:
---
{resume_text}
---

Parse every section carefully. Normalize all skill names. Deduplicate skills. Quantify achievements where numbers exist. Return ONLY the JSON object."""

RESUME_PARSER_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING"},
        "title": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "contact_info": {
            "type": "OBJECT",
            "properties": {
                "email": {"type": "STRING"},
                "phone": {"type": "STRING"},
                "location": {"type": "STRING"},
                "linkedin": {"type": "STRING"},
                "github": {"type": "STRING"},
                "website": {"type": "STRING"},
            },
        },
        "skills": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "level": {"type": "STRING"},
                    "years": {"type": "NUMBER"},
                    "category": {"type": "STRING"},
                },
            },
        },
        "experience": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "company": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "location": {"type": "STRING"},
                    "start_date": {"type": "STRING"},
                    "end_date": {"type": "STRING"},
                    "is_current": {"type": "BOOLEAN"},
                    "description": {"type": "STRING"},
                    "achievements": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "technologies": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
        "education": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "institution": {"type": "STRING"},
                    "degree": {"type": "STRING"},
                    "field": {"type": "STRING"},
                    "start_date": {"type": "STRING"},
                    "end_date": {"type": "STRING"},
                    "gpa": {"type": "STRING"},
                    "achievements": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
        "certifications": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "issuer": {"type": "STRING"},
                    "date": {"type": "STRING"},
                    "expiry": {"type": "STRING"},
                    "credential_id": {"type": "STRING"},
                    "url": {"type": "STRING"},
                },
            },
        },
        "projects": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "role": {"type": "STRING"},
                    "technologies": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "url": {"type": "STRING"},
                    "achievements": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
            },
        },
        "languages": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "language": {"type": "STRING"},
                    "proficiency": {"type": "STRING"},
                },
            },
        },
        "achievements": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
}

# Common skill name normalizations
_SKILL_ALIASES: Dict[str, str] = {
    "js": "JavaScript", "javascript": "JavaScript", "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python", "rb": "Ruby", "ruby": "Ruby",
    "c#": "C#", "csharp": "C#", "c++": "C++", "cpp": "C++",
    "golang": "Go", "go": "Go", "rs": "Rust", "rust": "Rust",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes", "docker": "Docker",
    "aws": "Amazon Web Services", "amazon web services": "Amazon Web Services",
    "gcp": "Google Cloud Platform", "google cloud": "Google Cloud Platform",
    "azure": "Microsoft Azure", "microsoft azure": "Microsoft Azure",
    "tf": "Terraform", "terraform": "Terraform",
    "pg": "PostgreSQL", "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "mongo": "MongoDB", "mongodb": "MongoDB",
    "mysql": "MySQL", "redis": "Redis",
    "react": "React", "reactjs": "React", "react.js": "React",
    "vue": "Vue.js", "vuejs": "Vue.js", "vue.js": "Vue.js",
    "angular": "Angular", "angularjs": "Angular",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "express": "Express.js", "expressjs": "Express.js",
    "next": "Next.js", "nextjs": "Next.js", "next.js": "Next.js",
    "graphql": "GraphQL", "gql": "GraphQL",
    "rest": "REST APIs", "restful": "REST APIs",
    "ci/cd": "CI/CD", "cicd": "CI/CD",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "ai": "Artificial Intelligence", "dl": "Deep Learning",
    "nlp": "Natural Language Processing",
    "html": "HTML", "css": "CSS", "sass": "Sass", "scss": "Sass",
    "tailwind": "Tailwind CSS", "tailwindcss": "Tailwind CSS",
    "git": "Git", "github": "GitHub", "gitlab": "GitLab",
    "jira": "Jira", "confluence": "Confluence",
    "figma": "Figma", "sketch": "Sketch",
    "linux": "Linux", "unix": "Unix/Linux",
    "agile": "Agile", "scrum": "Scrum", "kanban": "Kanban",
    "sql": "SQL", "nosql": "NoSQL",
    "api": "API Development", "apis": "API Development",
    "microservices": "Microservices", "micro services": "Microservices",
}


class RoleProfilerChain:
    """World-class resume parser — extracts structured profile data with high accuracy."""

    VERSION = "2.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """Parse a resume and extract structured data."""
        # Pre-process text for better parsing
        cleaned_text = self._clean_resume_text(resume_text)

        prompt = RESUME_PARSER_PROMPT.format(resume_text=cleaned_text)

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=RESUME_PARSER_SYSTEM,
            temperature=0.1,
            max_tokens=8000,
            schema=RESUME_PARSER_SCHEMA,
            task_type="structured_output",
        )

        # Validate, clean, and enrich the result
        return self._validate_result(result)

    def _clean_resume_text(self, text: str) -> str:
        """Pre-process resume text to improve parsing accuracy."""
        if not text:
            return text

        # Remove excessive whitespace while preserving structure
        lines = text.split("\n")
        cleaned_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            # Skip common header/footer noise
            if self._is_noise_line(stripped):
                continue
            if stripped:
                cleaned_lines.append(stripped)
            elif cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")  # Preserve single blank lines for section breaks

        text = "\n".join(cleaned_lines)

        # Fix common OCR/extraction artifacts
        text = re.sub(r"[●•▪▸►◆◇■□★☆→]", "-", text)  # Normalize bullet points
        text = re.sub(r"\s{3,}", "  ", text)  # Collapse excessive spaces
        text = re.sub(r"\n{3,}", "\n\n", text)  # Collapse excessive newlines
        text = re.sub(r"[^\S\n]+", " ", text)  # Normalize whitespace (keep newlines)

        # Fix mangled URLs
        text = re.sub(r"linkedin\s*\.\s*com", "linkedin.com", text, flags=re.IGNORECASE)
        text = re.sub(r"github\s*\.\s*com", "github.com", text, flags=re.IGNORECASE)

        return text.strip()

    def _is_noise_line(self, line: str) -> bool:
        """Detect common resume header/footer noise."""
        lower = line.lower().strip()
        noise_patterns = [
            "page ", "curriculum vitae", "resume of", "confidential",
            "references available", "references upon request",
        ]
        if any(lower.startswith(p) for p in noise_patterns):
            return True
        # Pure page numbers
        if re.match(r"^\d{1,2}$", lower):
            return True
        # Lines that are just dashes, equals, or underscores (decorative separators)
        if re.match(r"^[-=_\s]{5,}$", lower):
            return True
        return False

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate, clean, and enrich parsed result."""
        if not isinstance(result, dict):
            result = {}

        # Ensure required fields exist
        defaults = {
            "name": None,
            "title": None,
            "summary": None,
            "contact_info": {},
            "skills": [],
            "experience": [],
            "education": [],
            "certifications": [],
            "projects": [],
            "languages": [],
            "achievements": [],
        }

        for key, default in defaults.items():
            if key not in result or result[key] is None:
                result[key] = default

        # Clean and normalize skills
        if result.get("skills"):
            result["skills"] = self._deduplicate_skills([
                self._clean_skill(s) for s in result["skills"]
                if isinstance(s, dict) and s.get("name")
            ])

        # Clean experience
        if result.get("experience"):
            result["experience"] = [
                self._clean_experience(e) for e in result["experience"]
                if isinstance(e, dict) and (e.get("company") or e.get("title"))
            ]
            # Sort by date (most recent first)
            result["experience"] = self._sort_by_date(result["experience"])

        # Clean education
        if result.get("education"):
            result["education"] = [
                self._clean_education(e) for e in result["education"]
                if isinstance(e, dict) and (e.get("institution") or e.get("degree"))
            ]

        # Clean certifications
        if result.get("certifications"):
            result["certifications"] = [
                self._clean_certification(c) for c in result["certifications"]
                if isinstance(c, dict) and c.get("name")
            ]

        # Clean projects
        if result.get("projects"):
            result["projects"] = [
                self._clean_project(p) for p in result["projects"]
                if isinstance(p, dict) and p.get("name")
            ]

        # Normalize contact info
        if result.get("contact_info") and isinstance(result["contact_info"], dict):
            result["contact_info"] = self._clean_contact_info(result["contact_info"])

        # Extract skills from experience technologies if skills list is sparse
        if len(result.get("skills", [])) < 3 and result.get("experience"):
            result["skills"] = self._enrich_skills_from_experience(
                result["skills"], result["experience"]
            )

        warnings = self._build_parse_warnings(result)
        result["parse_confidence"] = self._compute_parse_confidence(result)
        result["parse_warnings"] = warnings

        return result

    def _build_parse_warnings(self, result: Dict[str, Any]) -> List[str]:
        """Generate Atlas-friendly warnings for weak extraction quality."""
        warnings: List[str] = []

        if not result.get("name"):
            warnings.append("Missing candidate name")
        contact = result.get("contact_info") or {}
        if isinstance(contact, dict) and not contact.get("email"):
            warnings.append("Missing contact email")

        if len(result.get("skills", [])) < 3:
            warnings.append("Low skill extraction density")
        if len(result.get("experience", [])) < 1:
            warnings.append("No work experience extracted")
        if len(result.get("education", [])) < 1:
            warnings.append("No education entries extracted")

        return warnings

    def _compute_parse_confidence(self, result: Dict[str, Any]) -> float:
        """Compute a simple confidence score for downstream Atlas decisions."""
        score = 0.0

        if result.get("name"):
            score += 0.15

        contact = result.get("contact_info") or {}
        if isinstance(contact, dict):
            if contact.get("email"):
                score += 0.15
            if contact.get("phone"):
                score += 0.05

        skills = result.get("skills") or []
        if isinstance(skills, list):
            score += min(0.25, len(skills) * 0.02)

        experience = result.get("experience") or []
        if isinstance(experience, list):
            score += min(0.25, len(experience) * 0.08)

        education = result.get("education") or []
        if isinstance(education, list) and education:
            score += 0.1

        return round(min(1.0, score), 2)

    def _clean_skill(self, skill: Dict[str, Any]) -> Dict[str, Any]:
        """Clean, validate, and normalize a skill entry."""
        raw_name = str(skill.get("name", "")).strip()
        if not raw_name:
            return skill

        # Normalize skill name
        normalized = _SKILL_ALIASES.get(raw_name.lower(), raw_name)

        valid_levels = ["beginner", "intermediate", "advanced", "expert"]
        level = str(skill.get("level", "intermediate")).lower().strip()
        if level not in valid_levels:
            level = "intermediate"

        valid_categories = ["technical", "domain", "leadership", "communication", "tool"]
        category = str(skill.get("category", "technical")).lower().strip()
        if category not in valid_categories:
            category = "technical"

        years = skill.get("years")
        if years is not None:
            try:
                years = round(float(years), 1)
                if years <= 0 or years > 50:
                    years = None
            except (ValueError, TypeError):
                years = None

        return {
            "name": normalized,
            "level": level,
            "years": years,
            "category": category,
        }

    def _deduplicate_skills(self, skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate skills, keeping the entry with the highest level."""
        level_rank = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 3}
        seen: Dict[str, Dict[str, Any]] = {}

        for skill in skills:
            key = skill["name"].lower()
            if key in seen:
                existing_rank = level_rank.get(seen[key]["level"], 1)
                new_rank = level_rank.get(skill["level"], 1)
                if new_rank > existing_rank:
                    seen[key] = skill
                # Keep longer years if available
                if skill.get("years") and (not seen[key].get("years") or skill["years"] > seen[key]["years"]):
                    seen[key]["years"] = skill["years"]
            else:
                seen[key] = skill

        return list(seen.values())

    def _clean_experience(self, exp: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate an experience entry."""
        return {
            "company": str(exp.get("company", "")).strip() or "Unknown Company",
            "title": str(exp.get("title", "")).strip() or "Unknown Role",
            "location": exp.get("location"),
            "start_date": self._normalize_date(exp.get("start_date")),
            "end_date": self._normalize_date(exp.get("end_date")),
            "is_current": bool(exp.get("is_current", False)),
            "description": exp.get("description"),
            "achievements": [a for a in (exp.get("achievements") or []) if isinstance(a, str) and a.strip()],
            "technologies": [t for t in (exp.get("technologies") or []) if isinstance(t, str) and t.strip()],
        }

    def _clean_education(self, edu: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate an education entry."""
        return {
            "institution": str(edu.get("institution", "")).strip(),
            "degree": str(edu.get("degree", "")).strip(),
            "field": edu.get("field"),
            "start_date": edu.get("start_date"),
            "end_date": edu.get("end_date"),
            "gpa": edu.get("gpa"),
            "achievements": [a for a in (edu.get("achievements") or []) if isinstance(a, str) and a.strip()],
        }

    def _clean_certification(self, cert: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate a certification entry."""
        return {
            "name": str(cert.get("name", "")).strip(),
            "issuer": str(cert.get("issuer", "")).strip(),
            "date": cert.get("date"),
            "expiry": cert.get("expiry"),
            "credential_id": cert.get("credential_id"),
            "url": cert.get("url"),
        }

    def _clean_project(self, proj: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate a project entry."""
        return {
            "name": str(proj.get("name", "")).strip(),
            "description": proj.get("description"),
            "role": proj.get("role"),
            "technologies": [t for t in (proj.get("technologies") or []) if isinstance(t, str) and t.strip()],
            "url": proj.get("url"),
            "achievements": [a for a in (proj.get("achievements") or []) if isinstance(a, str) and a.strip()],
        }

    def _clean_contact_info(self, contact: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize contact info fields."""
        cleaned = {}
        for key in ("email", "phone", "location", "linkedin", "github", "website"):
            val = contact.get(key)
            if val and isinstance(val, str):
                val = val.strip()
                # Fix URLs that are missing protocol
                if key in ("linkedin", "github", "website") and val and not val.startswith("http"):
                    if "linkedin.com" in val or "github.com" in val or "." in val:
                        val = "https://" + val.lstrip("/")
                cleaned[key] = val if val else None
            else:
                cleaned[key] = None
        return cleaned

    def _normalize_date(self, date_str: Optional[str]) -> Optional[str]:
        """Normalize date strings to 'Mon YYYY' or 'Present'."""
        if not date_str or not isinstance(date_str, str):
            return None
        date_str = date_str.strip()
        if date_str.lower() in ("present", "current", "now", "ongoing"):
            return "Present"
        return date_str

    def _sort_by_date(self, experiences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort experiences with current/most recent first."""
        def sort_key(exp):
            if exp.get("is_current"):
                return (1, 9999)
            end = exp.get("end_date", "")
            if end and end.lower() == "present":
                return (1, 9999)
            # Try to extract year
            if end:
                match = re.search(r"(\d{4})", str(end))
                if match:
                    return (0, int(match.group(1)))
            return (0, 0)

        return sorted(experiences, key=sort_key, reverse=True)

    def _enrich_skills_from_experience(
        self, skills: List[Dict[str, Any]], experience: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract additional skills from experience technologies when skill list is sparse."""
        existing = {s["name"].lower() for s in skills}
        new_skills = []

        for exp in experience:
            for tech in (exp.get("technologies") or []):
                normalized = _SKILL_ALIASES.get(tech.lower(), tech)
                if normalized.lower() not in existing:
                    existing.add(normalized.lower())
                    new_skills.append({
                        "name": normalized,
                        "level": "intermediate",
                        "years": None,
                        "category": "technical",
                    })

        return skills + new_skills
