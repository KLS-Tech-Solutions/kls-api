"""
JWT and authorisation audit, expressed as tests so regressions are caught
rather than discovered.
"""

from datetime import date, timezone

import jwt

from app.core.config import settings
from app.core.dates import today_in_ist
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import AdminProfile, User, UserRole, UserStatus
from tests.conftest import auth_headers

# Comfortably an adult, and stays that way — the alternative is a literal that
# quietly ages into a test failure.
ADULT_DOB = date(today_in_ist().year - 22, 6, 15).isoformat()

STUDENT = {
    "full_name": "Ananya Rao",
    "email": "ananya@example.com",
    "phone": "9845012345",
    "password": "kls12345",
    # Registration requires a date of birth and refuses under-18s. A fixed
    # date would start failing the day it drifts under the minimum, so this
    # is anchored to the clock rather than written out.
    "date_of_birth": ADULT_DOB,
}


def make_admin(db_session, role=UserRole.ADMIN, email="admin@klsacademy.example.com"):
    admin = User(
        full_name="Admin",
        email=email,
        phone="+919000000000",
        password_hash=hash_password("admin12345"),
        role=role,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db_session.add(admin)
    db_session.flush()
    db_session.add(AdminProfile(user_id=admin.id))
    db_session.commit()
    return admin


# --- Password storage -------------------------------------------------------


def test_passwords_are_argon2_hashed_not_stored():
    hashed = hash_password("kls12345")
    assert hashed.startswith("$argon2id$")
    assert "kls12345" not in hashed
    assert verify_password("kls12345", hashed)
    assert not verify_password("wrong12345", hashed)


def test_same_password_produces_different_hashes():
    """Per-password salt — two users with the same password must not match."""
    assert hash_password("kls12345") != hash_password("kls12345")


# --- Token contents ---------------------------------------------------------


def test_access_token_carries_role_and_expiry(db_session):
    admin = make_admin(db_session)
    token = create_access_token(admin.id, admin.role.value)
    claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    assert claims["sub"] == str(admin.id)
    assert claims["role"] == "admin"
    assert claims["type"] == "access"
    assert claims["exp"] > claims["iat"]
    # A unique id per token, so individual tokens can be revoked later.
    assert claims["jti"]


def test_refresh_token_carries_no_role(db_session):
    """A refresh token must not be usable as proof of privilege."""
    admin = make_admin(db_session)
    claims = jwt.decode(
        create_refresh_token(admin.id),
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    assert claims["type"] == "refresh"
    assert "role" not in claims


# --- Token rejection --------------------------------------------------------


def test_token_signed_with_another_key_is_rejected(client, db_session):
    admin = make_admin(db_session)
    forged = jwt.encode(
        {"sub": str(admin.id), "type": "access", "role": "super_admin"},
        "not-the-real-secret",
        algorithm="HS256",
    )
    response = client.get("/api/v1/me/journey", headers=auth_headers(forged))
    assert response.status_code == 401


def test_expired_token_is_rejected(client, db_session):
    from datetime import datetime, timedelta, timezone

    admin = make_admin(db_session)
    expired = jwt.encode(
        {
            "sub": str(admin.id),
            "type": "access",
            "role": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    response = client.get("/api/v1/admin/students", headers=auth_headers(expired))
    assert response.status_code == 401


def test_refresh_token_cannot_authenticate_a_request(client, db_session):
    """The type claim stops a long-lived token being used as an access token."""
    admin = make_admin(db_session)
    refresh = create_refresh_token(admin.id)
    response = client.get("/api/v1/admin/students", headers=auth_headers(refresh))
    assert response.status_code == 401


def test_garbage_and_missing_tokens_are_rejected(client):
    assert client.get("/api/v1/me/journey").status_code == 401
    assert (
        client.get("/api/v1/me/journey", headers={"Authorization": "Bearer nonsense"}).status_code
        == 401
    )
    assert (
        client.get("/api/v1/me/journey", headers={"Authorization": "Basic abc"}).status_code
        == 401
    )


def test_suspended_account_cannot_use_a_valid_token(client, db_session):
    """Suspension takes effect immediately, without waiting for expiry."""
    admin = make_admin(db_session)
    token = create_access_token(admin.id, admin.role.value)
    assert client.get("/api/v1/admin/students", headers=auth_headers(token)).status_code == 200

    admin.status = UserStatus.SUSPENDED
    db_session.commit()

    assert client.get("/api/v1/admin/students", headers=auth_headers(token)).status_code == 403


# --- Role separation --------------------------------------------------------


def test_student_token_cannot_reach_admin_routes(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    ).json()["access_token"]

    for path in [
        "/api/v1/admin/students",
        "/api/v1/admin/task-submissions",
        "/api/v1/admin/analytics/overview",
        "/api/v1/admin/admins",
    ]:
        assert client.get(path, headers=auth_headers(token)).status_code == 403, path


def test_admin_token_cannot_reach_student_routes(client, db_session):
    make_admin(db_session)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@klsacademy.example.com", "password": "admin12345"},
    ).json()["access_token"]

    assert client.get("/api/v1/me/journey", headers=auth_headers(token)).status_code == 403


def test_plain_admin_cannot_perform_super_admin_actions(client, db_session):
    make_admin(db_session, role=UserRole.ADMIN)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@klsacademy.example.com", "password": "admin12345"},
    ).json()["access_token"]

    forbidden = [
        client.post(
            "/api/v1/admin/internship-domains",
            headers=auth_headers(token),
            json={
                "slug": "x",
                "title": "Test",
                "description": "A description here.",
                "duration": "4 weeks",
                "difficulty": "beginner",
            },
        ),
        client.get("/api/v1/admin/activity-logs", headers=auth_headers(token)),
        client.get("/api/v1/admin/admins", headers=auth_headers(token)),
    ]
    assert all(r.status_code == 403 for r in forbidden)


def test_role_in_the_token_does_not_grant_access(client, db_session):
    """
    Authorisation reads the database, not the token claim — so a token minted
    with an inflated role is still only worth the account behind it.
    """
    client.post("/api/v1/auth/register", json=STUDENT)
    from sqlalchemy import select

    student = db_session.scalar(select(User).where(User.email == STUDENT["email"]))
    inflated = create_access_token(student.id, "super_admin")

    assert client.get("/api/v1/admin/students", headers=auth_headers(inflated)).status_code == 403
