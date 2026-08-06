import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl

from app.models import (
    BatchStatus,
    Difficulty,
    EnrollmentStatus,
    JourneyStage,
    PaymentStatus,
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
    outcomes: list[str] = []
    skills: list[str] = []
    status: PublishStatus = PublishStatus.ACTIVE


class DomainUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    duration: str | None = None
    difficulty: Difficulty | None = None
    icon: str | None = None
    outcomes: list[str] | None = None
    skills: list[str] | None = None
    status: PublishStatus | None = None


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


class TaskCreate(BaseModel):
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


class PaymentOut(ORMModel):
    id: uuid.UUID
    student_id: uuid.UUID
    transaction_id: str | None
    amount: int
    currency: str
    payment_status: PaymentStatus
    paid_at: datetime | None


class PaymentOrderOut(BaseModel):
    order_id: str
    amount: int
    currency: str = "INR"
    key_id: str


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


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
    payment: PaymentOut | None
    certificate: CertificateOut | None
    notifications: list[NotificationOut]
