from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ratelimit import EMAIL_SEND, LOGIN, REGISTER, clear, enforce
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_url_token,
    hash_password,
    token_is_current,
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
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UserOut,
)
from app.services.email import (
    send_password_reset,
    send_welcome,
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
    # Registration sends a welcome email, so an unlimited endpoint is a way to
    # spend the daily quota and stop real students signing up.
    enforce(request, REGISTER, scope="register")

    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # The account is usable immediately. There is no verification step: the
    # form is the whole of signing up, and the welcome email is a courtesy
    # rather than a gate.
    #
    # This is not as large a change as it looks. `login` has only ever refused
    # DELETED and SUSPENDED accounts — a PENDING one could always sign in — so
    # verification was already decorative for students. What it did do was send
    # people to a "check your inbox" page and leave `email_verified` false
    # forever for anyone who ignored it.
    #
    # The cost is stated plainly: nothing now proves the address is real. A
    # typo means every notification silently fails, and someone can register
    # with an address they do not own. Both are accepted trade-offs for
    # removing a step that stopped perhaps a third of signups.
    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        phone=payload.phone,
        state=payload.state,
        country=payload.country,
        password_hash=hash_password(payload.password),
        date_of_birth=payload.date_of_birth,
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db.add(user)
    db.flush()

    db.add(StudentProfile(user_id=user.id))

    notify(
        db,
        user.id,
        "Welcome to KLS Academy",
        "Your account is ready. Choose an internship domain to begin.",
        NotificationType.WELCOME,
    )
    log_activity(db, user.id, "Registered", "auth", str(user.id), _client_ip(request))
    db.commit()

    outbox = send_welcome(
        background,
        user_id=user.id,
        to=user.email,
        full_name=user.full_name,
    )

    return {
        "email": user.email,
        "email_verified": True,
        # Whether the welcome mail went out. Nothing depends on it — the
        # account works either way — but the form uses it to decide whether to
        # mention the inbox at all.
        "email_sent": outbox.delivered,
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
        access_token=create_access_token(user.id, user.role.value, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
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

    try:
        user_id = _uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid"
        ) from exc

    user = db.get(User, user_id)
    if user is None or user.status in (UserStatus.SUSPENDED, UserStatus.DELETED):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid"
        )

    # The refresh path is the one that matters. An access token expires in
    # half an hour on its own; a refresh token is good for thirty days and is
    # what turns a single theft into a month of access.
    if not token_is_current(claims, user.token_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid"
        )

    return RefreshResponse(
        access_token=create_access_token(user.id, user.role.value, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ordinary sign-out clears the cookies on this device and nothing else.

    `all_devices` revokes every token the account holds, which is the button
    you want after leaving yourself signed in on a college lab machine. It is
    not the default: someone signing out of their laptop does not expect to be
    thrown out of the app on their phone at the same time.
    """
    if payload is not None and payload.all_devices:
        user.token_version += 1
        log_activity(db, user.id, "Signed out of all devices", "auth", str(user.id))
    else:
        log_activity(db, user.id, "Signed out", "auth", str(user.id))
    db.commit()


@router.get("/me", response_model=dict)
def me(user: User = Depends(get_current_user)):
    return {"user": UserOut.model_validate(user).model_dump(mode="json")}


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


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    token = _consume_token(db, payload.token, "reset_password")
    user = db.get(User, token.user_id)
    if user is not None:
        user.password_hash = hash_password(payload.password)
        # The reason most people reset a password is that they think someone
        # else has it. Changing the password alone would leave the intruder's
        # 30-day refresh token working, which makes the reset theatre.
        user.token_version += 1
        log_activity(db, user.id, "Password reset; all sessions ended", "auth", str(user.id))
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
