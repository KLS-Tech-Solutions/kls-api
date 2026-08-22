"""
Certificate issuance.

The internship is free, so there is no payment step between finishing the work
and receiving the credential: **the certificate is issued the moment the last
technical task is approved**, inside the same transaction as that approval.

That makes the reviewer's click the single event that completes an internship,
which is the behaviour students expect and removes a whole class of "I finished
but never got my certificate" support requests.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Certificate,
    Enrollment,
    EnrollmentStatus,
    InternshipBatch,
    InternshipDomain,
    NotificationType,
    SubmissionStatus,
    Task,
    TaskSubmission,
    User,
)
from app.services.documents import generate_certificate
from app.services.notifications import log_activity, notify
from app.services.numbering import next_certificate_number

logger = logging.getLogger(__name__)


def all_tasks_approved(db: Session, student_id, enrollment: Enrollment) -> bool:
    """
    True when every active technical task in the batch has an approved
    submission. Disabled tasks are excluded — a task an admin has parked must
    not keep a student from finishing.
    """
    task_ids = list(
        db.scalars(
            select(Task.id).where(
                Task.batch_id == enrollment.batch_id,
                Task.order_number > 0,
                Task.is_active.is_(True),
            )
        )
    )
    if not task_ids:
        return False

    approved = set(
        db.scalars(
            select(TaskSubmission.task_id).where(
                TaskSubmission.student_id == student_id,
                TaskSubmission.task_id.in_(task_ids),
                TaskSubmission.status == SubmissionStatus.APPROVED,
            )
        )
    )
    return len(approved) == len(task_ids)


def issue_certificate(
    db: Session, student: User, enrollment: Enrollment
) -> Certificate | None:
    """
    Creates the certificate for one enrolment and marks it complete.

    Scoped to the enrolment, because a student on their second internship
    already holds a certificate for the first and must still receive a new one.

    **The record is written even if PDF rendering fails.** A file can be
    regenerated from the record on the next download; a missing record cannot
    be reconstructed at all.
    """
    existing = db.scalar(
        select(Certificate).where(
            Certificate.student_id == student.id,
            Certificate.enrollment_id == enrollment.id,
        )
    )
    if existing is not None:
        return existing

    batch = db.get(InternshipBatch, enrollment.batch_id)
    domain = db.get(InternshipDomain, batch.domain_id) if batch else None

    certificate = Certificate(
        student_id=student.id,
        enrollment_id=enrollment.id,
        certificate_number=next_certificate_number(db),
        student_name=student.full_name,
    )
    db.add(certificate)

    try:
        certificate.certificate_url, certificate.qr_code_url = generate_certificate(
            certificate_number=certificate.certificate_number,
            student_name=student.full_name,
            domain_title=domain.title if domain else "KLS Academy Internship",
            duration=domain.duration if domain else "",
        )
    except Exception:
        logger.exception(
            "Certificate PDF failed for %s; the record stands and it will "
            "regenerate on download",
            certificate.certificate_number,
        )

    enrollment.status = EnrollmentStatus.COMPLETED
    enrollment.completed_at = datetime.now(timezone.utc)

    notify(
        db,
        student.id,
        "Certificate issued",
        f"Certificate {certificate.certificate_number} is ready to download.",
        NotificationType.CERTIFICATE,
    )
    log_activity(
        db, student.id, "Certificate issued", "certificate", certificate.certificate_number
    )

    return certificate


def issue_if_complete(
    db: Session, student: User, enrollment: Enrollment
) -> Certificate | None:
    """Issues the certificate only if the internship is actually finished."""
    if not all_tasks_approved(db, student.id, enrollment):
        return None
    return issue_certificate(db, student, enrollment)
