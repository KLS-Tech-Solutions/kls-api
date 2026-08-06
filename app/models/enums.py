from enum import Enum


class StrEnum(str, Enum):
    """`enum.StrEnum` equivalent that also runs on Python 3.10."""

    def __str__(self) -> str:  # pragma: no cover
        return str(self.value)


class UserRole(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class PublishStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class BatchStatus(StrEnum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"


class EnrollmentStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SubmissionStatus(StrEnum):
    NOT_STARTED = "not_started"
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class CertificateStatus(StrEnum):
    ISSUED = "issued"
    REVOKED = "revoked"


class NotificationType(StrEnum):
    WELCOME = "welcome"
    OFFER_LETTER = "offer_letter"
    LINKEDIN = "linkedin"
    TASK = "task"
    REVIEW = "review"
    PAYMENT = "payment"
    CERTIFICATE = "certificate"
    ANNOUNCEMENT = "announcement"


class EmailStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class JourneyStage(StrEnum):
    """
    The single value that decides what is unlocked in the student dashboard.
    Computed by app/services/journey.py — never stored, always derived, so it
    can't drift out of sync with the underlying records.
    """

    NOT_ENROLLED = "not_enrolled"
    ENROLLED = "enrolled"
    OFFER_LETTER_GENERATED = "offer_letter_generated"
    LINKEDIN_SUBMITTED = "linkedin_submitted"
    LINKEDIN_APPROVED = "linkedin_approved"
    TASKS_IN_PROGRESS = "tasks_in_progress"
    ALL_TASKS_APPROVED = "all_tasks_approved"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    CERTIFICATE_ISSUED = "certificate_issued"
