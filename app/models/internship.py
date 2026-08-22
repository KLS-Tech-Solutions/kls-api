import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import GUID, TimestampMixin, UUIDMixin
from app.models.enums import BatchStatus, Difficulty, EnrollmentStatus, PublishStatus


class InternshipDomain(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "internship_domains"

    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[str] = mapped_column(String(40), nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty", native_enum=False), nullable=False
    )
    status: Mapped[PublishStatus] = mapped_column(
        Enum(PublishStatus, name="publish_status", native_enum=False),
        default=PublishStatus.ACTIVE,
        nullable=False,
    )
    # Presentation fields the marketing pages render.
    icon: Mapped[str] = mapped_column(String(40), default="code", nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    # Controls the order domains appear in on the public site and enrol screen.
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcomes: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)

    batches: Mapped[list["InternshipBatch"]] = relationship(
        back_populates="domain", cascade="all, delete-orphan"
    )


class InternshipBatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "internship_batches"

    domain_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("internship_domains.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_name: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus, name="batch_status", native_enum=False),
        default=BatchStatus.UPCOMING,
        nullable=False,
    )
    seats_total: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    domain: Mapped[InternshipDomain] = relationship(back_populates="batches")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="Task.order_number"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="batch")


class Enrollment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        # A student holds one active internship at a time.
        UniqueConstraint("student_id", "batch_id", name="uq_enrollment_student_batch"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("internship_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus, name="enrollment_status", native_enum=False),
        default=EnrollmentStatus.ACTIVE,
        nullable=False,
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    batch: Mapped[InternshipBatch] = relationship(back_populates="enrollments")


class Task(Base, UUIDMixin, TimestampMixin):
    """
    Tasks are variable per domain. order_number 0 is reserved for the LinkedIn
    onboarding task; technical tasks start at 1 and must stay contiguous.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("batch_id", "order_number", name="uq_task_batch_order"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("internship_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    estimated_hours: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    requirements: Mapped[list[str]] = mapped_column(JSON, default=list)

    # --- submission rules, configured per task ---------------------------
    # A disabled task is hidden from students and skipped by the journey
    # engine, so it can be parked without deleting submission history.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    min_screenshots: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_screenshots: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    require_github: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    require_explanation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_explanation_chars: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    require_live_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    batch: Mapped[InternshipBatch] = relationship(back_populates="tasks")
