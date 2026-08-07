import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_student
from app.models import (
    Certificate,
    Enrollment,
    EnrollmentStatus,
    InternshipBatch,
    InternshipDomain,
    JourneyStage,
    LinkedInSubmission,
    NotificationType,
    OfferLetter,
    Payment,
    PaymentStatus,
    ReviewStatus,
    SubmissionStatus,
    Task,
    TaskScreenshot,
    TaskSubmission,
    User,
)
from app.schemas.internship import (
    EnrollRequest,
    LinkedInSubmissionOut,
    LinkedInSubmitRequest,
    PaymentOrderOut,
    PaymentOut,
    PaymentVerifyRequest,
    TaskSubmissionOut,
)
from app.services.aggregate import submission_out
from app.services.journey import compute_stage, get_active_enrollment, has_reached
from app.services.notifications import log_activity, notify
from app.services.documents import generate_certificate, generate_offer_letter
from app.services.numbering import next_certificate_number, next_offer_letter_number
from app.services.storage import StorageError, save_screenshot

router = APIRouter(tags=["student"])

MIN_SCREENSHOTS = 3
MAX_SCREENSHOTS = 8


@router.post("/enrollments", status_code=status.HTTP_201_CREATED)
def enroll(
    payload: EnrollRequest,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if get_active_enrollment(db, student.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already hold an active internship",
        )

    batch = db.get(InternshipBatch, payload.batch_id)
    if batch is None or batch.domain_id != payload.domain_id:
        raise HTTPException(status_code=404, detail="Internship batch not found")

    enrollment = Enrollment(
        student_id=student.id, batch_id=batch.id, status=EnrollmentStatus.ACTIVE
    )
    db.add(enrollment)
    db.flush()

    # The offer letter is generated immediately — PRD business rule.
    domain = db.get(InternshipDomain, batch.domain_id)
    task_count = db.scalar(
        select(func.count(Task.id)).where(Task.batch_id == batch.id, Task.order_number > 0)
    ) or 0

    offer_letter = OfferLetter(
        student_id=student.id,
        batch_id=batch.id,
        offer_letter_number=next_offer_letter_number(db),
    )
    db.add(offer_letter)

    try:
        offer_letter.pdf_url = generate_offer_letter(
            offer_number=offer_letter.offer_letter_number,
            student_name=student.full_name,
            domain_title=domain.title if domain else "KLS Academy Internship",
            duration=domain.duration if domain else "",
            batch_name=batch.batch_name,
            task_count=task_count,
        )
    except Exception:  # noqa: BLE001 — enrolment must not fail on a render error
        offer_letter.pdf_url = None

    notify(
        db,
        student.id,
        "Offer letter generated",
        f"Offer letter {offer_letter.offer_letter_number} is ready to download.",
        NotificationType.OFFER_LETTER,
    )
    log_activity(db, student.id, "Enrolled", "enrollment", str(enrollment.id))
    db.commit()

    return {"enrollment_id": str(enrollment.id)}


@router.post("/linkedin-submissions", status_code=status.HTTP_201_CREATED, response_model=LinkedInSubmissionOut)
def submit_linkedin(
    payload: LinkedInSubmitRequest,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    enrollment = get_active_enrollment(db, student.id)
    if enrollment is None:
        raise HTTPException(status_code=409, detail="Enrol in an internship first")

    offer_letter = db.scalar(
        select(OfferLetter).where(
            OfferLetter.student_id == student.id,
            OfferLetter.batch_id == enrollment.batch_id,
        )
    )
    if offer_letter is None:
        raise HTTPException(status_code=409, detail="Your offer letter is not ready yet")

    existing = db.scalar(
        select(LinkedInSubmission)
        .where(LinkedInSubmission.student_id == student.id)
        .order_by(LinkedInSubmission.submitted_at.desc())
    )
    if existing is not None and existing.status == ReviewStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Your LinkedIn post is already verified")

    if existing is not None and existing.status == ReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Your post is already awaiting review")

    submission = LinkedInSubmission(
        student_id=student.id,
        offer_letter_id=offer_letter.id,
        linkedin_post_url=str(payload.linkedin_post_url),
        status=ReviewStatus.PENDING,
    )
    db.add(submission)
    log_activity(db, student.id, "Submitted LinkedIn post", "linkedin")
    db.commit()
    db.refresh(submission)
    return submission


@router.post("/task-submissions", status_code=status.HTTP_201_CREATED, response_model=TaskSubmissionOut)
async def submit_task(
    task_id: uuid.UUID = Form(...),
    title: str = Form(..., min_length=5, max_length=200),
    github_url: str = Form(...),
    description: str = Form(..., min_length=120),
    live_demo_url: str | None = Form(None),
    screenshots: list[UploadFile] = File(...),
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    stage = compute_stage(db, student.id)
    if not has_reached(stage, JourneyStage.LINKEDIN_APPROVED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical tasks unlock once your LinkedIn post is verified",
        )

    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    enrollment = get_active_enrollment(db, student.id)
    if enrollment is None or task.batch_id != enrollment.batch_id:
        raise HTTPException(status_code=403, detail="This task is not part of your internship")

    if not (MIN_SCREENSHOTS <= len(screenshots) <= MAX_SCREENSHOTS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "loc": ["body", "screenshots"],
                    "msg": f"Attach between {MIN_SCREENSHOTS} and {MAX_SCREENSHOTS} screenshots",
                    "type": "value_error",
                }
            ],
        )

    # Tasks are sequential — the previous one must be approved first.
    previous = db.scalar(
        select(Task).where(
            Task.batch_id == task.batch_id, Task.order_number == task.order_number - 1
        )
    )
    if previous is not None and previous.order_number > 0:
        previous_ok = db.scalar(
            select(TaskSubmission.id).where(
                TaskSubmission.student_id == student.id,
                TaskSubmission.task_id == previous.id,
                TaskSubmission.status == SubmissionStatus.APPROVED,
            )
        )
        if previous_ok is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Finish and get the previous task approved first",
            )

    existing = db.scalar(
        select(TaskSubmission).where(
            TaskSubmission.student_id == student.id, TaskSubmission.task_id == task.id
        )
    )
    if existing is not None and existing.status in (
        SubmissionStatus.UNDER_REVIEW,
        SubmissionStatus.SUBMITTED,
        SubmissionStatus.APPROVED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This task has already been submitted",
        )

    if existing is not None:
        submission = existing
        submission.attempt += 1
        submission.screenshots.clear()
    else:
        submission = TaskSubmission(task_id=task.id, student_id=student.id)
        db.add(submission)

    submission.title = title
    submission.github_url = github_url
    submission.live_demo_url = live_demo_url or None
    submission.description = description
    submission.status = SubmissionStatus.UNDER_REVIEW
    submission.submitted_at = datetime.now(timezone.utc)
    db.flush()

    try:
        for index, upload in enumerate(screenshots, start=1):
            url = save_screenshot(upload, submission.id, index)
            db.add(
                TaskScreenshot(
                    submission_id=submission.id, image_url=url, display_order=index
                )
            )
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["body", "screenshots"], "msg": str(exc), "type": "value_error"}],
        ) from exc

    log_activity(db, student.id, f"Submitted task {task.order_number}", "submission", str(submission.id))
    db.commit()

    db.refresh(submission)
    return submission_out(submission)


@router.post("/payments/order", response_model=PaymentOrderOut)
def create_payment_order(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    stage = compute_stage(db, student.id)
    if not has_reached(stage, JourneyStage.ALL_TASKS_APPROVED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Every task must be approved before payment unlocks",
        )

    if has_reached(stage, JourneyStage.PAID):
        raise HTTPException(status_code=409, detail="Your certificate fee is already paid")

    enrollment = get_active_enrollment(db, student.id)
    amount = settings.CERTIFICATE_FEE_PAISE

    if settings.payments_configured:
        import razorpay

        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        order = client.order.create(
            {"amount": amount, "currency": "INR", "payment_capture": 1}
        )
        order_id = order["id"]
    else:
        # Lets the flow be exercised before the Razorpay account exists.
        order_id = f"order_dev_{uuid.uuid4().hex[:12]}"

    payment = Payment(
        student_id=student.id,
        enrollment_id=enrollment.id if enrollment else None,
        razorpay_order_id=order_id,
        amount=amount,
        payment_status=PaymentStatus.CREATED,
    )
    db.add(payment)
    db.commit()

    return PaymentOrderOut(
        order_id=order_id,
        amount=amount,
        currency="INR",
        key_id=settings.RAZORPAY_KEY_ID or "rzp_dev_placeholder",
    )


@router.post("/payments/verify", response_model=PaymentOut)
def verify_payment(
    payload: PaymentVerifyRequest,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    payment = db.scalar(
        select(Payment).where(
            Payment.student_id == student.id,
            Payment.razorpay_order_id == payload.razorpay_order_id,
        )
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment order not found")

    if settings.payments_configured:
        import razorpay

        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        try:
            client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": payload.razorpay_order_id,
                    "razorpay_payment_id": payload.razorpay_payment_id,
                    "razorpay_signature": payload.razorpay_signature,
                }
            )
        except Exception as exc:
            payment.payment_status = PaymentStatus.FAILED
            payment.failure_reason = "Signature verification failed"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment could not be verified",
            ) from exc

    payment.transaction_id = payload.razorpay_payment_id
    payment.signature = payload.razorpay_signature
    payment.payment_status = PaymentStatus.SUCCESS
    payment.paid_at = datetime.now(timezone.utc)

    notify(
        db,
        student.id,
        "Payment successful",
        "Your certificate is being issued.",
        NotificationType.PAYMENT,
    )
    log_activity(db, student.id, "Paid certificate fee", "payment", str(payment.id))
    db.flush()

    _issue_certificate(db, student, payment)

    db.commit()
    db.refresh(payment)
    return payment


def _issue_certificate(db: Session, student: User, payment: Payment) -> None:
    """
    Runs inside the payment transaction. A student who has paid must end up
    with a certificate record even if PDF rendering fails — the file can be
    regenerated, a missing record cannot be reconstructed.
    """
    existing = db.scalar(
        select(Certificate).where(Certificate.student_id == student.id)
    )
    if existing is not None:
        return

    enrollment = get_active_enrollment(db, student.id)
    batch = db.get(InternshipBatch, enrollment.batch_id) if enrollment else None
    domain = db.get(InternshipDomain, batch.domain_id) if batch else None

    certificate = Certificate(
        student_id=student.id,
        enrollment_id=enrollment.id if enrollment else None,
        payment_id=payment.id,
        certificate_number=next_certificate_number(db),
    )
    db.add(certificate)

    try:
        certificate_url, qr_url = generate_certificate(
            certificate_number=certificate.certificate_number,
            student_name=student.full_name,
            domain_title=domain.title if domain else "KLS Academy Internship",
            duration=domain.duration if domain else "",
        )
        certificate.certificate_url = certificate_url
        certificate.qr_code_url = qr_url
    except Exception:  # noqa: BLE001
        pass

    if enrollment is not None:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = datetime.now(timezone.utc)

    notify(
        db,
        student.id,
        "Certificate issued",
        f"Certificate {certificate.certificate_number} is ready to download.",
        NotificationType.CERTIFICATE,
    )
