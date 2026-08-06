import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import GUID, TimestampMixin, UUIDMixin
from app.models.enums import ReviewStatus, SubmissionStatus


class OfferLetter(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "offer_letters"

    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("internship_batches.id", ondelete="CASCADE"), nullable=False
    )
    offer_letter_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    pdf_url: Mapped[str | None] = mapped_column(String(500))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(), nullable=False
    )
    linkedin_verified: Mapped[bool] = mapped_column(default=False, nullable=False)


class LinkedInSubmission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "linkedin_submissions"

    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offer_letter_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("offer_letters.id", ondelete="CASCADE"), nullable=False
    )
    linkedin_post_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status", native_enum=False),
        default=ReviewStatus.PENDING,
        nullable=False,
        index=True,
    )
    admin_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(), nullable=False
    )


class TaskSubmission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_submissions"

    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    github_url: Mapped[str] = mapped_column(String(500), nullable=False)
    live_demo_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, name="submission_status", native_enum=False),
        default=SubmissionStatus.UNDER_REVIEW,
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Incremented on resubmission so reviewers can see the history.
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    screenshots: Mapped[list["TaskScreenshot"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="TaskScreenshot.display_order",
    )
    reviews: Mapped[list["AdminReview"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="AdminReview.reviewed_at",
    )

    @property
    def latest_review(self) -> "AdminReview | None":
        return self.reviews[-1] if self.reviews else None


class TaskScreenshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_screenshots"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("task_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    submission: Mapped[TaskSubmission] = relationship(back_populates="screenshots")


class AdminReview(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "admin_reviews"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("task_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    remarks: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status", native_enum=False), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(), nullable=False
    )

    submission: Mapped[TaskSubmission] = relationship(back_populates="reviews")
