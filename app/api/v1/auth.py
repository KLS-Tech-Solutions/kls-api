from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.ratelimit import EMAIL_SEND, LOGIN, REGISTER, clear, enforce
from app.core.deps import get_current_user
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_url_token,
    hash_password,
    verify_password,
)
from app.models import (
    EmailToken,
    NotificationType,
    StudentProfile,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UserOut,
    VerifyEmailRequest,
)
from app.services.email import (
    send_password_reset,
    send_welcome_verification,
)
from app.services.notifications import log_activity, notify

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Registration sends a verification email, so an unlimited endpoint is a
    # way to spend the daily quota and stop real students signing up.
    enforce(request, REGISTER, scope="register")

    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=UserRole.STUDENT,
        status=UserStatus.PENDING,
        email_verified=False,
    )
    db.add(user)
    db.flush()

    db.add(StudentProfile(user_id=user.id))

    token = EmailToken(
        user_id=user.id,
        token=generate_url_token(),
        purpose="verify_email",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(token)

    notify(
        db,
        user.id,
        "Welcome to KLS Academy",
        "Your account is ready. Choose an internship domain to begin.",
        NotificationType.WELCOME,
    )
    log_activity(db, user.id, "Registered", "auth", str(user.id), _client_ip(request))
    db.commit()

    outbox = send_welcome_verification(
        background,
        user_id=user.id,
        to=user.email,
        full_name=user.full_name,
        token=token.token,
    )

    return {
        "email": user.email,
        "email_verified": False,
        "email_sent": outbox.delivered,
        # Returned only when email is unconfigured, so the flow is testable.
        "verification_token": None if outbox.delivered else token.token,
    }


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # Bucketed per address as well as per IP, so one account being attacked
    # does not lock out everyone else behind the same office connection.
    enforce(request, LOGIN, scope="login", identifier=payload.email)

    user = db.scalar(select(User).where(User.email == payload.email.lower()))

    # Same message either way — never reveal whether an email is registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if user.status == UserStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been closed",
        )

    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended",
        )

    # A correct password clears the counter — a legitimate person who fumbled
    # their password a few times is not then rate-limited on the next screen.
    clear(request, scope="login", identifier=payload.email)

    user.last_login_at = datetime.now(timezone.utc)
    log_activity(db, user.id, "Signed in", "auth", str(user.id), _client_ip(request))
    db.commit()

    return TokenPair(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.refresh_token, "refresh")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    import uuid as _uuid

    user = db.get(User, _uuid.UUID(claims["sub"]))
    if user is None or user.status in (UserStatus.SUSPENDED, UserStatus.DELETED):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid"
        )

    return RefreshResponse(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Tokens are stateless; the client clears its cookies. Logged for audit.
    log_activity(db, user.id, "Signed out", "auth", str(user.id))
    db.commit()


@router.get("/me", response_model=dict)
def me(user: User = Depends(get_current_user)):
    return {"user": UserOut.model_validate(user).model_dump(mode="json")}


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    token = _consume_token(db, payload.token, "verify_email")
    user = db.get(User, token.user_id)
    if user is not None:
        user.email_verified = True
        user.status = UserStatus.ACTIVE
    db.commit()


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Pointed at someone else's address this is an inbox-flooding tool, and it
    # spends the platform's daily email allowance either way.
    enforce(request, EMAIL_SEND, scope="forgot", identifier=payload.email)

    user = db.scalar(select(User).where(User.email == payload.email.lower()))

    # Always 204 — an attacker must not learn which emails are registered.
    if user is not None and user.status != UserStatus.DELETED:
        token = EmailToken(
            user_id=user.id,
            token=generate_url_token(),
            purpose="reset_password",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(token)
        db.commit()

        send_password_reset(
            background, user_id=user.id, to=user.email, token=token.token
        )


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
def resend_verification(
    payload: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Always 204, like forgot-password — this endpoint must not confirm whether
    an address is registered or already verified.
    """
    enforce(request, EMAIL_SEND, scope="resend", identifier=payload.email)

    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or user.email_verified or user.status == UserStatus.DELETED:
        return

    # Any earlier link stops working the moment a new one is issued.
    db.query(EmailToken).filter(
        EmailToken.user_id == user.id,
        EmailToken.purpose == "verify_email",
        EmailToken.used_at.is_(None),
    ).update({EmailToken.used_at: datetime.now(timezone.utc)}, synchronize_session=False)

    token = EmailToken(
        user_id=user.id,
        token=generate_url_token(),
        purpose="verify_email",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(token)
    db.commit()

    send_welcome_verification(
        background,
        user_id=user.id,
        to=user.email,
        full_name=user.full_name,
        token=token.token,
    )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token = _consume_token(db, payload.token, "reset_password")
    user = db.get(User, token.user_id)
    if user is not None:
        user.password_hash = hash_password(payload.password)
    db.commit()


def _consume_token(db: Session, raw_token: str, purpose: str) -> EmailToken:
    token = db.scalar(
        select(EmailToken).where(
            EmailToken.token == raw_token, EmailToken.purpose == purpose
        )
    )
    if token is None or token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This link is not valid"
        )

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This link has expired"
        )

    token.used_at = datetime.now(timezone.utc)
    return token
