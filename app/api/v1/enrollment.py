import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_student
from app.models import (
    Enrollment,
    EnrollmentStatus,
    InternshipBatch,
    InternshipDomain,
    JourneyStage,
    LinkedInSubmission,
    NotificationType,
    OfferLetter,
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
    TaskSubmissionOut,
)
from app.services.aggregate import submission_out
from app.services.journey import (
    certificate_for,
    compute_stage,
    get_active_enrollment,
    has_reached,
    linkedin_for,
)
from app.services.notifications import log_activity, notify
from app.services.documents import generate_offer_letter
from app.services.email import send_offer_letter_ready
from app.services.numbering import next_offer_letter_number
from app.services.storage import StorageError, save_screenshot

router = APIRouter(tags=["student"])

@router.post("/enrollments", status_code=status.HTTP_201_CREATED)
def enroll(
    payload: EnrollRequest,
    background: BackgroundTasks,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    # A student may take a second internship, but only once the current one is
    # finished — certificated, which means paid for too. Anything earlier and
    # they would abandon a half-done journey to start another.
    current = get_active_enrollment(db, student.id)
    if current is not None and certificate_for(db, current) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Finish your current internship first — your certificate is "
                "issued once every task is approved and the fee is paid"
            ),
        )

    batch = db.get(InternshipBatch, payload.batch_id)
    if batch is None or batch.domain_id != payload.domain_id:
        raise HTTPException(status_code=404, detail="Internship batch not found")

    # Re-enrolling in a batch they have already taken would make the previous
    # submissions count towards the new internship, since submissions are
    # keyed by task.
    already_taken = db.scalar(
        select(Enrollment.id).where(
            Enrollment.student_id == student.id,
            Enrollment.batch_id == batch.id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED]),
        )
    )
    if already_taken is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already taken this internship — choose a different one",
        )

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
            starts_on=batch.start_date,
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

    send_offer_letter_ready(
        background,
        user_id=student.id,
        to=student.email,
        full_name=student.full_name,
        offer_number=offer_letter.offer_letter_number,
        domain_title=domain.title if domain else "your internship",
    )

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

    # Scoped to this batch — an approved post from a previous internship must
    # not block the student from posting about this one.
    existing = linkedin_for(db, student.id, enrollment.batch_id)
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
    github_url: str = Form(""),
    description: str = Form(""),
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

    if not task.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This task is not currently open for submission",
        )

    # Every rule below is configured per task by a super admin, so a domain
    # can require different evidence without a code change.
    issues: list[dict[str, object]] = []
    attached = [f for f in screenshots if f and f.filename]

    if not (task.min_screenshots <= len(attached) <= task.max_screenshots):
        issues.append(
            {
                "loc": ["body", "screenshots"],
                "msg": (
                    f"Attach between {task.min_screenshots} and "
                    f"{task.max_screenshots} screenshots"
                ),
                "type": "value_error",
            }
        )

    if task.require_github and not github_url.strip():
        issues.append(
            {
                "loc": ["body", "github_url"],
                "msg": "A public GitHub repository is required for this task",
                "type": "value_error",
            }
        )

    if task.require_explanation and len(description.strip()) < task.min_explanation_chars:
        issues.append(
            {
                "loc": ["body", "description"],
                "msg": (
                    f"Explain your implementation in at least "
                    f"{task.min_explanation_chars} characters"
                ),
                "type": "value_error",
            }
        )

    if task.require_live_demo and not (live_demo_url or "").strip():
        issues.append(
            {
                "loc": ["body", "live_demo_url"],
                "msg": "A live demo URL is required for this task",
                "type": "value_error",
            }
        )

    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=issues
        )

    # Tasks are sequential, but the gate is **submission, not approval**. A
    # student who has finished task 1 can start task 2 immediately rather than
    # sitting idle waiting for a reviewer — review latency should never be the
    # thing that slows an internship down.
    #
    # Approval still gates the certificate: `all_tasks_approved` requires every
    # submission to be approved, so nobody finishes on unreviewed work.
    previous = db.scalar(
        select(Task)
        .where(
            Task.batch_id == task.batch_id,
            Task.order_number < task.order_number,
            Task.order_number > 0,
            Task.is_active.is_(True),
        )
        .order_by(Task.order_number.desc())
    )
    if previous is not None:
        previous_submitted = db.scalar(
            select(TaskSubmission.id).where(
                TaskSubmission.student_id == student.id,
                TaskSubmission.task_id == previous.id,
                TaskSubmission.status.in_(
                    [
                        SubmissionStatus.SUBMITTED,
                        SubmissionStatus.UNDER_REVIEW,
                        SubmissionStatus.APPROVED,
                        SubmissionStatus.REJECTED,
                    ]
                ),
            )
        )
        if previous_submitted is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Submit the previous task before starting this one",
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
        for index, upload in enumerate(attached, start=1):
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
