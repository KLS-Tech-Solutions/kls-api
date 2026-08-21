"""
Study notes — chapter-wise material for each internship domain.

Students read these before starting the technical tasks. Nothing is locked
behind them: the tasks page prompts, and that is all. A hard gate would produce
support requests from people who read the PDF elsewhere and cannot see why they
are stuck, and the point of the notes is to make the internship feel prepared,
not to police it.

Chapters belong to a domain, so material is uploaded once per domain rather
than per batch.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    get_current_admin,
    get_current_student,
    get_current_user,
)
from app.models import (
    ChapterRead,
    InternshipDomain,
    LearningChapter,
    PublishStatus,
    User,
)
from app.schemas.internship import (
    ChapterCreate,
    ChapterOut,
    ChapterReorder,
    ChapterUpdate,
)
from app.services.journey import get_active_enrollment
from app.services.notifications import log_activity
from app.services.storage import StorageError, read_bytes, save_chapter_pdf

router = APIRouter(tags=["learning"])


def _chapter_or_404(db: Session, chapter_id: uuid.UUID) -> LearningChapter:
    chapter = db.get(LearningChapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------


@router.get("/me/chapters", response_model=list[ChapterOut])
def my_chapters(
    student: User = Depends(get_current_student), db: Session = Depends(get_db)
):
    """
    The notes for the internship the student is currently taking.

    Empty when they are not enrolled — there is no domain to draw material
    from, and showing every domain's notes at once would be noise.
    """
    enrollment = get_active_enrollment(db, student.id)
    if enrollment is None:
        return []

    from app.models import InternshipBatch

    batch = db.get(InternshipBatch, enrollment.batch_id)
    if batch is None:
        return []

    chapters = list(
        db.scalars(
            select(LearningChapter)
            .where(
                LearningChapter.domain_id == batch.domain_id,
                LearningChapter.status == PublishStatus.ACTIVE,
            )
            .order_by(LearningChapter.order_number)
        )
    )

    read_ids = set(
        db.scalars(
            select(ChapterRead.chapter_id).where(ChapterRead.student_id == student.id)
        )
    )

    out = []
    for chapter in chapters:
        data = ChapterOut.model_validate(chapter)
        data.is_read = chapter.id in read_ids
        out.append(data)
    return out


@router.get("/me/chapters/{chapter_id}/download")
def download_chapter(
    chapter_id: uuid.UUID,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """
    Streams the chapter PDF through the API rather than exposing a storage URL.

    Same reasoning as the offer letters: nothing student-facing is served from
    a public bucket, so the material cannot be scraped wholesale by anyone who
    guesses a filename.
    """
    chapter = _chapter_or_404(db, chapter_id)
    if chapter.status != PublishStatus.ACTIVE or not chapter.pdf_url:
        raise HTTPException(status_code=404, detail="That chapter has no notes yet")

    pdf = read_bytes(chapter.pdf_url)
    if pdf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The notes file is missing — an administrator has been notified",
        )

    filename = chapter.pdf_filename or f"{chapter.title}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/me/chapters/{chapter_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_chapter_read(
    chapter_id: uuid.UUID,
    student: User = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Idempotent — marking a chapter read twice is not an error."""
    _chapter_or_404(db, chapter_id)

    existing = db.scalar(
        select(ChapterRead).where(
            ChapterRead.student_id == student.id,
            ChapterRead.chapter_id == chapter_id,
        )
    )
    if existing is None:
        db.add(ChapterRead(student_id=student.id, chapter_id=chapter_id))
        db.commit()


# ---------------------------------------------------------------------------
# Admin
#
# Open to **any** admin, not just super admins. Notes are teaching material:
# whoever is reviewing a domain's submissions is the person best placed to fix
# a chapter, and routing that through one super admin makes the material go
# stale. The catalogue itself — domains, batches, tasks — stays super-admin
# only, because changing a batch mid-flight moves the goalposts for students
# already enrolled in it.
#
# Every change records who made it in `updated_by`, and in the activity log.
# ---------------------------------------------------------------------------


@router.get("/admin/chapters", response_model=list[ChapterOut])
def list_chapters(
    domain_id: uuid.UUID | None = None,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = select(LearningChapter).order_by(
        LearningChapter.domain_id, LearningChapter.order_number
    )
    if domain_id is not None:
        query = query.where(LearningChapter.domain_id == domain_id)

    chapters = list(db.scalars(query))

    # One lookup for every editor rather than a query per row.
    editor_ids = {c.updated_by for c in chapters if c.updated_by}
    names = (
        dict(
            db.execute(
                select(User.id, User.full_name).where(User.id.in_(editor_ids))
            ).all()
        )
        if editor_ids
        else {}
    )

    out = []
    for chapter in chapters:
        data = ChapterOut.model_validate(chapter)
        data.updated_by_name = names.get(chapter.updated_by, "")
        out.append(data)
    return out


@router.post("/admin/chapters", response_model=ChapterOut, status_code=201)
def create_chapter(
    payload: ChapterCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if db.get(InternshipDomain, payload.domain_id) is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    clash = db.scalar(
        select(LearningChapter.id).where(
            LearningChapter.domain_id == payload.domain_id,
            LearningChapter.order_number == payload.order_number,
        )
    )
    if clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Chapter {payload.order_number} already exists in this domain",
        )

    chapter = LearningChapter(**payload.model_dump(), updated_by=admin.id)
    db.add(chapter)
    log_activity(db, admin.id, f"Added chapter: {payload.title}", "learning")
    db.commit()
    db.refresh(chapter)
    return chapter


@router.patch("/admin/chapters/{chapter_id}", response_model=ChapterOut)
def update_chapter(
    chapter_id: uuid.UUID,
    payload: ChapterUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    chapter = _chapter_or_404(db, chapter_id)
    data = payload.model_dump(exclude_unset=True)

    new_position = data.get("order_number")
    if new_position is not None and new_position != chapter.order_number:
        clash = db.scalar(
            select(LearningChapter.id).where(
                LearningChapter.domain_id == chapter.domain_id,
                LearningChapter.order_number == new_position,
                LearningChapter.id != chapter.id,
            )
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Chapter {new_position} already exists in this domain",
            )

    for field, value in data.items():
        setattr(chapter, field, value)
    chapter.updated_by = admin.id

    log_activity(db, admin.id, f"Updated chapter: {chapter.title}", "learning")
    db.commit()
    db.refresh(chapter)
    return chapter


@router.post("/admin/chapters/{chapter_id}/pdf", response_model=ChapterOut)
async def upload_chapter_pdf(
    chapter_id: uuid.UUID,
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Replaces the chapter's PDF. Uploading again overwrites the previous one."""
    chapter = _chapter_or_404(db, chapter_id)
    data = await file.read()

    try:
        chapter.pdf_url = save_chapter_pdf(
            data, chapter.id, file.filename, file.content_type
        )
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    chapter.pdf_filename = file.filename
    chapter.pdf_size_bytes = len(data)
    chapter.updated_by = admin.id

    log_activity(db, admin.id, f"Uploaded notes for: {chapter.title}", "learning")
    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/admin/chapters/{chapter_id}", status_code=204)
def delete_chapter(
    chapter_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    chapter = _chapter_or_404(db, chapter_id)
    log_activity(db, admin.id, f"Deleted chapter: {chapter.title}", "learning")
    db.delete(chapter)
    db.commit()


@router.post("/admin/chapters/reorder", response_model=list[ChapterOut])
def reorder_chapters(
    payload: ChapterReorder,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Takes the full ordered list for one domain, so positions cannot end up with
    gaps or duplicates.

    Written in two passes because `(domain_id, order_number)` is unique: moving
    chapter 3 to position 1 while 1 still holds it would violate the constraint
    mid-update. Parking everything in a negative range first avoids that.
    """
    chapters = list(
        db.scalars(
            select(LearningChapter).where(LearningChapter.id.in_(payload.chapter_ids))
        )
    )
    if len(chapters) != len(payload.chapter_ids):
        raise HTTPException(status_code=404, detail="One of those chapters is missing")

    if len({c.domain_id for c in chapters}) > 1:
        raise HTTPException(
            status_code=422, detail="Reorder one domain's chapters at a time"
        )

    by_id = {c.id: c for c in chapters}
    for offset, chapter_id in enumerate(payload.chapter_ids):
        by_id[chapter_id].order_number = -(offset + 1)
    db.flush()

    for offset, chapter_id in enumerate(payload.chapter_ids):
        by_id[chapter_id].order_number = offset + 1

    log_activity(db, admin.id, "Reordered chapters", "learning")
    db.commit()

    return list(
        db.scalars(
            select(LearningChapter)
            .where(LearningChapter.domain_id == chapters[0].domain_id)
            .order_by(LearningChapter.order_number)
        )
    )


# ---------------------------------------------------------------------------
# Screenshots
#
# Task screenshots used to sit on a public bucket and were rendered straight
# from that URL. They are private now, so both apps fetch them here and the
# route decides whether the caller is allowed to look.
# ---------------------------------------------------------------------------


@router.get("/screenshots/{screenshot_id}")
def download_screenshot(
    screenshot_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The student who submitted it, or any admin reviewing it."""
    from app.models import TaskScreenshot, TaskSubmission

    shot = db.get(TaskScreenshot, screenshot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    submission = db.get(TaskSubmission, shot.submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    if not user.is_admin and submission.student_id != user.id:
        # 404 rather than 403: one student has no business learning that
        # another student's screenshot exists.
        raise HTTPException(status_code=404, detail="Screenshot not found")

    data = read_bytes(shot.image_url)
    if data is None:
        raise HTTPException(status_code=404, detail="That image is no longer stored")

    suffix = shot.image_url.rsplit(".", 1)[-1].lower()
    media_type = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}.get(
        suffix, "image/png"
    )
    return Response(content=data, media_type=media_type)
