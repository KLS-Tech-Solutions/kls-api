"""
Production seed.

Creates only what the platform cannot start without: the first super admin and
the email template rows. **No internship domains, batches, tasks or students** —
real content is created through the admin console so there is never demo data
to hunt down later.

    python scripts/seed.py

Idempotent — safe to run repeatedly.
"""

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    AdminProfile,
    EmailTemplate,
    User,
    UserRole,
    UserStatus,
)

# The subject and body here are *not* what students receive. Every workflow
# email is composed in `app/services/email.py`, which owns the layout and the
# copy. These rows exist so `email_logs.template_id` has something to point at,
# which is what makes "how many task-approved emails failed last week" a query
# rather than a guess. Editing the text below changes nothing a student sees.
EMAIL_TEMPLATES = [
    ("welcome", "Welcome to KLS Academy", "Your account is ready."),
    ("offer_letter", "Your KLS Academy offer letter", "Your offer letter is ready to download."),
    ("linkedin_approved", "LinkedIn task approved", "Your technical tasks are now unlocked."),
    ("linkedin_rejected", "LinkedIn task needs changes", "Please review the reviewer's comments."),
    ("task_assigned", "A new task is available", "A new task has been added to your internship."),
    ("task_approved", "Task approved", "Your submission has been approved."),
    ("task_rejected", "Task needs changes", "Please review the reviewer's remarks and resubmit."),
    ("certificate_issued", "Your certificate is ready", "Download your QR-verified certificate."),
    ("password_reset", "Reset your password", "Use the link to choose a new password."),
    ("admin_invite", "You've been invited to the KLS Academy console", "Set your password to begin."),
]


def seed() -> None:
    db = SessionLocal()
    try:
        created_templates = 0
        for name, subject, body in EMAIL_TEMPLATES:
            exists = db.scalar(
                select(EmailTemplate).where(EmailTemplate.template_name == name)
            )
            if exists is None:
                db.add(EmailTemplate(template_name=name, subject=subject, body=body))
                created_templates += 1

        admin = db.scalar(
            select(User).where(User.email == settings.FIRST_SUPERADMIN_EMAIL.lower())
        )
        if admin is None:
            # Hashing an empty string would produce a real, usable hash for a
            # password of "" — an open door on a public repository.
            if not settings.FIRST_SUPERADMIN_PASSWORD:
                raise SystemExit(
                    "Set FIRST_SUPERADMIN_PASSWORD in .env before seeding.\n"
                    "Generate one with: "
                    'python -c "import secrets; print(secrets.token_urlsafe(18))"'
                )

            admin = User(
                full_name="KLS Administrator",
                email=settings.FIRST_SUPERADMIN_EMAIL.lower(),
                phone="+919000000000",
                password_hash=hash_password(settings.FIRST_SUPERADMIN_PASSWORD),
                role=UserRole.SUPER_ADMIN,
                status=UserStatus.ACTIVE,
                email_verified=True,
            )
            db.add(admin)
            db.flush()
            db.add(AdminProfile(user_id=admin.id, designation="Super Administrator"))
            print(f"Created super admin: {admin.email}")
            print("  Sign in at the admin console and change this password.")
        else:
            print(f"Super admin already exists: {admin.email}")

        db.commit()

        print(f"Seed complete — {created_templates} email templates added.")
        print()
        print("The catalogue is intentionally empty. Create real internship")
        print("domains, batches and tasks from the admin console.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
