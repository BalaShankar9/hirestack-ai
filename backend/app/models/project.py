"""Project model - suggested portfolio projects"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.roadmap import Roadmap


class Project(Base):
    """Suggested portfolio project for skill development."""

    __tablename__ = "projects"

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
    roadmap_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmaps.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Project details
    tech_stack: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )
    difficulty: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    estimated_duration: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Implementation guide
    implementation_guide: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )
    milestones: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    features: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Learning outcomes
    skills_developed: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )
    learning_outcomes: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Resources
    resources: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True
    )
    references: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Status tracking
    status: Mapped[str] = mapped_column(String(50), default="suggested")
    progress: Mapped[int] = mapped_column(default=0)  # 0-100

    # Repository/demo links
    repo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    demo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    user: Mapped["User"] = relationship("User", back_populates="projects")
    roadmap: Mapped[Optional["Roadmap"]] = relationship("Roadmap", back_populates="projects")

    def __repr__(self) -> str:
        return f"<Project {self.title}>"
