import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import GUID, TimestampMixin, UUIDMixin
from app.models.enums import Difficulty, PublishStatus


class LearningChapter(Base, UUIDMixin, TimestampMixin):
    """
    A chapter of study notes attached to an internship domain.

    Chapters belong to the **domain**, not the batch, so an admin uploads the
    Backend Development material once and every batch of that domain gets it.
    Re-uploading per cohort was the obvious alternative and is pure busywork.

    Ordered beginner to advanced by `order_number`, which is what makes a list
    of PDFs feel like a course rather than a folder.
    """

    __tablename__ = "learning_chapters"
    __table_args__ = (
        # Two chapters cannot claim the same position in the same domain.
        UniqueConstraint("domain_id", "order_number", name="uq_chapter_position"),
    )

    domain_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("internship_domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty", native_enum=False),
        default=Difficulty.BEGINNER,
        nullable=False,
    )
    # Where the PDF lives in storage. Nullable so a chapter can be drafted
    # before its file is ready.
    pdf_url: Mapped[str | None] = mapped_column(String(500))
    pdf_filename: Mapped[str | None] = mapped_column(String(255))
    pdf_size_bytes: Mapped[int | None] = mapped_column(Integer)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    status: Mapped[PublishStatus] = mapped_column(
        Enum(PublishStatus, name="publish_status", native_enum=False),
        default=PublishStatus.ACTIVE,
        nullable=False,
    )
    # Who last touched this chapter. Any admin can edit the notes now, so
    # "who changed this" stops being obvious from the fact that only one
    # person could have. SET NULL rather than CASCADE: an admin leaving must
    # not delete the teaching material they wrote.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )


class ChapterRead(Base, UUIDMixin, TimestampMixin):
    """
    A student marking a chapter as read.

    Nothing is gated on this — the notes are a prompt, not a lock. It exists so
    a student can see their own progress through the material, and so admins
    can tell whether the notes are actually being used.
    """

    __tablename__ = "chapter_reads"
    __table_args__ = (
        UniqueConstraint("student_id", "chapter_id", name="uq_chapter_read"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("learning_chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
