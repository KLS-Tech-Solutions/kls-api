"""
The editable certificate fee, and closing an account.

Both touch things that are hard to undo — one changes what students are
charged, the other scrubs personal data — so the guard rails are asserted
rather than assumed.
"""

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    AdminProfile,
    Certificate,
    CertificateStatus,
    StudentProfile,
    User,
    UserRole,
    UserStatus,
)
from tests.conftest import auth_headers
from tests.test_journey import STUDENT, catalogue, student_token  # noqa: F401


def make_admin(client, db_session, *, role: UserRole, email: str) -> str:
    admin = User(
        full_name="KLS Admin",
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

    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": "admin12345"}
    ).json()["access_token"]


@pytest.fixture()
def super_admin(client, db_session):
    return make_admin(
        client, db_session, role=UserRole.SUPER_ADMIN,
        email="super@klsacademy.example.com",
    )


@pytest.fixture()
def reviewer(client, db_session):
    return make_admin(
        client, db_session, role=UserRole.ADMIN,
        email="reviewer@klsacademy.example.com",
    )


# --------------------------------------------------------------------------
# The certificate fee
# --------------------------------------------------------------------------


def test_the_fee_falls_back_to_the_environment_before_it_is_ever_set(
    client, super_admin
):
    """A fresh database has no settings row and must still behave."""
    response = client.get("/api/v1/admin/settings", headers=auth_headers(super_admin))
    assert response.status_code == 200
    assert response.json()["certificate_fee_paise"] == 5000


def test_a_super_admin_can_change_the_fee(client, super_admin, student_token):
    response = client.patch(
        "/api/v1/admin/settings/certificate-fee",
        headers=auth_headers(super_admin),
        json={"amount_paise": 19900},
    )
    assert response.status_code == 200
    assert response.json()["certificate_fee_paise"] == 19900

    # The student's checkout screen reads the same value.
    journey = client.get(
        "/api/v1/me/journey", headers=auth_headers(student_token)
    ).json()
    assert journey["certificate_fee_paise"] == 19900


def test_a_reviewer_can_read_the_fee_but_not_change_it(client, reviewer):
    assert (
        client.get("/api/v1/admin/settings", headers=auth_headers(reviewer)).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/admin/settings/certificate-fee",
            headers=auth_headers(reviewer),
            json={"amount_paise": 100},
        ).status_code
        == 403
    )


def test_a_student_cannot_touch_the_fee(client, student_token):
    headers = auth_headers(student_token)
    assert client.get("/api/v1/admin/settings", headers=headers).status_code == 403
    assert (
        client.patch(
            "/api/v1/admin/settings/certificate-fee",
            headers=headers,
            json={"amount_paise": 100},
        ).status_code
        == 403
    )


def test_an_absurd_fee_is_refused(client, super_admin):
    """An extra zero is the classic payments mistake — the bounds catch it."""
    for amount in (0, 50, 500_000_000, -5000):
        response = client.patch(
            "/api/v1/admin/settings/certificate-fee",
            headers=auth_headers(super_admin),
            json={"amount_paise": amount},
        )
        assert response.status_code == 422, amount


def test_an_order_keeps_the_price_it_was_quoted(
    client, db_session, catalogue, student_token, super_admin, screenshot_files
):
    """
    A student who opens checkout and then sees the price change mid-flow must
    still pay what they were shown.
    """
    from app.models import Payment

    headers = auth_headers(student_token)
    admin_headers = auth_headers(super_admin)

    client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={
            "domain_id": str(catalogue["domain"].id),
            "batch_id": str(catalogue["batch"].id),
        },
    )
    client.post(
        "/api/v1/linkedin-submissions",
        headers=headers,
        json={"linkedin_post_url": "https://www.linkedin.com/posts/ananya_kls-1"},
    )
    queue = client.get(
        "/api/v1/admin/linkedin-submissions?status=pending", headers=admin_headers
    ).json()
    client.patch(
        f"/api/v1/admin/linkedin-submissions/{queue[0]['id']}",
        headers=admin_headers,
        json={"status": "approved", "remarks": "Verified."},
    )

    tasks = [
        t
        for t in client.get("/api/v1/me/tasks", headers=headers).json()
        if t["order_number"] > 0
    ]
    for task in sorted(tasks, key=lambda t: t["order_number"]):
        submission = client.post(
            "/api/v1/task-submissions",
            headers=headers,
            data={
                "task_id": task["id"],
                "title": task["title"],
                "github_url": "https://github.com/ananya/repo",
                "description": "A thorough written explanation of the work. " * 4,
            },
            files=screenshot_files,
        )
        client.post(
            f"/api/v1/admin/task-submissions/{submission.json()['id']}/review",
            headers=admin_headers,
            json={"status": "approved", "remarks": "Approved."},
        )

    order = client.post("/api/v1/payments/order", headers=headers).json()
    assert order["amount"] == 5000

    client.patch(
        "/api/v1/admin/settings/certificate-fee",
        headers=admin_headers,
        json={"amount_paise": 25000},
    )

    payment = db_session.scalar(
        select(Payment).where(Payment.razorpay_order_id == order["order_id"])
    )
    assert payment.amount == 5000, "an in-flight order must not be repriced"


# --------------------------------------------------------------------------
# Closing an account
# --------------------------------------------------------------------------


def test_closing_an_account_needs_the_password(client, student_token):
    response = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=auth_headers(student_token),
        json={"password": "not-the-password"},
    )
    assert response.status_code == 403

    # Still signed in and usable.
    assert (
        client.get("/api/v1/me/journey", headers=auth_headers(student_token)).status_code
        == 200
    )


def test_closing_an_account_scrubs_it_and_blocks_sign_in(
    client, db_session, student_token
):
    client.patch(
        "/api/v1/me/profile",
        headers=auth_headers(student_token),
        json={"college_name": "PES University", "linkedin_url": "https://in.linkedin.com/in/ananya"},
    )

    response = client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=auth_headers(student_token),
        json={"password": STUDENT["password"]},
    )
    assert response.status_code == 204

    user = db_session.scalar(select(User).where(User.id == _only_user_id(db_session)))
    assert user.status == UserStatus.DELETED
    assert user.deleted_at is not None
    assert user.full_name == "Deleted user"
    assert user.phone == ""
    assert STUDENT["email"] not in user.email
    assert user.email.endswith("@account.invalid")

    # Every trace of the profile is gone.
    assert (
        db_session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user.id)
        )
        is None
    )

    # The old credentials no longer work, and neither does the old session.
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": STUDENT["email"], "password": STUDENT["password"]},
        ).status_code
        == 401
    )
    assert (
        client.get("/api/v1/me/journey", headers=auth_headers(student_token)).status_code
        == 401
    )


def test_a_closed_account_keeps_its_certificate_verifiable(
    client, db_session, student_token
):
    """
    The whole reason deletion is soft. An employer's verification link must
    not start failing because the student later closed their account.
    """
    user_id = _only_user_id(db_session)
    certificate = Certificate(
        student_id=user_id,
        certificate_number="KLS-CERT-2026-09999",
        status=CertificateStatus.ISSUED,
    )
    db_session.add(certificate)
    db_session.commit()

    client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=auth_headers(student_token),
        json={"password": STUDENT["password"]},
    )

    response = client.get("/api/v1/certificates/verify/KLS-CERT-2026-09999")
    assert response.status_code == 200
    assert response.json()["student_name"] == STUDENT["full_name"], (
        "the certificate must remember who earned it, not read the scrubbed row"
    )


def test_a_closed_account_cannot_be_recovered_by_email(client, db_session, student_token):
    """Password reset and re-verification must not resurrect a closed account."""
    client.request(
        "DELETE",
        "/api/v1/me/account",
        headers=auth_headers(student_token),
        json={"password": STUDENT["password"]},
    )

    # Both endpoints always answer 204 by design, so assert the effect: no new
    # token is minted for the closed account.
    from app.models import EmailToken

    before = db_session.scalar(
        select(EmailToken).where(EmailToken.used_at.is_(None))
    )
    assert before is None

    client.post("/api/v1/auth/forgot-password", json={"email": STUDENT["email"]})
    client.post("/api/v1/auth/resend-verification", json={"email": STUDENT["email"]})

    assert (
        db_session.scalar(select(EmailToken).where(EmailToken.used_at.is_(None))) is None
    )


def _only_user_id(db_session):
    return db_session.scalar(select(User.id).where(User.role == UserRole.STUDENT))


def test_the_fee_survives_an_unmigrated_database(client, db_session, student_token):
    """
    `platform_settings` is newer than the rest of the schema. If the table is
    missing — `alembic upgrade head` not yet run — the read must fall back to
    the environment rather than 500, because it sits inside `/me/journey` and
    `/admin/settings` and would otherwise take down the student dashboard and
    the admin payments screen over a value that has a perfectly good default.
    """
    from app.models import PlatformSetting

    PlatformSetting.__table__.drop(db_session.get_bind())

    response = client.get("/api/v1/me/journey", headers=auth_headers(student_token))
    assert response.status_code == 200
    assert response.json()["certificate_fee_paise"] == 5000
