import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from app.core.config import settings

_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    False for a wrong password *and* for a malformed stored hash.

    `InvalidHashError` matters: a scrubbed or corrupt row must produce a failed
    login rather than a 500. Anything outside these three is a real fault in
    the hasher and is left to propagate — swallowing it would turn a broken
    argon2 install into "everybody's password is wrong".
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _create_token(
    subject: str, token_type: TokenType, expires: timedelta, claims: dict[str, Any] | None = None
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": secrets.token_urlsafe(16),
        **(claims or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: str, token_version: int = 0) -> str:
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        {"role": role, "tv": token_version},
    )


def create_refresh_token(user_id: uuid.UUID, token_version: int = 0) -> str:
    return _create_token(
        str(user_id),
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        {"tv": token_version},
    )


class TokenError(Exception):
    """Raised when a token is missing, expired, malformed or the wrong type."""


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Token is invalid") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")

    return payload


def token_is_current(payload: dict[str, Any], token_version: int) -> bool:
    """
    Whether a decoded token predates the account's last revocation.

    A token issued before this column existed carries no `tv` claim. Those are
    treated as version 0, which is what every existing row holds, so nobody is
    signed out by the deployment that introduces this. The moment an account
    revokes anything its version becomes 1 and the old claim-less tokens stop
    matching — which is exactly the behaviour wanted.
    """
    return int(payload.get("tv", 0)) == token_version


def generate_url_token() -> str:
    """Email verification and password reset links."""
    return secrets.token_urlsafe(32)
