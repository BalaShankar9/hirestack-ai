"""Benchmark model - ideal candidate package"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.job import JobDescription
    from app.models.gap import GapReport


class Benchmark(Base):
    """Benchmark representing the ideal candidate for a job."""

    __tablename__ = "benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Ideal candidate profile
    ideal_profile: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )
    ideal_skills: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    ideal_experience: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    ideal_education: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    ideal_certifications: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Generated documents
    ideal_cv: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ideal_cover_letter: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Portfolio and case studies
    ideal_portfolio: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    ideal_case_studies: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Action plan
    ideal_action_plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Technical/business proposals
    ideal_proposals: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Compatibility scoring criteria
    compatibility_criteria: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )
    scoring_weights: Mapped[Optional[Dict[str, float]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Metadata
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(50), default="generated")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    job_description: Mapped["JobDescription"] = relationship(
        "JobDescription",
        back_populates="benchmarks"
    )
    gap_reports: Mapped[List["GapReport"]] = relationship(
        "GapReport",
        back_populates="benchmark",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Benchmark for job {self.job_description_id}>"
