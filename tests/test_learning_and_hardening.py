"""
The free-platform pivot, study notes, and the security fixes that shipped with
it.

Each test here corresponds to something that was either newly built or newly
closed, so a regression in any of them is a real one.
"""

import io
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import ratelimit
from app.core.security import hash_password
from app.models import (
    AdminProfile,
    Certificate,
    Difficulty,
    InternshipBatch,
    InternshipDomain,
    LearningChapter,
    OfferLetter,
    Task,
    User,
    UserRole,
    UserStatus,
)
from tests.conftest import auth_headers

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture()
def domain(db_session):
    domain = InternshipDomain(
        slug="backend",
        title="Backend Development",
        description="Build production services.",
        duration="8 weeks",
        difficulty=Difficulty.INTERMEDIATE,
    )
    db_session.add(domain)
    db_session.flush()

    batch = InternshipBatch(
        domain_id=domain.id,
        batch_name="Batch 01",
        start_date=date.today(),
        end_date=date.today() + timedelta(weeks=8),
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        Task(batch_id=batch.id, title="Task 1", description="Build it well.", order_number=1)
    )
    db_session.commit()
    return {"domain": domain, "batch": batch}


@pytest.fixture()
def super_admin(client, db_session):
    admin = User(
        full_name="KLS Admin",
        email="super@klsacademy.example.com",
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
        json={"email": "super@klsacademy.example.com", "password": "admin12345"},
    ).json()["access_token"]


@pytest.fixture()
def student(client):
    client.post("/api/v1/auth/register", json={
        "full_name": "Ananya Rao", "email": "ananya@example.com",
        "phone": "9845012345", "password": "kls12345",
    })
    return client.post(
        "/api/v1/auth/login",
        json={"email": "ananya@example.com", "password": "kls12345"},
    ).json()["access_token"]


# ---------------------------------------------------------------------------
# The platform is free
# ---------------------------------------------------------------------------


def test_there_is_no_payment_surface_left(client, student):
    """The pivot removed payments entirely rather than hiding them."""
    for method, path in [
        ("post", "/api/v1/payments/order"),
        ("post", "/api/v1/payments/verify"),
        ("get", "/api/v1/admin/payments"),
        ("get", "/api/v1/admin/settings"),
    ]:
        response = getattr(client, method)(path, headers=auth_headers(student))
        assert response.status_code == 404, f"{path} still exists"


def test_the_journey_has_no_payment_stage():
    from app.models import JourneyStage
    from app.services.journey import STAGE_ORDER

    values = [s.value for s in STAGE_ORDER]
    assert "payment_pending" not in values
    assert "paid" not in values
    # Finishing the work is the last thing that happens.
    assert values[-2:] == ["all_tasks_approved", "certificate_issued"]
    assert not hasattr(JourneyStage, "PAID")


# ---------------------------------------------------------------------------
# Document numbers
# ---------------------------------------------------------------------------


def test_document_numbers_are_random_not_sequential(client, db_session, domain):
    """
    The old scheme counted rows and added one, which both raced under
    concurrent enrolment and told anyone holding one number what the others
    were called.
    """
    numbers = []
    for index in range(4):
        email = f"student{index}@example.com"
        client.post("/api/v1/auth/register", json={
            "full_name": f"Student {index}", "email": email,
            "phone": "9845012345", "password": "kls12345",
        })
        token = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "kls12345"}
        ).json()["access_token"]
        client.post(
            "/api/v1/enrollments",
            headers=auth_headers(token),
            json={
                "domain_id": str(domain["domain"].id),
                "batch_id": str(domain["batch"].id),
            },
        )

    numbers = [
        n for n in db_session.scalars(select(OfferLetter.offer_letter_number))
    ]
    assert len(numbers) == 4
    assert len(set(numbers)) == 4, "numbers must be unique"

    suffixes = [n.removeprefix("KLS-ACAD-") for n in numbers]
    assert all(len(s) == 10 for s in suffixes)

    # The giveaway of a counter: consecutive integers.
    assert not any(s.isdigit() for s in suffixes), "suffix looks sequential"
    # And no ambiguous characters, so a number read off paper cannot be
    # mistyped into a different valid one.
    assert not set("".join(suffixes)) & set("ILOU")


# ---------------------------------------------------------------------------
# Storage is private
# ---------------------------------------------------------------------------


def test_stored_documents_are_keys_not_public_urls(client, db_session, domain, student):
    """
    Offer letters used to be written to a public bucket under a predictable
    name, so one URL let anyone walk the whole sequence. Nothing is public now
    — what is stored is an opaque key, fetched through an authenticated route.
    """
    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(student),
        json={
            "domain_id": str(domain["domain"].id),
            "batch_id": str(domain["batch"].id),
        },
    )

    letter = db_session.scalar(select(OfferLetter))
    assert letter.pdf_url is not None
    assert not letter.pdf_url.startswith("http"), "a public URL was stored"
    assert not letter.pdf_url.startswith("/media/")
    assert letter.pdf_url.startswith("offer-letters/")

    # It is still downloadable, through the route that checks who is asking.
    response = client.get(
        "/api/v1/me/offer-letter/download", headers=auth_headers(student)
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_media_is_not_mounted_as_a_static_directory():
    from app.main import app

    mounts = [r.path for r in app.routes if r.__class__.__name__ == "Mount"]
    assert "/media" not in mounts


# ---------------------------------------------------------------------------
# Uploads are validated by content
# ---------------------------------------------------------------------------


def test_a_file_claiming_to_be_a_png_is_checked(client):
    from app.services.storage import StorageError, save_chapter_pdf

    with pytest.raises(StorageError):
        save_chapter_pdf(b"<html>not a pdf</html>", __import__("uuid").uuid4(), "x.pdf", "application/pdf")

    # A real PDF is accepted.
    key = save_chapter_pdf(PDF, __import__("uuid").uuid4(), "notes.pdf", "application/pdf")
    assert key.startswith("chapters/")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_login_is_rate_limited(client, student, monkeypatch):
    """
    Enforcement is off under test by default, because the suite signs in far
    more often than any real person. This switches it on to prove the limit
    exists at all.
    """
    monkeypatch.setattr(ratelimit, "ENFORCE_IN_TESTS", True)
    ratelimit.limiter.reset("login:testclient:wrong@example.com")

    codes = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@example.com", "password": "nope12345"},
        ).status_code
        for _ in range(ratelimit.LOGIN.limit + 3)
    ]

    assert 401 in codes, "the first attempts should be ordinary failures"
    assert 429 in codes, "a burst of guesses must eventually be refused"


def test_password_reset_cannot_be_used_to_flood_an_inbox(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "ENFORCE_IN_TESTS", True)
    ratelimit.limiter.reset("forgot:testclient:victim@example.com")

    codes = [
        client.post(
            "/api/v1/auth/forgot-password", json={"email": "victim@example.com"}
        ).status_code
        for _ in range(ratelimit.EMAIL_SEND.limit + 2)
    ]
    assert 429 in codes


def test_security_headers_are_set(client):
    response = client.get("/")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "referrer-policy" in response.headers


# ---------------------------------------------------------------------------
# Learning notes
# ---------------------------------------------------------------------------


def test_an_admin_manages_chapters_and_a_student_reads_them(
    client, db_session, domain, super_admin, student
):
    admin_headers = auth_headers(super_admin)

    created = client.post(
        "/api/v1/admin/chapters",
        headers=admin_headers,
        json={
            "domain_id": str(domain["domain"].id),
            "title": "Chapter 1 — HTTP and REST",
            "summary": "How the web actually talks.",
            "order_number": 1,
            "difficulty": "beginner",
            "estimated_minutes": 30,
        },
    )
    assert created.status_code == 201
    chapter_id = created.json()["id"]

    # Two chapters cannot hold the same position in one domain.
    clash = client.post(
        "/api/v1/admin/chapters",
        headers=admin_headers,
        json={
            "domain_id": str(domain["domain"].id),
            "title": "Another first chapter",
            "order_number": 1,
        },
    )
    assert clash.status_code == 409

    # Upload the notes.
    upload = client.post(
        f"/api/v1/admin/chapters/{chapter_id}/pdf",
        headers=admin_headers,
        files={"file": ("chapter-1.pdf", io.BytesIO(PDF), "application/pdf")},
    )
    assert upload.status_code == 200
    assert upload.json()["pdf_filename"] == "chapter-1.pdf"

    # A student who is not enrolled has no notes to read — there is no domain
    # to draw them from.
    assert client.get("/api/v1/me/chapters", headers=auth_headers(student)).json() == []

    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(student),
        json={
            "domain_id": str(domain["domain"].id),
            "batch_id": str(domain["batch"].id),
        },
    )

    chapters = client.get("/api/v1/me/chapters", headers=auth_headers(student)).json()
    assert len(chapters) == 1
    assert chapters[0]["title"] == "Chapter 1 — HTTP and REST"
    assert chapters[0]["is_read"] is False

    pdf = client.get(
        f"/api/v1/me/chapters/{chapter_id}/download", headers=auth_headers(student)
    )
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    # Marking read is idempotent.
    for _ in range(2):
        assert client.post(
            f"/api/v1/me/chapters/{chapter_id}/read", headers=auth_headers(student)
        ).status_code == 204

    chapters = client.get("/api/v1/me/chapters", headers=auth_headers(student)).json()
    assert chapters[0]["is_read"] is True


def test_notes_do_not_block_task_submission(
    client, db_session, domain, super_admin, student, screenshot_files
):
    """
    The notes are a prompt, not a gate. A student who ignores them entirely
    must still be able to work — anything else produces support requests from
    people who cannot see why they are stuck.
    """
    client.post(
        "/api/v1/admin/chapters",
        headers=auth_headers(super_admin),
        json={
            "domain_id": str(domain["domain"].id),
            "title": "Unread chapter",
            "order_number": 1,
        },
    )
    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(student),
        json={
            "domain_id": str(domain["domain"].id),
            "batch_id": str(domain["batch"].id),
        },
    )
    client.post(
        "/api/v1/linkedin-submissions",
        headers=auth_headers(student),
        json={"linkedin_post_url": "https://www.linkedin.com/posts/ananya_kls-1"},
    )
    queue = client.get(
        "/api/v1/admin/linkedin-submissions?status=pending",
        headers=auth_headers(super_admin),
    ).json()
    client.patch(
        f"/api/v1/admin/linkedin-submissions/{queue[0]['id']}",
        headers=auth_headers(super_admin),
        json={"status": "approved", "remarks": "Verified."},
    )

    task = [
        t for t in client.get("/api/v1/me/tasks", headers=auth_headers(student)).json()
        if t["order_number"] > 0
    ][0]

    response = client.post(
        "/api/v1/task-submissions",
        headers=auth_headers(student),
        data={
            "task_id": task["id"],
            "title": "Built it without reading a thing",
            "github_url": "https://github.com/ananya/repo",
            "description": "A thorough written explanation of the work. " * 4,
        },
        files=screenshot_files,
    )
    assert response.status_code == 201


def test_a_student_cannot_manage_chapters(client, student, domain):
    response = client.post(
        "/api/v1/admin/chapters",
        headers=auth_headers(student),
        json={
            "domain_id": str(domain["domain"].id),
            "title": "Mine now",
            "order_number": 1,
        },
    )
    assert response.status_code == 403


def test_reordering_chapters_survives_a_swap(client, domain, super_admin, db_session):
    """
    `(domain_id, order_number)` is unique, so a naive reorder violates the
    constraint halfway through. The two-pass write is what makes this pass.
    """
    headers = auth_headers(super_admin)
    ids = []
    for position in (1, 2, 3):
        ids.append(
            client.post(
                "/api/v1/admin/chapters",
                headers=headers,
                json={
                    "domain_id": str(domain["domain"].id),
                    "title": f"Chapter {position}",
                    "order_number": position,
                },
            ).json()["id"]
        )

    reversed_ids = list(reversed(ids))
    response = client.post(
        "/api/v1/admin/chapters/reorder",
        headers=headers,
        json={"chapter_ids": reversed_ids},
    )
    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == reversed_ids
    assert [c["order_number"] for c in response.json()] == [1, 2, 3]


def test_the_certificate_is_issued_when_the_last_task_is_approved(
    client, db_session, domain, super_admin, student, screenshot_files
):
    """The whole point of the pivot: finishing the work is the only condition."""
    admin_headers = auth_headers(super_admin)
    headers = auth_headers(student)

    client.post(
        "/api/v1/enrollments", headers=headers,
        json={
            "domain_id": str(domain["domain"].id),
            "batch_id": str(domain["batch"].id),
        },
    )
    client.post(
        "/api/v1/linkedin-submissions", headers=headers,
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

    task = [
        t for t in client.get("/api/v1/me/tasks", headers=headers).json()
        if t["order_number"] > 0
    ][0]
    submission = client.post(
        "/api/v1/task-submissions",
        headers=headers,
        data={
            "task_id": task["id"],
            "title": "REST API foundation",
            "github_url": "https://github.com/ananya/repo",
            "description": "A thorough written explanation of the work. " * 4,
        },
        files=screenshot_files,
    ).json()

    # Not yet — the work has not been reviewed.
    assert db_session.scalar(select(Certificate)) is None

    client.post(
        f"/api/v1/admin/task-submissions/{submission['id']}/review",
        headers=admin_headers,
        json={"status": "approved", "remarks": "Approved."},
    )

    journey = client.get("/api/v1/me/journey", headers=headers).json()
    assert journey["stage"] == "certificate_issued"
    assert journey["certificate"]["certificate_number"].startswith("KLS-CERT-")
    assert journey["history"][0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Who may curate the notes
# ---------------------------------------------------------------------------


@pytest.fixture()
def reviewer(client, db_session):
    """A plain admin — reviews submissions, cannot touch the catalogue."""
    admin = User(
        full_name="Priya Reviewer",
        email="reviewer@klsacademy.example.com",
        phone="+919000000001",
        password_hash=hash_password("admin12345"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db_session.add(admin)
    db_session.flush()
    db_session.add(AdminProfile(user_id=admin.id))
    db_session.commit()
    return client.post(
        "/api/v1/auth/login",
        json={"email": "reviewer@klsacademy.example.com", "password": "admin12345"},
    ).json()["access_token"]


def test_a_plain_admin_can_manage_chapters(client, domain, reviewer):
    """
    Notes are teaching material, not configuration. Whoever reviews a domain's
    submissions is best placed to fix its chapters, and funnelling that through
    one super admin is how material goes stale.
    """
    headers = auth_headers(reviewer)

    created = client.post(
        "/api/v1/admin/chapters",
        headers=headers,
        json={
            "domain_id": str(domain["domain"].id),
            "title": "Chapter 1 — Written by a reviewer",
            "order_number": 1,
        },
    )
    assert created.status_code == 201
    chapter_id = created.json()["id"]

    assert client.post(
        f"/api/v1/admin/chapters/{chapter_id}/pdf",
        headers=headers,
        files={"file": ("notes.pdf", io.BytesIO(PDF), "application/pdf")},
    ).status_code == 200

    assert client.patch(
        f"/api/v1/admin/chapters/{chapter_id}",
        headers=headers,
        json={"title": "Chapter 1 — Revised"},
    ).status_code == 200

    assert client.delete(
        f"/api/v1/admin/chapters/{chapter_id}", headers=headers
    ).status_code == 204


def test_the_catalogue_itself_is_still_super_admin_only(client, domain, reviewer):
    """
    Opening the notes up must not have opened up domains, batches or tasks —
    changing a batch mid-flight moves the goalposts for enrolled students.
    """
    headers = auth_headers(reviewer)

    assert client.post(
        "/api/v1/admin/internship-domains",
        headers=headers,
        json={
            "slug": "sneaky", "title": "Mine now",
            "description": "Should not be allowed.", "duration": "1 week",
            "difficulty": "beginner",
        },
    ).status_code == 403

    assert client.post(
        "/api/v1/admin/tasks",
        headers=headers,
        json={
            "batch_id": str(domain["batch"].id), "title": "Sneaky task",
            "description": "Should not be allowed.", "order_number": 9,
        },
    ).status_code == 403


def test_a_chapter_records_who_last_edited_it(client, domain, super_admin, reviewer):
    """`updated_by` is the point of the audit column — it must actually move."""
    created = client.post(
        "/api/v1/admin/chapters",
        headers=auth_headers(super_admin),
        json={
            "domain_id": str(domain["domain"].id),
            "title": "Chapter 1",
            "order_number": 1,
        },
    ).json()

    listed = client.get(
        "/api/v1/admin/chapters", headers=auth_headers(super_admin)
    ).json()
    assert listed[0]["updated_by_name"] == "KLS Admin"

    # A different admin edits it — the attribution follows.
    client.patch(
        f"/api/v1/admin/chapters/{created['id']}",
        headers=auth_headers(reviewer),
        json={"summary": "Clarified the section on status codes."},
    )

    listed = client.get(
        "/api/v1/admin/chapters", headers=auth_headers(reviewer)
    ).json()
    assert listed[0]["updated_by_name"] == "Priya Reviewer"


def test_students_still_cannot_manage_chapters(client, domain, student):
    assert client.post(
        "/api/v1/admin/chapters",
        headers=auth_headers(student),
        json={
            "domain_id": str(domain["domain"].id),
            "title": "Mine now",
            "order_number": 1,
        },
    ).status_code == 403
