import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_super_admin
from app.models import (
    ActivityLog,
    JourneyStage,
    AdminReview,
    Certificate,
    CertificateStatus,
    Enrollment,
    InternshipBatch,
    InternshipDomain,
    LinkedInSubmission,
    NotificationType,
    OfferLetter,
    Payment,
    PaymentStatus,
    ReviewStatus,
    SubmissionStatus,
    Task,
    TaskSubmission,
    User,
    UserRole,
)
from app.schemas.internship import (
    BatchCreate,
    BatchOut,
    BatchUpdate,
    CertificateOut,
    DomainCreate,
    DomainOut,
    DomainReorder,
    DomainUpdate,
    JourneyOut,
    LinkedInSubmissionOut,
    PaymentOut,
    ReviewRequest,
    TaskCreate,
    TaskOut,
    TaskReorder,
    TaskSubmissionOut,
    TaskUpdate,
)
from app.schemas.auth import UserOut
from app.services.aggregate import batch_out, build_journey, domain_out, submission_out
from app.services.journey import compute_stage
from app.services.email import send_linkedin_reviewed, send_task_reviewed
from app.services.notifications import log_activity, notify

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Review queues — the screens that move students forward
# ---------------------------------------------------------------------------


@router.get("/linkedin-submissions", response_model=list[LinkedInSubmissionOut])
def list_linkedin_submissions(
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = select(LinkedInSubmission)
    if status_filter:
        query = query.where(LinkedInSubmission.status == status_filter)
    return list(db.scalars(query.order_by(LinkedInSubmission.submitted_at.desc())))


@router.patch("/linkedin-submissions/{submission_id}", response_model=LinkedInSubmissionOut)
def review_linkedin_submission(
    submission_id: uuid.UUID,
    payload: ReviewRequest,
    background: BackgroundTasks,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    submission = db.get(LinkedInSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    if payload.status == ReviewStatus.PENDING:
        raise HTTPException(status_code=422, detail="Choose approved or rejected")

    submission.status = payload.status
    submission.admin_comment = payload.remarks
    submission.reviewed_by = admin.id
    submission.reviewed_at = datetime.now(timezone.utc)

    if payload.status == ReviewStatus.APPROVED:
        offer_letter = db.get(OfferLetter, submission.offer_letter_id)
        if offer_letter is not None:
            offer_letter.linkedin_verified = True
        notify(
            db,
            submission.student_id,
            "LinkedIn task approved",
            "Your post was verified. Technical tasks are now unlocked.",
            NotificationType.LINKEDIN,
        )
    else:
        notify(
            db,
            submission.student_id,
            "LinkedIn task needs changes",
            payload.remarks,
            NotificationType.LINKEDIN,
        )

    log_activity(
        db, admin.id, f"Reviewed LinkedIn submission ({payload.status.value})",
        "review", str(submission.id),
    )
    db.commit()
    db.refresh(submission)

    student = db.get(User, submission.student_id)
    if student is not None:
        send_linkedin_reviewed(
            background,
            user_id=student.id,
            to=student.email,
            approved=payload.status == ReviewStatus.APPROVED,
            remarks=payload.remarks,
        )

    return submission


@router.get("/task-submissions", response_model=list[TaskSubmissionOut])
def list_task_submissions(
    status_filter: SubmissionStatus | None = Query(default=None, alias="status"),
    batch_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    student_id: uuid.UUID | None = None,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = select(TaskSubmission).options(
        selectinload(TaskSubmission.screenshots), selectinload(TaskSubmission.reviews)
    )
    if status_filter:
        query = query.where(TaskSubmission.status == status_filter)
    if task_id:
        query = query.where(TaskSubmission.task_id == task_id)
    if student_id:
        query = query.where(TaskSubmission.student_id == student_id)
    if batch_id:
        query = query.join(Task, TaskSubmission.task_id == Task.id).where(
            Task.batch_id == batch_id
        )

    submissions = db.scalars(query.order_by(TaskSubmission.submitted_at.desc()))
    return [submission_out(s) for s in submissions]


@router.get("/task-submissions/{submission_id}", response_model=TaskSubmissionOut)
def get_task_submission(
    submission_id: uuid.UUID,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    submission = db.get(TaskSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission_out(submission)


@router.post("/task-submissions/{submission_id}/review", response_model=TaskSubmissionOut)
def review_task_submission(
    submission_id: uuid.UUID,
    payload: ReviewRequest,
    background: BackgroundTasks,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    submission = db.get(TaskSubmission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    if payload.status == ReviewStatus.PENDING:
        raise HTTPException(status_code=422, detail="Choose approved or rejected")

    submission.status = (
        SubmissionStatus.APPROVED
        if payload.status == ReviewStatus.APPROVED
        else SubmissionStatus.REJECTED
    )

    db.add(
        AdminReview(
            submission_id=submission.id,
            reviewed_by=admin.id,
            remarks=payload.remarks,
            status=payload.status,
        )
    )

    task = db.get(Task, submission.task_id)
    label = f"Task {task.order_number}" if task else "Your submission"

    if payload.status == ReviewStatus.APPROVED:
        notify(
            db,
            submission.student_id,
            f"{label} approved",
            payload.remarks,
            NotificationType.REVIEW,
        )
    else:
        notify(
            db,
            submission.student_id,
            f"{label} needs changes",
            payload.remarks,
            NotificationType.REVIEW,
        )

    log_activity(
        db, admin.id, f"Reviewed task submission ({payload.status.value})",
        "review", str(submission.id),
    )
    db.commit()
    db.refresh(submission)

    student = db.get(User, submission.student_id)
    if student is not None:
        approved = payload.status == ReviewStatus.APPROVED
        # Tell them explicitly when this was the last one — that is the moment
        # the certificate becomes available and it should not be a surprise.
        finished = approved and compute_stage(db, student.id) in (
            JourneyStage.ALL_TASKS_APPROVED,
            JourneyStage.PAYMENT_PENDING,
        )
        send_task_reviewed(
            background,
            user_id=student.id,
            to=student.email,
            approved=approved,
            task_title=task.title if task else "Your submission",
            remarks=payload.remarks,
            all_approved=finished,
        )

    return submission_out(submission)


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


@router.get("/students")
def list_students(
    search: str | None = None,
    batch_id: uuid.UUID | None = None,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = select(User).where(User.role == UserRole.STUDENT)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            func.lower(User.full_name).like(pattern) | func.lower(User.email).like(pattern)
        )
    if batch_id:
        query = query.join(Enrollment, Enrollment.student_id == User.id).where(
            Enrollment.batch_id == batch_id
        )

    students = list(db.scalars(query.order_by(User.created_at.desc()).limit(200)))
    return [
        {
            **UserOut.model_validate(s).model_dump(mode="json"),
            "stage": compute_stage(db, s.id).value,
        }
        for s in students
    ]


@router.get("/students/{student_id}", response_model=JourneyOut)
def get_student(
    student_id: uuid.UUID,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Same shape the student's own dashboard renders from."""
    student = db.get(User, student_id)
    if student is None or student.role != UserRole.STUDENT:
        raise HTTPException(status_code=404, detail="Student not found")
    return build_journey(db, student)


# ---------------------------------------------------------------------------
# Catalogue — super admin only
# ---------------------------------------------------------------------------


@router.post("/internship-domains", response_model=DomainOut, status_code=201)
def create_domain(
    payload: DomainCreate,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(select(InternshipDomain).where(InternshipDomain.slug == payload.slug)):
        raise HTTPException(status_code=409, detail="A domain with this slug already exists")

    domain = InternshipDomain(**payload.model_dump())
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain_out(db, domain)


@router.patch("/internship-domains/{domain_id}", response_model=DomainOut)
def update_domain(
    domain_id: uuid.UUID,
    payload: DomainUpdate,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    domain = db.get(InternshipDomain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(domain, field, value)
    db.commit()
    db.refresh(domain)
    return domain_out(db, domain)


@router.delete("/internship-domains/{domain_id}", status_code=204)
def delete_domain(
    domain_id: uuid.UUID,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    domain = db.get(InternshipDomain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    enrolled = db.scalar(
        select(func.count(Enrollment.id))
        .join(InternshipBatch, Enrollment.batch_id == InternshipBatch.id)
        .where(InternshipBatch.domain_id == domain_id)
    )
    if enrolled:
        raise HTTPException(
            status_code=409,
            detail="Students are enrolled in this domain — deactivate it instead",
        )

    db.delete(domain)
    db.commit()


@router.post("/internship-domains/reorder", response_model=list[DomainOut])
def reorder_domains(
    payload: DomainReorder,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Rewrites display_order from the supplied sequence."""
    domains = {d.id: d for d in db.scalars(select(InternshipDomain))}
    if set(payload.domain_ids) != set(domains):
        raise HTTPException(
            status_code=422, detail="Send every domain id exactly once"
        )

    for position, domain_id in enumerate(payload.domain_ids, start=1):
        domains[domain_id].display_order = position
    db.commit()

    return [
        domain_out(db, d)
        for d in db.scalars(
            select(InternshipDomain).order_by(
                InternshipDomain.display_order, InternshipDomain.title
            )
        )
    ]


@router.post("/internship-batches", response_model=BatchOut, status_code=201)
def create_batch(
    payload: BatchCreate,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    batch = InternshipBatch(**payload.model_dump())
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch_out(db, batch)


@router.patch("/internship-batches/{batch_id}", response_model=BatchOut)
def update_batch(
    batch_id: uuid.UUID,
    payload: BatchUpdate,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    batch = db.get(InternshipBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)
    db.commit()
    db.refresh(batch)
    return batch_out(db, batch)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    batch_id: uuid.UUID,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Includes disabled tasks — an admin needs to see what they parked."""
    return list(
        db.scalars(select(Task).where(Task.batch_id == batch_id).order_by(Task.order_number))
    )


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskCreate,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    clash = db.scalar(
        select(Task).where(
            Task.batch_id == payload.batch_id, Task.order_number == payload.order_number
        )
    )
    if clash is not None:
        raise HTTPException(
            status_code=409, detail="Another task already uses that position"
        )

    task = Task(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: uuid.UUID,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    submitted = db.scalar(
        select(func.count(TaskSubmission.id)).where(TaskSubmission.task_id == task_id)
    )
    if submitted:
        raise HTTPException(
            status_code=409, detail="Students have already submitted this task"
        )

    db.delete(task)
    db.commit()


@router.post("/tasks/reorder", response_model=list[TaskOut])
def reorder_tasks(
    batch_id: uuid.UUID,
    payload: TaskReorder,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Rewrites order_number from the supplied sequence. Position 0 stays reserved
    for the LinkedIn onboarding task, so technical tasks start at 1 and remain
    contiguous — the student app locks each task behind the previous one.
    """
    tasks = {
        t.id: t
        for t in db.scalars(select(Task).where(Task.batch_id == batch_id))
    }
    if set(payload.task_ids) != set(tasks):
        raise HTTPException(
            status_code=422, detail="Send every task id for this batch exactly once"
        )

    # Two passes so the unique (batch_id, order_number) constraint never trips.
    for offset, task_id in enumerate(payload.task_ids):
        tasks[task_id].order_number = -(offset + 1)
    db.flush()

    for position, task_id in enumerate(payload.task_ids, start=1):
        tasks[task_id].order_number = position
    db.commit()

    return list(
        db.scalars(select(Task).where(Task.batch_id == batch_id).order_by(Task.order_number))
    )


# ---------------------------------------------------------------------------
# Money, credentials, ops
# ---------------------------------------------------------------------------


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    status_filter: PaymentStatus | None = Query(default=None, alias="status"),
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = select(Payment)
    if status_filter:
        query = query.where(Payment.payment_status == status_filter)
    return list(db.scalars(query.order_by(Payment.created_at.desc()).limit(500)))


@router.get("/certificates", response_model=list[CertificateOut])
def list_certificates(
    _: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    from app.services.aggregate import certificate_out

    certificates = db.scalars(select(Certificate).order_by(Certificate.issued_at.desc()))
    return [certificate_out(db, c) for c in certificates]


@router.post("/certificates/{certificate_id}/revoke", response_model=CertificateOut)
def revoke_certificate(
    certificate_id: uuid.UUID,
    payload: dict,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    from app.services.aggregate import certificate_out

    certificate = db.get(Certificate, certificate_id)
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found")

    certificate.status = CertificateStatus.REVOKED
    certificate.revoked_reason = str(payload.get("reason", ""))[:2000]

    log_activity(db, admin.id, "Revoked certificate", "certificate", str(certificate.id))
    db.commit()
    db.refresh(certificate)
    return certificate_out(db, certificate)


@router.get("/analytics/overview")
def analytics_overview(
    _: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    students = list(db.scalars(select(User).where(User.role == UserRole.STUDENT)))
    by_stage: dict[str, int] = {}
    for student in students:
        stage = compute_stage(db, student.id).value
        by_stage[stage] = by_stage.get(stage, 0) + 1

    revenue = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.payment_status == PaymentStatus.SUCCESS
        )
    )

    return {
        "students_total": len(students),
        "students_by_stage": by_stage,
        "pending_linkedin_reviews": db.scalar(
            select(func.count(LinkedInSubmission.id)).where(
                LinkedInSubmission.status == ReviewStatus.PENDING
            )
        ),
        "pending_task_reviews": db.scalar(
            select(func.count(TaskSubmission.id)).where(
                TaskSubmission.status == SubmissionStatus.UNDER_REVIEW
            )
        ),
        "certificates_issued": db.scalar(
            select(func.count(Certificate.id)).where(
                Certificate.status == CertificateStatus.ISSUED
            )
        ),
        "revenue_paise": revenue or 0,
    }


@router.get("/activity-logs")
def list_activity_logs(
    user_id: uuid.UUID | None = None,
    module: str | None = None,
    _: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    query = select(ActivityLog)
    if user_id:
        query = query.where(ActivityLog.user_id == user_id)
    if module:
        query = query.where(ActivityLog.module == module)

    logs = db.scalars(query.order_by(ActivityLog.created_at.desc()).limit(300))
    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "activity": log.activity,
            "module": log.module,
            "entity_id": log.entity_id,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
