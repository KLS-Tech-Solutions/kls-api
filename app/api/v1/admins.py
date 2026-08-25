import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_super_admin
from app.core.security import generate_url_token, hash_password
from app.models import (
    AdminProfile,
    EmailToken,
    NotificationType,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.admins import (
    AcceptInviteRequest,
    AdminInviteRequest,
    AdminInviteResponse,
    AdminOut,
    AdminUpdateRequest,
    InvitePreview,
)
from app.services.email import send_admin_invite
from app.services.notifications import log_activity, notify

router = APIRouter(tags=["admins"])

INVITE_PURPOSE = "admin_invite"
INVITE_TTL_DAYS = 7


@router.get("/admin/admins", response_model=list[AdminOut])
def list_admins(
    _: User = Depends(get_current_super_admin), db: Session = Depends(get_db)
):
    return list(
        db.scalars(
            select(User)
            .where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
            .order_by(User.created_at)
        )
    )


@router.post(
    "/admin/admins/invite",
    response_model=AdminInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_admin(
    payload: AdminInviteRequest,
    background: BackgroundTasks,
    inviter: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Creates a pending administrator and a single-use invite link.

    No password is set here — the invitee chooses their own, so a working
    credential never travels by email or through a third party.
    """
    if payload.role == UserRole.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invite an admin or super_admin",
        )

    email = payload.email.lower()
    existing = db.scalar(select(User).where(User.email == email))

    if existing is not None and existing.status != UserStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    if existing is None:
        admin = User(
            full_name=payload.full_name.strip(),
            email=email,
            # Admins are invited by email and never phoned.
            phone=None,
            # Unusable placeholder — replaced when the invite is accepted.
            password_hash=hash_password(generate_url_token()),
            role=payload.role,
            status=UserStatus.PENDING,
            email_verified=False,
        )
        db.add(admin)
        db.flush()
        db.add(AdminProfile(user_id=admin.id))
    else:
        # Re-inviting someone who never accepted: refresh their details.
        admin = existing
        admin.full_name = payload.full_name.strip()
        admin.role = payload.role
        # Old links stop working the moment a new one is issued.
        db.query(EmailToken).filter(
            EmailToken.user_id == admin.id,
            EmailToken.purpose == INVITE_PURPOSE,
            EmailToken.used_at.is_(None),
        ).update({EmailToken.used_at: datetime.now(timezone.utc)}, synchronize_session=False)

    token = EmailToken(
        user_id=admin.id,
        token=generate_url_token(),
        purpose=INVITE_PURPOSE,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(token)
    db.flush()

    log_activity(db, inviter.id, f"Invited {admin.email}", "admin", str(admin.id))
    db.commit()
    db.refresh(admin)

    outbox = send_admin_invite(
        background,
        user_id=admin.id,
        to=admin.email,
        full_name=admin.full_name,
        invited_by=inviter.full_name,
        token=token.token,
        role=admin.role.value,
    )

    return AdminInviteResponse(
        admin=AdminOut.model_validate(admin),
        # Always returned. Even with email working, a new sending domain often
        # lands in spam — the inviter needs a link they can pass on directly.
        invite_url=outbox.action_url,
        email_delivered=outbox.delivered,
    )


@router.patch("/admin/admins/{admin_id}", response_model=AdminOut)
def update_admin(
    admin_id: uuid.UUID,
    payload: AdminUpdateRequest,
    actor: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    admin = db.get(User, admin_id)
    if admin is None or admin.role == UserRole.STUDENT:
        raise HTTPException(status_code=404, detail="Administrator not found")

    if admin.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot change your own role or status",
        )

    if payload.role is not None:
        if payload.role == UserRole.STUDENT:
            raise HTTPException(status_code=422, detail="Choose admin or super_admin")
        admin.role = payload.role

    if payload.status is not None:
        # Never leave the platform without a way in.
        if payload.status != UserStatus.ACTIVE and admin.role == UserRole.SUPER_ADMIN:
            remaining = db.scalar(
                select(User).where(
                    User.role == UserRole.SUPER_ADMIN,
                    User.status == UserStatus.ACTIVE,
                    User.id != admin.id,
                )
            )
            if remaining is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This is the last active super administrator",
                )
        admin.status = payload.status

    log_activity(db, actor.id, f"Updated admin {admin.email}", "admin", str(admin.id))
    db.commit()
    db.refresh(admin)
    return admin


@router.get("/auth/invite/{token}", response_model=InvitePreview)
def preview_invite(token: str, db: Session = Depends(get_db)):
    """Public — lets the accept screen show who the invite is for."""
    admin = _admin_for_token(db, token)
    return InvitePreview(
        full_name=admin.full_name, email=admin.email, role=admin.role
    )


@router.post("/auth/accept-invite", status_code=status.HTTP_204_NO_CONTENT)
def accept_invite(payload: AcceptInviteRequest, db: Session = Depends(get_db)):
    """Public — the invitee sets their own password and the account activates."""
    record = _token_record(db, payload.token)
    admin = db.get(User, record.user_id)
    if admin is None:
        raise HTTPException(status_code=400, detail="This invitation is not valid")

    admin.password_hash = hash_password(payload.password)
    admin.status = UserStatus.ACTIVE
    admin.email_verified = True
    record.used_at = datetime.now(timezone.utc)

    notify(
        db,
        admin.id,
        "Welcome to the KLS Academy console",
        "Your administrator account is active.",
        NotificationType.WELCOME,
    )
    log_activity(db, admin.id, "Accepted admin invitation", "admin", str(admin.id))
    db.commit()


def _token_record(db: Session, raw_token: str) -> EmailToken:
    record = db.scalar(
        select(EmailToken).where(
            EmailToken.token == raw_token, EmailToken.purpose == INVITE_PURPOSE
        )
    )
    if record is None or record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has already been used or is not valid",
        )

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired — ask for a new one",
        )

    return record


def _admin_for_token(db: Session, raw_token: str) -> User:
    record = _token_record(db, raw_token)
    admin = db.get(User, record.user_id)
    if admin is None:
        raise HTTPException(status_code=400, detail="This invitation is not valid")
    return admin
