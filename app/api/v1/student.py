import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_student
from app.core.security import generate_url_token, hash_password, verify_password
from app.models import (
    Certificate,
    EmailToken,
    Enrollment,
    InternshipBatch,
    InternshipDomain,
    Notification,
    OfferLetter,
    StudentProfile,
    Task,
    User,
    UserStatus,
)
from app.schemas.auth import DeleteAccountRequest
from app.schemas.internship import (
    CertificateOut,
    JourneyOut,
    MarkReadRequest,
    NotificationOut,
    ProfileOut,
    ProfileUpdate,
    TaskOut,
)
from app.services.aggregate import build_journey, certificate_out
from app.services.documents import generate_certificate, generate_offer_letter
from app.services.journey import (
    certificate_for,
    get_active_enrollment,
)
from app.services.notifications import log_activity
from app.services.storage import read_bytes

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
    # These live on the user row, not the student profile, so they are split
    # off before the rest is applied to the profile.
    for field in ("full_name", "phone", "state", "country"):
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


def _offer_letter_response(db: Session, student: User, offer_letter: OfferLetter):
    """
    Streams an offer letter PDF, regenerating it if the stored file is missing.

    The database record is the source of truth and the file is a rendering of
    it, so a lost file is never a lost document.
    """
    pdf = read_bytes(offer_letter.pdf_url) if offer_letter.pdf_url else None

    if pdf is None or not (offer_letter.pdf_url or "").endswith(".pdf"):
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
            starts_on=batch.start_date if batch else None,
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


def _certificate_response(db: Session, student: User, certificate: Certificate):
    """Streams a certificate PDF, regenerating it if the file is missing."""
    pdf = read_bytes(certificate.certificate_url) if certificate.certificate_url else None

    if pdf is None or not (certificate.certificate_url or "").endswith(".pdf"):
        data = certificate_out(db, certificate)
        certificate.certificate_url, certificate.qr_code_url = generate_certificate(
            certificate_number=certificate.certificate_number,
            student_name=data.student_name or certificate.student_name or student.full_name,
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


def _own_enrollment(db: Session, student: User, enrollment_id: uuid.UUID) -> Enrollment:
    """
    Resolves an enrolment id, refusing anything that is not the caller's.

    Returning 404 rather than 403 for someone else's enrolment: a student has
    no business learning whether a given id exists.
    """
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.student_id != student.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found"
        )
    return enrollment


@router.get("/offer-letter/download")
def download_offer_letter(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    """The offer letter for the internship currently in progress."""
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

    return _offer_letter_response(db, student, offer_letter)


@router.get("/certificate/download")
def download_certificate(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    """The certificate for the internship currently in progress."""
    enrollment = get_active_enrollment(db, student.id)
    certificate = certificate_for(db, enrollment) if enrollment else None
    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Your certificate has not been issued yet",
        )

    return _certificate_response(db, student, certificate)


# --------------------------------------------------------------------------
# Documents from any internship the student has taken
#
# A student who completes one internship and starts another keeps access to
# everything they earned. These routes are addressed by enrolment id so the
# "My internships" screen can offer a download on every card, not just the
# current one.
# --------------------------------------------------------------------------


@router.get("/internships/{enrollment_id}/offer-letter/download")
def download_offer_letter_for(
    enrollment_id: uuid.UUID,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    enrollment = _own_enrollment(db, student, enrollment_id)
    offer_letter = db.scalar(
        select(OfferLetter).where(
            OfferLetter.student_id == student.id,
            OfferLetter.batch_id == enrollment.batch_id,
        )
    )
    if offer_letter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="There is no offer letter for that internship",
        )

    return _offer_letter_response(db, student, offer_letter)


@router.get("/internships/{enrollment_id}/certificate/download")
def download_certificate_for(
    enrollment_id: uuid.UUID,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    enrollment = _own_enrollment(db, student, enrollment_id)
    certificate = certificate_for(db, enrollment)
    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No certificate was issued for that internship",
        )

    return _certificate_response(db, student, certificate)


@router.get("/certificate", response_model=CertificateOut | None)
def my_certificate(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    """
    The certificate for the internship currently in progress, if it has one.

    Scoped to the current enrolment like the rest of the journey — a student on
    their second internship must not see the first one's certificate here. Past
    certificates come back in `journey.history`.
    """
    enrollment = get_active_enrollment(db, student.id)
    certificate = certificate_for(db, enrollment) if enrollment else None
    return certificate_out(db, certificate) if certificate else None


# --------------------------------------------------------------------------
# Closing an account
# --------------------------------------------------------------------------


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountRequest,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Close the account and scrub the personal data behind it.

    **Soft, not a row delete.** Issued certificates must stay verifiable — an
    employer's link cannot start 404ing because the student later closed their
    account, and the credential was paid for. The user row therefore survives
    as an anonymous shell so those foreign keys still resolve, and the
    certificate carries its own copy of the recipient's name.

    What is removed: name, phone, the whole student profile (college, degree,
    branch, year, LinkedIn, GitHub) and the password. The email address is
    replaced with an unusable placeholder, which also releases the real
    address should they ever want to sign up again.

    The current password is required. This is irreversible, and an unattended
    logged-in session should not be enough to trigger it.
    """
    if not verify_password(payload.password, student.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="That password is not correct",
        )

    certificates = list(
        db.scalars(select(Certificate).where(Certificate.student_id == student.id))
    )
    for certificate in certificates:
        # Backfill for anything issued before the snapshot column existed,
        # while the real name is still readable.
        if not certificate.student_name:
            certificate.student_name = student.full_name

    log_activity(db, student.id, "Closed their account", "account", str(student.id))

    profile = db.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    if profile is not None:
        db.delete(profile)

    # Any outstanding email links stop working immediately.
    db.query(EmailToken).filter(
        EmailToken.user_id == student.id, EmailToken.used_at.is_(None)
    ).update({EmailToken.used_at: datetime.now(timezone.utc)}, synchronize_session=False)

    student.full_name = "Deleted user"
    student.phone = None
    student.state = None
    student.country = None
    # Unique, unusable, and clearly not a real address.
    student.email = f"deleted+{student.id}@account.invalid"
    student.password_hash = hash_password(generate_url_token())
    student.email_verified = False
    student.date_of_birth = None
    student.status = UserStatus.DELETED
    student.deleted_at = datetime.now(timezone.utc)
    # Every token this account holds stops working now, not in thirty days.
    student.token_version += 1

    db.commit()
