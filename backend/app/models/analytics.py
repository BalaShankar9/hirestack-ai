"""Analytics model - user activity tracking"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class EventType:
    """Analytics event type constants."""
    # Auth events
    LOGIN = "auth.login"
    LOGOUT = "auth.logout"
    REGISTER = "auth.register"

    # Profile events
    PROFILE_UPLOAD = "profile.upload"
    PROFILE_UPDATE = "profile.update"
    PROFILE_PARSE = "profile.parse"

    # Job events
    JOB_CREATE = "job.create"
    JOB_UPDATE = "job.update"
    JOB_DELETE = "job.delete"

    # Benchmark events
    BENCHMARK_GENERATE = "benchmark.generate"
    BENCHMARK_VIEW = "benchmark.view"

    # Gap analysis events
    GAP_ANALYZE = "gap.analyze"
    GAP_VIEW = "gap.view"

    # Roadmap events
    ROADMAP_GENERATE = "roadmap.generate"
    ROADMAP_UPDATE = "roadmap.update"
    MILESTONE_COMPLETE = "roadmap.milestone_complete"

    # Document events
    DOCUMENT_GENERATE = "document.generate"
    DOCUMENT_EDIT = "document.edit"
    DOCUMENT_VIEW = "document.view"

    # Export events
    EXPORT_CREATE = "export.create"
    EXPORT_DOWNLOAD = "export.download"

    # AI events
    AI_REQUEST = "ai.request"
    AI_RESPONSE = "ai.response"
    AI_ERROR = "ai.error"


class Analytics(Base):
    """User analytics event."""

    __tablename__ = "analytics"

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

    # Event details
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True
    )

    # Context
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Related entity
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )

    # Timing
    duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="analytics")

    def __repr__(self) -> str:
        return f"<Analytics {self.event_type}>"
