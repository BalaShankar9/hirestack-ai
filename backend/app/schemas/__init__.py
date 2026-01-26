"""
HireStack AI - Pydantic Schemas
Request/Response validation schemas for all API endpoints
"""
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserInDB
from app.schemas.profile import (
    ProfileCreate, ProfileUpdate, ProfileResponse,
    ResumeUpload, ParsedProfile
)
from app.schemas.job import (
    JobDescriptionCreate, JobDescriptionUpdate, JobDescriptionResponse,
    ParsedJobDescription
)
from app.schemas.benchmark import (
    BenchmarkCreate, BenchmarkResponse, BenchmarkSummary,
    IdealCandidate, IdealDocument
)
from app.schemas.gap import (
    GapAnalysisRequest, GapReportResponse, GapSummary,
    SkillGap, ExperienceGap
)
from app.schemas.roadmap import (
    RoadmapCreate, RoadmapResponse, RoadmapMilestone,
    LearningResource
)
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectImplementation
)
from app.schemas.document import (
    DocumentCreate, DocumentUpdate, DocumentResponse,
    DocumentGenerate
)
from app.schemas.export import (
    ExportRequest, ExportResponse, ExportStatus
)

__all__ = [
    # User
    "UserCreate", "UserUpdate", "UserResponse", "UserInDB",
    # Profile
    "ProfileCreate", "ProfileUpdate", "ProfileResponse",
    "ResumeUpload", "ParsedProfile",
    # Job
    "JobDescriptionCreate", "JobDescriptionUpdate", "JobDescriptionResponse",
    "ParsedJobDescription",
    # Benchmark
    "BenchmarkCreate", "BenchmarkResponse", "BenchmarkSummary",
    "IdealCandidate", "IdealDocument",
    # Gap
    "GapAnalysisRequest", "GapReportResponse", "GapSummary",
    "SkillGap", "ExperienceGap",
    # Roadmap
    "RoadmapCreate", "RoadmapResponse", "RoadmapMilestone",
    "LearningResource",
    # Project
    "ProjectCreate", "ProjectUpdate", "ProjectResponse",
    "ProjectImplementation",
    # Document
    "DocumentCreate", "DocumentUpdate", "DocumentResponse",
    "DocumentGenerate",
    # Export
    "ExportRequest", "ExportResponse", "ExportStatus",
]
