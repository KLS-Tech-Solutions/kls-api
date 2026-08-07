import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_student
from app.models import (
    Certificate,
    CertificateStatus,
    Enrollment,
    EnrollmentStatus,
    InternshipBatch,
    JourneyStage,
    LinkedInSubmission,
    Notification,
    NotificationType,
    OfferLetter,
    Payment,
    PaymentStatus,
    ReviewStatus,
    StudentProfile,
    SubmissionStatus,
    Task,
    TaskScreenshot,
    TaskSubmission,
    User,
)
from app.schemas.internship import (
    CertificateOut,
    EnrollRequest,
    JourneyOut,
    LinkedInSubmissionOut,
    LinkedInSubmitRequest,
    MarkReadRequest,
    NotificationOut,
    PaymentOrderOut,
    PaymentOut,
    PaymentVerifyRequest,
    ProfileOut,
    ProfileUpdate,
    TaskOut,
    TaskSubmissionOut,
)
from app.services.aggregate import build_journey, certificate_out, submission_out
from app.services.journey import compute_stage, get_active_enrollment, has_reached
from app.services.notifications import log_activity, notify
from app.services.numbering import next_certificate_number, next_offer_letter_number
from app.services.storage import save_screenshot

router = APIRouter(prefix="/me", tags=["student"])

MIN_SCREENSHOTS = 3
MAX_SCREENSHOTS = 8


@router.get("/journey", response_model=JourneyOut)
def my_journey(student: User = Depends(get_current_student), db: Session = Depends(get_db)):
    return build_journey(db, student)


@router.get("/tasks", response_model=list[TaskOut])
def my_tasks(student: User = Depends(get_current_student), db: Session = Depends(get_db)):
    enrollment = get_active_enrollment(db, student.id)
    if enrollment is None:
        return []
    return list(
        db.scalars(
            select(Task)
            .where(Task.batch_id == enrollment.batch_id, Task.is_active.is_(True))
            .order_by(Task.order_number)
        )
    )


@router.patch("/profile", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))
    if profile is None:
        profile = StudentProfile(user_id=student.id)
        db.add(profile)

    data = payload.model_dump(exclude_unset=True)
    for field in ("full_name", "phone"):
        if data.get(field):
            setattr(student, field, data.pop(field))
        else:
            data.pop(field, None)

    for field, value in data.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


@router.get("/notifications", response_model=list[NotificationOut])
def my_notifications(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == student.id)
            .order_by(Notification.created_at.desc())
            .limit(100)
        )
    )


@router.patch("/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_notifications_read(
    payload: MarkReadRequest,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.user_id == student.id, Notification.id.in_(payload.ids)
    ).update({Notification.is_read: True}, synchronize_session=False)
    db.commit()


@router.get("/certificate", response_model=CertificateOut | None)
def my_certificate(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    certificate = db.scalar(
        select(Certificate).where(
            Certificate.student_id == student.id,
            Certificate.status == CertificateStatus.ISSUED,
        )
    )
    return certificate_out(db, certificate) if certificate else None
