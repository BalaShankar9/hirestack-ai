"""Pydantic request schemas for the generation API."""
from typing import List

from pydantic import BaseModel, field_validator

from app.api.deps import validate_uuid


# ── Allowed job modules (both snake_case and camelCase) ──
ALLOWED_JOB_MODULES = {
    # snake_case (canonical for /jobs endpoint)
    "cv", "cover_letter", "personal_statement", "portfolio",
    "learning_plan", "scorecard", "benchmark", "gap_analysis",
    # camelCase (accepted for cross-format compatibility)
    "coverLetter", "personalStatement", "learningPlan", "gaps",
}


class PipelineRequest(BaseModel):
    job_title: str
    company: str = ""
    jd_text: str
    resume_text: str = ""


class PlannedPipelineRequest(BaseModel):
    """Request body for the planner-driven pipeline endpoint."""
    user_request: str
    job_title: str = ""
    company: str = ""
    jd_text: str = ""
    resume_text: str = ""


class GenerationJobRequest(BaseModel):
    application_id: str
    requested_modules: List[str] = []

    @field_validator("application_id")
    @classmethod
    def application_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("application_id is required")
        if len(v) > 200:
            raise ValueError("application_id too long")
        return v

    @field_validator("requested_modules")
    @classmethod
    def validate_modules(cls, v: List[str]) -> List[str]:
        if len(v) > 20:
            raise ValueError("Too many requested modules (max 20)")
        for mod in v:
            if mod not in ALLOWED_JOB_MODULES:
                raise ValueError(f"Unknown module: {mod}")
        return v


class RetryModulesRequest(BaseModel):
    modules: List[str]

    @field_validator("modules")
    @classmethod
    def validate_retry_modules(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one module must be specified for retry")
        if len(v) > 20:
            raise ValueError("Too many modules (max 20)")
        for mod in v:
            if mod not in ALLOWED_JOB_MODULES:
                raise ValueError(f"Unknown module: {mod}")
        return v


class GenerateDocumentRequest(BaseModel):
    application_id: str
    doc_key: str
    doc_label: str = ""

    @field_validator("application_id")
    @classmethod
    def _validate_app_id(cls, v: str) -> str:
        validate_uuid(v, "application_id")
        return v

    @field_validator("doc_key")
    @classmethod
    def _validate_doc_key(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("doc_key must be 1-100 characters")
        return v
