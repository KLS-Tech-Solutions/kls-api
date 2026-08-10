import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select
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
    InternshipDomain,
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
from app.services.aggregate import build_journey, certificate_out
from app.services.documents import generate_certificate, generate_offer_letter
from app.services.storage import read_bytes
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


@router.get("/offer-letter/download")
def download_offer_letter(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    """
    Streams the offer letter PDF.

    Regenerates it if the stored file is missing — which covers records created
    before PDF rendering worked, and any file lost from storage. The database
    record is the source of truth; the file is a rendering of it.
    """
    enrollment = get_active_enrollment(db, student.id)
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

    if offer_letter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You do not have an offer letter yet",
        )

    pdf = read_bytes(offer_letter.pdf_url) if offer_letter.pdf_url else None

    if pdf is None or not offer_letter.pdf_url or not offer_letter.pdf_url.endswith(".pdf"):
        batch = db.get(InternshipBatch, offer_letter.batch_id)
        domain = db.get(InternshipDomain, batch.domain_id) if batch else None
        task_count = db.scalar(
            select(func.count(Task.id)).where(
                Task.batch_id == offer_letter.batch_id,
                Task.order_number > 0,
                Task.is_active.is_(True),
            )
        ) or 0

        offer_letter.pdf_url = generate_offer_letter(
            offer_number=offer_letter.offer_letter_number,
            student_name=student.full_name,
            domain_title=domain.title if domain else "KLS Academy Internship",
            duration=domain.duration if domain else "",
            batch_name=batch.batch_name if batch else "",
            task_count=task_count,
            issued_on=offer_letter.generated_at,
        )
        db.commit()
        pdf = read_bytes(offer_letter.pdf_url)

    if pdf is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The offer letter could not be generated",
        )

    filename = f"KLS-Offer-Letter-{offer_letter.offer_letter_number.replace('/', '-')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/certificate/download")
def download_certificate(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    """Streams the certificate PDF, regenerating it if the file is missing."""
    certificate = db.scalar(
        select(Certificate).where(
            Certificate.student_id == student.id,
            Certificate.status == CertificateStatus.ISSUED,
        )
    )
    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Your certificate has not been issued yet",
        )

    pdf = read_bytes(certificate.certificate_url) if certificate.certificate_url else None

    if pdf is None or not (certificate.certificate_url or "").endswith(".pdf"):
        data = certificate_out(db, certificate)
        certificate.certificate_url, certificate.qr_code_url = generate_certificate(
            certificate_number=certificate.certificate_number,
            student_name=data.student_name or student.full_name,
            domain_title=data.domain_title,
            duration=data.duration,
            issued_on=certificate.issued_at,
        )
        db.commit()
        pdf = read_bytes(certificate.certificate_url)

    if pdf is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The certificate could not be generated",
        )

    filename = f"KLS-Certificate-{certificate.certificate_number}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
