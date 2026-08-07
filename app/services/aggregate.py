"""Builds the `/me/journey` payload — one query set, one response."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Certificate,
    CertificateStatus,
    InternshipBatch,
    InternshipDomain,
    LinkedInSubmission,
    Notification,
    OfferLetter,
    Payment,
    PaymentStatus,
    StudentProfile,
    Task,
    TaskSubmission,
    User,
)
from app.schemas.internship import (
    BatchOut,
    CertificateOut,
    DomainOut,
    EnrollmentOut,
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
from app.services.journey import compute_stage, get_active_enrollment


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

    linkedin = db.scalar(
        select(LinkedInSubmission)
        .where(LinkedInSubmission.student_id == student.id)
        .order_by(LinkedInSubmission.submitted_at.desc())
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

    submissions = list(
        db.scalars(
            select(TaskSubmission)
            .options(
                selectinload(TaskSubmission.screenshots),
                selectinload(TaskSubmission.reviews),
            )
            .where(TaskSubmission.student_id == student.id)
        )
    )

    payment = db.scalar(
        select(Payment)
        .where(Payment.student_id == student.id)
        .order_by(Payment.created_at.desc())
    )

    certificate = db.scalar(
        select(Certificate).where(
            Certificate.student_id == student.id,
            Certificate.status == CertificateStatus.ISSUED,
        )
    )

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
    )
