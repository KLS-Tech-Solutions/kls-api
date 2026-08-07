"""
Wipes all internship content and student activity, leaving administrators and
email templates in place.

    python scripts/reset_content.py --yes

Use this once to clear anything created while testing. It is destructive and
deliberately requires the flag.
"""

import sys

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models import (
    ActivityLog,
    AdminReview,
    Certificate,
    CertificateVerificationLog,
    EmailLog,
    EmailToken,
    Enrollment,
    InternshipBatch,
    InternshipDomain,
    LinkedInSubmission,
    Notification,
    OfferLetter,
    Payment,
    StudentProfile,
    Task,
    TaskScreenshot,
    TaskSubmission,
    User,
    UserRole,
)

# Order matters — children before parents.
CONTENT_TABLES = [
    CertificateVerificationLog,
    Certificate,
    Payment,
    AdminReview,
    TaskScreenshot,
    TaskSubmission,
    LinkedInSubmission,
    OfferLetter,
    Enrollment,
    Task,
    InternshipBatch,
    InternshipDomain,
]


def reset() -> None:
    db = SessionLocal()
    try:
        for model in CONTENT_TABLES:
            removed = db.execute(delete(model)).rowcount
            print(f"  {model.__tablename__}: {removed} removed")

        student_ids = list(
            db.scalars(select(User.id).where(User.role == UserRole.STUDENT))
        )
        if student_ids:
            for model in (Notification, EmailLog, EmailToken, ActivityLog):
                db.execute(delete(model).where(model.user_id.in_(student_ids)))
            db.execute(delete(StudentProfile).where(StudentProfile.user_id.in_(student_ids)))
            db.execute(delete(User).where(User.id.in_(student_ids)))
            print(f"  students: {len(student_ids)} removed")

        db.commit()
        print("\nContent reset. Administrators and email templates were kept.")
    finally:
        db.close()


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        print("This deletes every domain, batch, task, student and submission.")
        print("Re-run with --yes to confirm.")
        raise SystemExit(1)
    reset()
