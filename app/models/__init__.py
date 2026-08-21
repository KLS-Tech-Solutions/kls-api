"""
Every model imported here so Alembic autogenerate and Base.metadata see them.
Mirrors KLS_Academy_MVP_Database_Schema_v2 with a few additions noted below.
"""

from app.models.base import GUID, TimestampMixin, UUIDMixin
from app.models.comms import ActivityLog, EmailLog, EmailTemplate, Notification
from app.models.credential import Certificate, CertificateVerificationLog
from app.models.enums import (
    BatchStatus,
    CertificateStatus,
    Difficulty,
    EmailStatus,
    EnrollmentStatus,
    JourneyStage,
    NotificationType,
    PublishStatus,
    ReviewStatus,
    SubmissionStatus,
    UserRole,
    UserStatus,
)
from app.models.internship import Enrollment, InternshipBatch, InternshipDomain, Task
from app.models.learning import ChapterRead, LearningChapter
from app.models.submission import (
    AdminReview,
    LinkedInSubmission,
    OfferLetter,
    TaskScreenshot,
    TaskSubmission,
)
from app.models.user import AdminProfile, EmailToken, StudentProfile, User

__all__ = [
    "ActivityLog",
    "AdminProfile",
    "AdminReview",
    "BatchStatus",
    "Certificate",
    "ChapterRead",
    "CertificateStatus",
    "CertificateVerificationLog",
    "Difficulty",
    "EmailLog",
    "EmailStatus",
    "EmailTemplate",
    "EmailToken",
    "Enrollment",
    "EnrollmentStatus",
    "GUID",
    "InternshipBatch",
    "InternshipDomain",
    "JourneyStage",
    "LearningChapter",
    "LinkedInSubmission",
    "Notification",
    "NotificationType",
    "OfferLetter",
    "PublishStatus",
    "ReviewStatus",
    "StudentProfile",
    "SubmissionStatus",
    "Task",
    "TaskScreenshot",
    "TaskSubmission",
    "TimestampMixin",
    "User",
    "UUIDMixin",
    "UserRole",
    "UserStatus",
]
