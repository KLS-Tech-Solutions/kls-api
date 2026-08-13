"""Builds the `/me/journey` payload — one query set, one response."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import (
    Certificate,
    CertificateStatus,
    InternshipBatch,
    InternshipDomain,
    JourneyStage,
    LinkedInSubmission,
    Notification,
    OfferLetter,
    Payment,
    PaymentStatus,
    StudentProfile,
    SubmissionStatus,
    Task,
    TaskSubmission,
    User,
)
from app.schemas.internship import (
    BatchOut,
    CertificateOut,
    DomainOut,
    EnrollmentOut,
    InternshipHistoryOut,
    JourneyOut,
    LinkedInSubmissionOut,
    NotificationOut,
    OfferLetterOut,
    PaymentOut,
    ProfileOut,
    TaskOut,
    TaskSubmissionOut,
)
from app.schemas.auth import UserOut
from app.services.settings_store import certificate_fee_paise
from app.services.journey import (
    certificate_for,
    compute_stage,
    get_active_enrollment,
    linkedin_for,
    list_enrollments,
)


def domain_out(db: Session, domain: InternshipDomain) -> DomainOut:
    task_count = db.scalar(
        select(func.count(Task.id))
        .join(InternshipBatch, Task.batch_id == InternshipBatch.id)
        .where(
            InternshipBatch.domain_id == domain.id,
            Task.order_number > 0,
            Task.is_active.is_(True),
        )
    )
    data = DomainOut.model_validate(domain)
    data.task_count = task_count or 0
    return data


def batch_out(db: Session, batch: InternshipBatch) -> BatchOut:
    from app.models import Enrollment

    taken = db.scalar(
        select(func.count(Enrollment.id)).where(Enrollment.batch_id == batch.id)
    )
    data = BatchOut.model_validate(batch)
    data.seats_left = max(0, batch.seats_total - (taken or 0))
    return data


def submission_out(submission: TaskSubmission) -> TaskSubmissionOut:
    data = TaskSubmissionOut.model_validate(submission)
    review = submission.latest_review
    if review is not None:
        from app.schemas.internship import AdminReviewOut

        data.review = AdminReviewOut.model_validate(review)
    return data


def certificate_out(db: Session, certificate: Certificate) -> CertificateOut:
    """Denormalised for the public verification page and the student's copy."""
    data = CertificateOut.model_validate(certificate)

    # Prefer the snapshot taken at issue. Falling back to the live user row
    # keeps certificates issued before that column existed working, but a
    # closed account would render as "Deleted user" through that path.
    if certificate.student_name:
        data.student_name = certificate.student_name
    else:
        student = db.get(User, certificate.student_id)
        if student is not None:
            data.student_name = student.full_name

    if certificate.enrollment_id is not None:
        from app.models import Enrollment

        enrollment = db.get(Enrollment, certificate.enrollment_id)
        if enrollment is not None:
            batch = db.get(InternshipBatch, enrollment.batch_id)
            if batch is not None:
                data.batch_name = batch.batch_name
                domain = db.get(InternshipDomain, batch.domain_id)
                if domain is not None:
                    data.domain_title = domain.title
                    data.duration = domain.duration

    return data


def build_history(db: Session, student_id: uuid.UUID) -> list[InternshipHistoryOut]:
    """
    One card per internship the student has taken, newest first.

    The offer letter and certificate URLs are included on every entry, not
    just the current one — a student who paid for a credential keeps access to
    it after moving on to the next internship.
    """
    from app.models import Enrollment  # noqa: F401 — used via list_enrollments

    enrollments = list_enrollments(db, student_id)
    current_id = enrollments[0].id if enrollments else None
    history: list[InternshipHistoryOut] = []

    for enrollment in enrollments:
        batch = db.get(InternshipBatch, enrollment.batch_id)
        domain = db.get(InternshipDomain, batch.domain_id) if batch else None

        task_ids = list(
            db.scalars(
                select(Task.id).where(
                    Task.batch_id == enrollment.batch_id,
                    Task.order_number > 0,
                    Task.is_active.is_(True),
                )
            )
        )
        approved = (
            db.scalar(
                select(func.count(TaskSubmission.id)).where(
                    TaskSubmission.student_id == student_id,
                    TaskSubmission.task_id.in_(task_ids),
                    TaskSubmission.status == SubmissionStatus.APPROVED,
                )
            )
            or 0
            if task_ids
            else 0
        )

        offer_letter = db.scalar(
            select(OfferLetter).where(
                OfferLetter.student_id == student_id,
                OfferLetter.batch_id == enrollment.batch_id,
            )
        )
        certificate = certificate_for(db, enrollment)

        history.append(
            InternshipHistoryOut(
                enrollment_id=enrollment.id,
                batch_id=enrollment.batch_id,
                batch_name=batch.batch_name if batch else "Internship",
                domain_title=domain.title if domain else "KLS Academy Internship",
                domain_slug=domain.slug if domain else None,
                duration=domain.duration if domain else None,
                status=enrollment.status,
                enrolled_at=enrollment.enrolled_at,
                completed_at=enrollment.completed_at,
                is_current=enrollment.id == current_id,
                tasks_total=len(task_ids),
                tasks_approved=approved,
                offer_letter_number=(
                    offer_letter.offer_letter_number if offer_letter else None
                ),
                offer_letter_url=offer_letter.pdf_url if offer_letter else None,
                certificate_number=(
                    certificate.certificate_number if certificate else None
                ),
                certificate_url=certificate.certificate_url if certificate else None,
                certificate_issued_at=certificate.issued_at if certificate else None,
            )
        )

    return history


def build_journey(db: Session, student: User) -> JourneyOut:
    stage = compute_stage(db, student.id)
    enrollment = get_active_enrollment(db, student.id)

    batch = db.get(InternshipBatch, enrollment.batch_id) if enrollment else None
    domain = db.get(InternshipDomain, batch.domain_id) if batch else None

    profile = db.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )

    offer_letter = (
        db.scalar(
            select(OfferLetter).where(
                OfferLetter.student_id == student.id,
                OfferLetter.batch_id == enrollment.batch_id,
            )
        )
        if enrollment
        else None
    )

    # Scoped to the current batch, like everything else here — a LinkedIn post
    # approved for a previous internship is not this internship's.
    linkedin = (
        linkedin_for(db, student.id, enrollment.batch_id) if enrollment else None
    )

    tasks = (
        list(
            db.scalars(
                select(Task)
                .where(Task.batch_id == enrollment.batch_id, Task.is_active.is_(True))
                .order_by(Task.order_number)
            )
        )
        if enrollment
        else []
    )

    submissions = (
        list(
            db.scalars(
                select(TaskSubmission)
                .options(
                    selectinload(TaskSubmission.screenshots),
                    selectinload(TaskSubmission.reviews),
                )
                .join(Task, TaskSubmission.task_id == Task.id)
                .where(
                    TaskSubmission.student_id == student.id,
                    Task.batch_id == enrollment.batch_id,
                )
            )
        )
        if enrollment
        else []
    )

    payment = (
        db.scalar(
            select(Payment)
            .where(
                Payment.student_id == student.id,
                Payment.enrollment_id == enrollment.id,
            )
            .order_by(Payment.created_at.desc())
        )
        if enrollment
        else None
    )

    certificate = certificate_for(db, enrollment) if enrollment else None

    notifications = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == student.id)
            .order_by(Notification.created_at.desc())
            .limit(50)
        )
    )

    return JourneyOut(
        stage=stage,
        user=UserOut.model_validate(student),
        profile=ProfileOut.model_validate(profile) if profile else None,
        domain=domain_out(db, domain) if domain else None,
        batch=batch_out(db, batch) if batch else None,
        enrollment=EnrollmentOut.model_validate(enrollment) if enrollment else None,
        offerLetter=OfferLetterOut.model_validate(offer_letter) if offer_letter else None,
        linkedinSubmission=(
            LinkedInSubmissionOut.model_validate(linkedin) if linkedin else None
        ),
        tasks=[TaskOut.model_validate(t) for t in tasks],
        submissions=[submission_out(s) for s in submissions],
        payment=PaymentOut.model_validate(payment) if payment else None,
        certificate=certificate_out(db, certificate) if certificate else None,
        notifications=[NotificationOut.model_validate(n) for n in notifications],
        certificate_fee_paise=certificate_fee_paise(db),
        history=build_history(db, student.id),
        # A student may start another internship once the current one is
        # certificated — finished and paid for, not merely task-complete.
        can_enroll_again=stage == JourneyStage.CERTIFICATE_ISSUED,
    )
