import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.models import (
    BatchStatus,
    Difficulty,
    EnrollmentStatus,
    JourneyStage,
    PublishStatus,
    ReviewStatus,
    SubmissionStatus,
)
from app.schemas.auth import UserOut
from app.schemas.common import ORMModel


class DomainOut(ORMModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    duration: str
    difficulty: Difficulty
    status: PublishStatus
    icon: str
    image_url: str | None = None
    display_order: int = 0
    outcomes: list[str] = []
    skills: list[str] = []
    task_count: int = 0


class DomainCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=10)
    duration: str = Field(min_length=2, max_length=40)
    difficulty: Difficulty
    icon: str = "code"
    image_url: str | None = None
    display_order: int = Field(default=0, ge=0)
    outcomes: list[str] = []
    skills: list[str] = []
    status: PublishStatus = PublishStatus.ACTIVE


class DomainUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    duration: str | None = None
    difficulty: Difficulty | None = None
    icon: str | None = None
    image_url: str | None = None
    display_order: int | None = Field(default=None, ge=0)
    outcomes: list[str] | None = None
    skills: list[str] | None = None
    status: PublishStatus | None = None


class DomainReorder(BaseModel):
    """Full ordered list of domain ids — avoids gaps and duplicate positions."""

    domain_ids: list[uuid.UUID]


class BatchOut(ORMModel):
    id: uuid.UUID
    domain_id: uuid.UUID
    batch_name: str
    start_date: date
    end_date: date
    status: BatchStatus
    seats_total: int
    seats_left: int = 0


class BatchCreate(BaseModel):
    domain_id: uuid.UUID
    batch_name: str = Field(min_length=3, max_length=150)
    start_date: date
    end_date: date
    seats_total: int = Field(default=50, ge=1, le=1000)
    status: BatchStatus = BatchStatus.UPCOMING


class BatchUpdate(BaseModel):
    batch_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    seats_total: int | None = None
    status: BatchStatus | None = None


class TaskOut(ORMModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    title: str
    description: str
    order_number: int
    deadline: date | None
    estimated_hours: int
    requirements: list[str] = []
    is_active: bool = True
    instructions: str | None = None
    min_screenshots: int = 3
    max_screenshots: int = 8
    require_github: bool = True
    require_explanation: bool = True
    min_explanation_chars: int = 120
    require_live_demo: bool = False


class TaskConfig(BaseModel):
    """Submission rules a super admin sets per task."""

    is_active: bool = True
    instructions: str | None = None
    min_screenshots: int = Field(default=3, ge=0, le=20)
    max_screenshots: int = Field(default=8, ge=1, le=20)
    require_github: bool = True
    require_explanation: bool = True
    min_explanation_chars: int = Field(default=120, ge=0, le=5000)
    require_live_demo: bool = False


class TaskCreate(TaskConfig):
    batch_id: uuid.UUID
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10)
    order_number: int = Field(ge=0)
    deadline: date | None = None
    estimated_hours: int = Field(default=8, ge=1, le=200)
    requirements: list[str] = []


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    order_number: int | None = None
    deadline: date | None = None
    estimated_hours: int | None = None
    requirements: list[str] | None = None
    is_active: bool | None = None
    instructions: str | None = None
    min_screenshots: int | None = Field(default=None, ge=0, le=20)
    max_screenshots: int | None = Field(default=None, ge=1, le=20)
    require_github: bool | None = None
    require_explanation: bool | None = None
    min_explanation_chars: int | None = Field(default=None, ge=0, le=5000)
    require_live_demo: bool | None = None


class TaskReorder(BaseModel):
    """Full ordered list of task ids for a batch — avoids gaps and duplicates."""

    task_ids: list[uuid.UUID]


class EnrollmentOut(ORMModel):
    id: uuid.UUID
    student_id: uuid.UUID
    batch_id: uuid.UUID
    status: EnrollmentStatus
    enrolled_at: datetime
    completed_at: datetime | None


class EnrollRequest(BaseModel):
    domain_id: uuid.UUID
    batch_id: uuid.UUID


class OfferLetterOut(ORMModel):
    id: uuid.UUID
    student_id: uuid.UUID
    batch_id: uuid.UUID
    offer_letter_number: str
    pdf_url: str | None
    generated_at: datetime
    linkedin_verified: bool


class LinkedInSubmissionOut(ORMModel):
    id: uuid.UUID
    student_id: uuid.UUID
    offer_letter_id: uuid.UUID
    linkedin_post_url: str
    status: ReviewStatus
    admin_comment: str | None
    submitted_at: datetime


class LinkedInSubmitRequest(BaseModel):
    linkedin_post_url: HttpUrl


class ReviewRequest(BaseModel):
    status: ReviewStatus
    remarks: str = Field(min_length=3, max_length=2000)


class ScreenshotOut(ORMModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    image_url: str
    display_order: int

    @model_validator(mode="after")
    def _route_through_the_api(self):
        """
        `image_url` holds a storage key, which no browser can fetch. Both apps
        render this straight into an <img>, so it is rewritten to the
        authenticated route that streams the bytes.
        """
        object.__setattr__(self, "image_url", f"/screenshots/{self.id}")
        return self


class AdminReviewOut(ORMModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    reviewed_by: uuid.UUID | None
    remarks: str
    status: ReviewStatus
    reviewed_at: datetime


class TaskSubmissionOut(ORMModel):
    id: uuid.UUID
    task_id: uuid.UUID
    student_id: uuid.UUID
    title: str
    github_url: str
    live_demo_url: str | None
    description: str
    status: SubmissionStatus
    submitted_at: datetime | None
    attempt: int
    screenshots: list[ScreenshotOut] = []
    review: AdminReviewOut | None = None


class CertificateOut(ORMModel):
    id: uuid.UUID
    student_id: uuid.UUID
    certificate_number: str
    certificate_url: str | None
    qr_code_url: str | None
    issued_at: datetime
    student_name: str = ""
    domain_title: str = ""
    duration: str = ""
    batch_name: str = ""

    @field_validator("student_name", mode="before")
    @classmethod
    def _name_never_null(cls, value: str | None) -> str:
        """
        `Certificate.student_name` is nullable — it snapshots the recipient at
        issue and is null for certificates created before that column existed.
        Both frontends type this as a string, so null becomes empty here and
        `certificate_out` fills it from the user row.
        """
        return value or ""


class ProfileOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    college_name: str | None
    degree: str | None
    branch: str | None
    year: str | None
    linkedin_url: str | None
    github_url: str | None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = None
    state: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=80)
    college_name: str | None = Field(default=None, max_length=150)
    degree: str | None = Field(default=None, max_length=60)
    branch: str | None = Field(default=None, max_length=80)
    year: str | None = Field(default=None, max_length=20)
    linkedin_url: str | None = None
    github_url: str | None = None


class NotificationOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime


class MarkReadRequest(BaseModel):
    ids: list[uuid.UUID]


class InternshipHistoryOut(BaseModel):
    """
    One past or present internship, with everything needed to render a history
    card and re-download the documents. A student paid for these credentials;
    they keep access to them for good.
    """

    enrollment_id: uuid.UUID
    batch_id: uuid.UUID
    batch_name: str
    domain_title: str
    domain_slug: str | None = None
    duration: str | None = None
    status: EnrollmentStatus
    enrolled_at: datetime
    completed_at: datetime | None = None
    is_current: bool = False

    tasks_total: int = 0
    tasks_approved: int = 0

    offer_letter_number: str | None = None
    offer_letter_url: str | None = None
    certificate_number: str | None = None
    certificate_url: str | None = None
    certificate_issued_at: datetime | None = None


class JourneyOut(BaseModel):
    """
    The aggregate both dashboards render from. Field names match the frontend
    `StudentJourney` type exactly — do not rename without changing both apps.
    """

    stage: JourneyStage
    user: UserOut
    profile: ProfileOut | None
    domain: DomainOut | None
    batch: BatchOut | None
    enrollment: EnrollmentOut | None
    offerLetter: OfferLetterOut | None
    linkedinSubmission: LinkedInSubmissionOut | None
    tasks: list[TaskOut]
    submissions: list[TaskSubmissionOut]
    certificate: CertificateOut | None
    notifications: list[NotificationOut]
    # Every internship the student has taken, newest first — the current one
    # included, flagged `is_current`. Drives the "My internships" screen.
    history: list[InternshipHistoryOut] = []
    # True once the current internship is certificated, which is when a
    # student becomes eligible to start another.
    can_enroll_again: bool = False


# ---------------------------------------------------------------------------
# Learning notes
# ---------------------------------------------------------------------------


class ChapterOut(ORMModel):
    """One chapter of study notes. `is_read` is per-student, filled in by the
    student endpoint and left false for admin listings."""

    id: uuid.UUID
    domain_id: uuid.UUID
    title: str
    summary: str | None
    order_number: int
    difficulty: Difficulty
    pdf_url: str | None
    pdf_filename: str | None
    pdf_size_bytes: int | None
    estimated_minutes: int
    status: PublishStatus
    is_read: bool = False
    updated_by: uuid.UUID | None = None
    # Filled in by the admin listing so the console does not have to resolve
    # a user id per row.
    updated_by_name: str = ""


class ChapterCreate(BaseModel):
    domain_id: uuid.UUID
    title: str = Field(min_length=3, max_length=200)
    summary: str | None = None
    order_number: int = Field(ge=1)
    difficulty: Difficulty = Difficulty.BEGINNER
    estimated_minutes: int = Field(default=20, ge=1, le=600)
    status: PublishStatus = PublishStatus.ACTIVE


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    summary: str | None = None
    order_number: int | None = Field(default=None, ge=1)
    difficulty: Difficulty | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=600)
    status: PublishStatus | None = None


class ChapterReorder(BaseModel):
    """Full ordered list of chapter ids — avoids gaps and duplicate positions."""

    chapter_ids: list[uuid.UUID]
