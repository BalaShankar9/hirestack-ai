"""
Role Profiler Chain
Parses resumes and extracts structured profile data
"""
from typing import Dict, Any

from ai_engine.client import AIClient


RESUME_PARSER_SYSTEM = """You are an expert resume parser and career analyst. Your task is to extract structured information from resumes with high accuracy.

Extract all relevant information and return it in a structured JSON format. Be thorough but accurate - only include information that is actually present in the resume.

For skills, determine the level based on context clues:
- "expert", "advanced", "lead", "architect" → "expert"
- "proficient", "experienced", "senior" → "advanced"
- "familiar", "working knowledge", "junior" → "intermediate"
- "basic", "learning", "exposure" → "beginner"

For experience, calculate approximate years at each position based on dates provided.

Return ONLY valid JSON with no additional text or markdown."""


RESUME_PARSER_PROMPT = """Parse the following resume and extract all information into this exact JSON structure:

```json
{
  "name": "Full Name",
  "title": "Current or Target Job Title",
  "summary": "Professional summary or objective",
  "contact_info": {
    "email": "email@example.com",
    "phone": "+1234567890",
    "location": "City, State/Country",
    "linkedin": "linkedin.com/in/profile",
    "github": "github.com/username",
    "website": "personal website"
  },
  "skills": [
    {
      "name": "Skill Name",
      "level": "beginner|intermediate|advanced|expert",
      "years": 3.5,
      "category": "technical|soft|language|tool"
    }
  ],
  "experience": [
    {
      "company": "Company Name",
      "title": "Job Title",
      "location": "City, Country",
      "start_date": "Month Year",
      "end_date": "Month Year or Present",
      "is_current": true/false,
      "description": "Role description",
      "achievements": ["Achievement 1", "Achievement 2"],
      "technologies": ["Tech 1", "Tech 2"]
    }
  ],
  "education": [
    {
      "institution": "University Name",
      "degree": "Degree Type",
      "field": "Field of Study",
      "start_date": "Year",
      "end_date": "Year",
      "gpa": "3.8/4.0",
      "achievements": ["Honor", "Award"]
    }
  ],
  "certifications": [
    {
      "name": "Certification Name",
      "issuer": "Issuing Organization",
      "date": "Month Year",
      "expiry": "Month Year",
      "credential_id": "ID123",
      "url": "verification URL"
    }
  ],
  "projects": [
    {
      "name": "Project Name",
      "description": "Project description",
      "role": "Your role",
      "technologies": ["Tech 1", "Tech 2"],
      "url": "project URL",
      "achievements": ["Outcome 1"]
    }
  ],
  "languages": [
    {
      "language": "English",
      "proficiency": "native|fluent|professional|conversational|basic"
    }
  ],
  "achievements": [
    "Notable achievement or award"
  ]
}
```

RESUME TEXT:
---
{resume_text}
---

Parse this resume carefully. Include only information that is actually present. Use null for missing fields.
Return ONLY the JSON object, no other text."""


class RoleProfilerChain:
    """Chain for parsing resumes and extracting profile data."""

    VERSION = "1.0.0"

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    async def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """Parse a resume and extract structured data."""
        prompt = RESUME_PARSER_PROMPT.format(resume_text=resume_text)

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=RESUME_PARSER_SYSTEM,
            temperature=0.2,
            max_tokens=4000
        )

        # Validate and clean the result
        return self._validate_result(result)

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean parsed result."""
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
            "achievements": []
        }

        for key, default in defaults.items():
            if key not in result or result[key] is None:
                result[key] = default

        # Clean skills
        if result.get("skills"):
            result["skills"] = [
                self._clean_skill(s) for s in result["skills"]
                if isinstance(s, dict) and s.get("name")
            ]

        # Clean experience
        if result.get("experience"):
            result["experience"] = [
                self._clean_experience(e) for e in result["experience"]
                if isinstance(e, dict) and e.get("company")
            ]

        return result

    def _clean_skill(self, skill: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate a skill entry."""
        valid_levels = ["beginner", "intermediate", "advanced", "expert"]
        level = skill.get("level", "intermediate").lower()
        if level not in valid_levels:
            level = "intermediate"

        return {
            "name": skill.get("name", ""),
            "level": level,
            "years": skill.get("years"),
            "category": skill.get("category", "technical")
        }

    def _clean_experience(self, exp: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate an experience entry."""
        return {
            "company": exp.get("company", ""),
            "title": exp.get("title", ""),
            "location": exp.get("location"),
            "start_date": exp.get("start_date"),
            "end_date": exp.get("end_date"),
            "is_current": exp.get("is_current", False),
            "description": exp.get("description"),
            "achievements": exp.get("achievements", []),
            "technologies": exp.get("technologies", [])
        }
