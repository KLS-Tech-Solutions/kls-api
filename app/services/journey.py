"""
The journey stage engine.

This is the most important module in the backend. `GET /me/journey` returns a
single `stage` value and both frontends decide what is locked from it — they
never infer it themselves. The stage is *derived* from the underlying records
on every read rather than stored, so it can never drift out of sync with
reality (an approval that was rolled back, a payment that failed later).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Certificate,
    CertificateStatus,
    Enrollment,
    EnrollmentStatus,
    JourneyStage,
    LinkedInSubmission,
    OfferLetter,
    Payment,
    PaymentStatus,
    ReviewStatus,
    SubmissionStatus,
    Task,
    TaskSubmission,
)

STAGE_ORDER: list[JourneyStage] = [
    JourneyStage.NOT_ENROLLED,
    JourneyStage.ENROLLED,
    JourneyStage.OFFER_LETTER_GENERATED,
    JourneyStage.LINKEDIN_SUBMITTED,
    JourneyStage.LINKEDIN_APPROVED,
    JourneyStage.TASKS_IN_PROGRESS,
    JourneyStage.ALL_TASKS_APPROVED,
    JourneyStage.PAYMENT_PENDING,
    JourneyStage.PAID,
    JourneyStage.CERTIFICATE_ISSUED,
]


def has_reached(stage: JourneyStage, target: JourneyStage) -> bool:
    return STAGE_ORDER.index(stage) >= STAGE_ORDER.index(target)


def get_active_enrollment(db: Session, student_id: uuid.UUID) -> Enrollment | None:
    return db.scalar(
        select(Enrollment)
        .where(
            Enrollment.student_id == student_id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED]),
        )
        .order_by(Enrollment.enrolled_at.desc())
    )


def compute_stage(db: Session, student_id: uuid.UUID) -> JourneyStage:
    """Walk the journey backwards — the furthest condition met wins."""

    enrollment = get_active_enrollment(db, student_id)
    if enrollment is None:
        return JourneyStage.NOT_ENROLLED

    # --- certificate ------------------------------------------------------
    certificate = db.scalar(
        select(Certificate).where(
            Certificate.student_id == student_id,
            Certificate.status == CertificateStatus.ISSUED,
        )
    )
    if certificate is not None:
        return JourneyStage.CERTIFICATE_ISSUED

    # --- payment ----------------------------------------------------------
    successful_payment = db.scalar(
        select(Payment).where(
            Payment.student_id == student_id,
            Payment.payment_status == PaymentStatus.SUCCESS,
        )
    )
    if successful_payment is not None:
        return JourneyStage.PAID

    # --- tasks ------------------------------------------------------------
    technical_task_ids = list(
        db.scalars(
            select(Task.id).where(Task.batch_id == enrollment.batch_id, Task.order_number > 0)
        )
    )

    linkedin = db.scalar(
        select(LinkedInSubmission)
        .where(LinkedInSubmission.student_id == student_id)
        .order_by(LinkedInSubmission.submitted_at.desc())
    )
    linkedin_approved = linkedin is not None and linkedin.status == ReviewStatus.APPROVED

    if linkedin_approved and technical_task_ids:
        approved_task_ids = set(
            db.scalars(
                select(TaskSubmission.task_id).where(
                    TaskSubmission.student_id == student_id,
                    TaskSubmission.task_id.in_(technical_task_ids),
                    TaskSubmission.status == SubmissionStatus.APPROVED,
                )
            )
        )

        if len(approved_task_ids) == len(technical_task_ids):
            # Payment row exists but hasn't succeeded → they've started paying.
            pending_payment = db.scalar(
                select(Payment).where(
                    Payment.student_id == student_id,
                    Payment.payment_status.in_(
                        [PaymentStatus.CREATED, PaymentStatus.PENDING, PaymentStatus.FAILED]
                    ),
                )
            )
            return (
                JourneyStage.PAYMENT_PENDING
                if pending_payment is not None
                else JourneyStage.ALL_TASKS_APPROVED
            )

        has_any_submission = db.scalar(
            select(TaskSubmission.id).where(
                TaskSubmission.student_id == student_id,
                TaskSubmission.task_id.in_(technical_task_ids),
            )
        )
        return (
            JourneyStage.TASKS_IN_PROGRESS
            if has_any_submission is not None
            else JourneyStage.LINKEDIN_APPROVED
        )

    if linkedin_approved:
        return JourneyStage.LINKEDIN_APPROVED

    if linkedin is not None:
        # Rejected sends them back to resubmit, so both land on "submitted".
        return JourneyStage.LINKEDIN_SUBMITTED

    # --- offer letter -----------------------------------------------------
    offer_letter = db.scalar(
        select(OfferLetter).where(
            OfferLetter.student_id == student_id,
            OfferLetter.batch_id == enrollment.batch_id,
        )
    )
    if offer_letter is not None:
        return JourneyStage.OFFER_LETTER_GENERATED

    return JourneyStage.ENROLLED
