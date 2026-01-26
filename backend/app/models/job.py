"""Job Description model"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.benchmark import Benchmark


class JobDescription(Base):
    """Job description for matching and benchmark generation."""

    __tablename__ = "job_descriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Basic info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    experience_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    salary_range: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Full description
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Parsed requirements
    parsed_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )
    required_skills: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )
    preferred_skills: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )
    requirements: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )
    responsibilities: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )
    benefits: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Company info
    company_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Vector embedding
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(1536),
        nullable=True
    )

    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    user: Mapped["User"] = relationship("User", back_populates="job_descriptions")
    benchmarks: Mapped[List["Benchmark"]] = relationship(
        "Benchmark",
        back_populates="job_description",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<JobDescription {self.title} at {self.company}>"
