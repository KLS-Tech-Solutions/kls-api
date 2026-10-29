"""
Workflow emails.

SMTP is disabled in tests (see conftest), so these assert that the right email
is *composed and queued* at each step — subject, recipient, action link, and
the spam-folder guidance every message carries.
"""

from datetime import date, timedelta

import pytest

from app.core.dates import today_in_ist
from app.core.security import hash_password
from app.models import (
    AdminProfile,
    Difficulty,
    InternshipBatch,
    InternshipDomain,
    LinkedInSubmission,
    OfferLetter,
    ReviewStatus,
    Task,
    User,
    UserRole,
    UserStatus,
)
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


@pytest.fixture()
def outbox(monkeypatch):
    """Captures every email instead of delivering it."""
    from app.services import email as email_service

    sent: list[dict] = []

    def capture(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(email_service, "_deliver_and_log", capture)
    return sent


def subjects(outbox) -> list[str]:
    return [message["subject"] for message in outbox]


def only(outbox, fragment: str) -> dict:
    matches = [m for m in outbox if fragment.lower() in m["subject"].lower()]
    assert matches, f"no email matching {fragment!r} in {subjects(outbox)}"
    return matches[-1]


# --- Every email carries the same guidance --------------------------------


def test_every_email_tells_people_to_check_spam(client, outbox):
    client.post("/api/v1/auth/register", json=STUDENT)

    # Registration now sends a welcome, not a verification request. The
    # guidance itself comes from the shared layout, so this still covers every
    # email the platform sends.
    message = only(outbox, "welcome")
    assert "Spam" in message["html"] and "Junk" in message["html"]
    assert "Bin" in message["html"]
    assert "Spam, Junk or Bin" in message["text"]


def test_emails_are_sent_as_html_and_plain_text(client, outbox):
    client.post("/api/v1/auth/register", json=STUDENT)

    message = only(outbox, "welcome")
    assert message["html"].lstrip().startswith("<!doctype html>")
    assert "KLS ACADEMY" in message["html"]
    # A plain-text alternative matters: some clients and filters reject
    # HTML-only mail outright.
    assert "KLS Tech Solutions" in message["text"]
    assert "<" not in message["text"]


# --- Account emails --------------------------------------------------------


def test_registration_sends_a_welcome_with_nothing_to_click(client, outbox):
    """
    The welcome email is a courtesy, not a gate. There is no verification step,
    so it must not contain a link that looks like one — a student who thinks
    their account is pending until they click something will wait forever.
    """
    response = client.post("/api/v1/auth/register", json=STUDENT)
    assert response.status_code == 201

    message = only(outbox, "welcome")
    assert message["to"] == "ananya@example.com"
    assert "/verify-email" not in message["html"]
    assert "token=" not in message["html"]
    # It does tell them which address they used, which is what makes a later
    # password reset findable.
    assert "ananya@example.com" in message["html"]


def test_the_account_works_immediately_without_touching_email(client):
    """Register, then sign in. No step in between."""
    client.post("/api/v1/auth/register", json=STUDENT)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email_verified"] is True
    assert response.json()["user"]["status"] == "active"


def test_password_reset_sends_a_link(client, outbox):
    client.post("/api/v1/auth/register", json=STUDENT)
    outbox.clear()

    client.post("/api/v1/auth/forgot-password", json={"email": STUDENT["email"]})

    message = only(outbox, "reset your")
    assert "/reset-password?token=" in message["html"]


def test_no_reset_email_for_an_unknown_address(client, outbox):
    """Silence is the point — the endpoint must not confirm who is registered."""
    response = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 204
    assert outbox == []


def test_the_verification_endpoints_are_gone(client):
    """
    Both routes were removed with the verification step. They are asserted
    absent rather than simply deleted from the suite, so that re-adding one by
    accident — and with it a half-wired flow that leaves accounts PENDING —
    fails here rather than in production.
    """
    for path in ("/api/v1/auth/verify-email", "/api/v1/auth/resend-verification"):
        assert client.post(path, json={"token": "x", "email": "a@example.com"}).status_code == 404


# --- Journey emails --------------------------------------------------------


@pytest.fixture()
def catalogue(db_session):
    domain = InternshipDomain(
        slug="full-stack-python",
        title="Full Stack Python",
        description="Build a complete web application.",
        duration="4 weeks",
        difficulty=Difficulty.INTERMEDIATE,
    )
    db_session.add(domain)
    db_session.flush()
    batch = InternshipBatch(
        domain_id=domain.id,
        batch_name="Batch 01",
        start_date=date.today(),
        end_date=date.today() + timedelta(weeks=4),
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        Task(batch_id=batch.id, title="LinkedIn", description="Post it.", order_number=0)
    )
    db_session.add(
        Task(
            batch_id=batch.id,
            title="Task 1 REST API",
            description="Build the service.",
            order_number=1,
            min_screenshots=1,
            min_explanation_chars=20,
        )
    )
    db_session.commit()
    return {"domain": domain, "batch": batch}


@pytest.fixture()
def admin_token(client, db_session):
    admin = User(
        full_name="KLS Admin",
        email="admin@klsacademy.example.com",
        phone="+919000000000",
        password_hash=hash_password("admin12345"),
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db_session.add(admin)
    db_session.flush()
    db_session.add(AdminProfile(user_id=admin.id))
    db_session.commit()
    return client.post(
        "/api/v1/auth/login",
        json={"email": "admin@klsacademy.example.com", "password": "admin12345"},
    ).json()["access_token"]


@pytest.fixture()
def student_token(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    return client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    ).json()["access_token"]


def test_enrolment_emails_the_offer_letter(client, catalogue, student_token, outbox):
    outbox.clear()
    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(student_token),
        json={
            "domain_id": str(catalogue["domain"].id),
            "batch_id": str(catalogue["batch"].id),
        },
    )

    message = only(outbox, "offer letter")
    assert "KLS-ACAD-" in message["subject"]
    assert "/dashboard/offer-letter" in message["html"]
    assert "LinkedIn" in message["html"], "the email must state the next step"


def test_review_decisions_email_the_student(
    client, db_session, catalogue, student_token, admin_token, outbox
):
    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(student_token),
        json={
            "domain_id": str(catalogue["domain"].id),
            "batch_id": str(catalogue["batch"].id),
        },
    )
    client.post(
        "/api/v1/linkedin-submissions",
        headers=auth_headers(student_token),
        json={"linkedin_post_url": "https://www.linkedin.com/posts/x_y-activity-1"},
    )

    queue = client.get(
        "/api/v1/admin/linkedin-submissions?status=pending", headers=auth_headers(admin_token)
    ).json()

    # --- rejection carries the reviewer's words ---------------------------
    outbox.clear()
    client.patch(
        f"/api/v1/admin/linkedin-submissions/{queue[0]['id']}",
        headers=auth_headers(admin_token),
        json={"status": "rejected", "remarks": "The post is not public."},
    )
    message = only(outbox, "needs changes")
    assert "The post is not public." in message["html"]
    assert "The post is not public." in message["text"]

    # --- approval says what it unlocked ------------------------------------
    outbox.clear()
    client.patch(
        f"/api/v1/admin/linkedin-submissions/{queue[0]['id']}",
        headers=auth_headers(admin_token),
        json={"status": "approved", "remarks": "Verified."},
    )
    message = only(outbox, "approved")
    assert "unlocked" in message["html"].lower()


def test_final_approval_issues_and_emails_the_certificate(
    client, catalogue, student_token, admin_token, outbox, screenshot_files
):
    headers = auth_headers(student_token)
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
        json={"linkedin_post_url": "https://www.linkedin.com/posts/x_y-activity-1"},
    )
    queue = client.get(
        "/api/v1/admin/linkedin-submissions?status=pending", headers=auth_headers(admin_token)
    ).json()
    client.patch(
        f"/api/v1/admin/linkedin-submissions/{queue[0]['id']}",
        headers=auth_headers(admin_token),
        json={"status": "approved", "remarks": "Verified."},
    )

    tasks = client.get("/api/v1/me/tasks", headers=headers).json()
    technical = next(t for t in tasks if t["order_number"] == 1)

    submission = client.post(
        "/api/v1/task-submissions",
        headers=headers,
        files=screenshot_files[:1],
        data={
            "task_id": technical["id"],
            "title": "REST API",
            "github_url": "https://github.com/a/b",
            "description": "x" * 40,
        },
    ).json()

    # --- the last approval must say so explicitly -------------------------
    outbox.clear()
    client.post(
        f"/api/v1/admin/task-submissions/{submission['id']}/review",
        headers=auth_headers(admin_token),
        json={"status": "approved", "remarks": "Clean implementation."},
    )
    message = only(outbox, "approved")
    assert "Every task is now approved" in message["html"]
    assert "/dashboard/certificate" in message["html"]

    # The certificate is issued in the same request as that final approval —
    # there is no payment step in between — so both emails are already out.
    certificate = only(outbox, "certificate is ready")
    # Certificates carry their own prefix so they are never confused with an
    # offer letter, and the suffix is random rather than sequential.
    assert "KLS-CERT-" in certificate["subject"]
    assert "/verify/KLS-CERT-" in certificate["html"]


def test_admin_invitation_emails_the_invitee(client, db_session, admin_token, outbox):
    outbox.clear()
    response = client.post(
        "/api/v1/admin/admins/invite",
        headers=auth_headers(admin_token),
        json={"full_name": "Priya Sharma", "email": "priya@klsacademy.example.com"},
    )
    assert response.status_code == 201

    message = only(outbox, "invited")
    assert message["to"] == "priya@klsacademy.example.com"
    assert "/accept-invite?token=" in message["html"]
    assert "KLS Admin" in message["html"], "the email should name who invited them"

    # The link is always returned too, so it can be passed on if email is slow
    # or lands in spam.
    assert "/accept-invite?token=" in response.json()["invite_url"]
