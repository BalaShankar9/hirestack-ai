"""Gap Report model - user vs benchmark analysis"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.profile import Profile
    from app.models.benchmark import Benchmark
    from app.models.roadmap import Roadmap


class GapReport(Base):
    """Gap analysis comparing user profile against benchmark."""

    __tablename__ = "gap_reports"

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
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("benchmarks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Overall compatibility score (0-100)
    compatibility_score: Mapped[int] = mapped_column(Integer, default=0)

    # Detailed scores by category
    skill_score: Mapped[int] = mapped_column(Integer, default=0)
    experience_score: Mapped[int] = mapped_column(Integer, default=0)
    education_score: Mapped[int] = mapped_column(Integer, default=0)
    certification_score: Mapped[int] = mapped_column(Integer, default=0)
    project_score: Mapped[int] = mapped_column(Integer, default=0)

    # Gap details
    skill_gaps: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    experience_gaps: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    education_gaps: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    certification_gaps: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )
    project_gaps: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Strengths (what user has that matches/exceeds benchmark)
    strengths: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Recommendations
    recommendations: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    priority_actions: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Full analysis summary
    summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="gap_reports")
    profile: Mapped["Profile"] = relationship("Profile", back_populates="gap_reports")
    benchmark: Mapped["Benchmark"] = relationship("Benchmark", back_populates="gap_reports")
    roadmaps: Mapped[List["Roadmap"]] = relationship(
        "Roadmap",
        back_populates="gap_report",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GapReport score={self.compatibility_score}>"
