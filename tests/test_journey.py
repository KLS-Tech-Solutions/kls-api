"""
Walks a student through the entire internship and asserts the stage after each
step. This is the contract both frontends depend on — if any assertion here
breaks, a dashboard somewhere shows the wrong thing as locked.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import (
    AdminProfile,
    Difficulty,
    InternshipBatch,
    InternshipDomain,
    Task,
    User,
    UserRole,
    UserStatus,
)
from tests.conftest import auth_headers

STUDENT = {
    "full_name": "Ananya Rao",
    "email": "ananya@example.com",
    "phone": "9845012345",
    "password": "kls12345",
}


@pytest.fixture()
def catalogue(db_session):
    domain = InternshipDomain(
        slug="full-stack-python",
        title="Full Stack Python Development",
        description="Build and ship a complete web application.",
        duration="4 weeks",
        difficulty=Difficulty.INTERMEDIATE,
        icon="code",
        skills=["Python"],
        outcomes=["Ship an app"],
    )
    db_session.add(domain)
    db_session.flush()

    batch = InternshipBatch(
        domain_id=domain.id,
        batch_name="Full Stack Python — Batch 01",
        start_date=date.today(),
        end_date=date.today() + timedelta(weeks=4),
        seats_total=50,
    )
    db_session.add(batch)
    db_session.flush()

    db_session.add(
        Task(
            batch_id=batch.id,
            title="Share your offer letter on LinkedIn",
            description="Post it and submit the URL.",
            order_number=0,
            requirements=["Public post"],
        )
    )
    # Two technical tasks — deliberately not the same count as other domains.
    for index in range(1, 3):
        db_session.add(
            Task(
                batch_id=batch.id,
                title=f"Task {index}",
                description="Build the thing and document it thoroughly.",
                order_number=index,
                requirements=["Public repo", "3 screenshots"],
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
        "/api/v1/auth/login", json={"email": "admin@klsacademy.example.com", "password": "admin12345"}
    ).json()["access_token"]


@pytest.fixture()
def student_token(client):
    client.post("/api/v1/auth/register", json=STUDENT)
    return client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    ).json()["access_token"]


def stage_of(client, token) -> str:
    return client.get("/api/v1/me/journey", headers=auth_headers(token)).json()["stage"]


def test_full_journey(client, db_session, catalogue, student_token, admin_token, screenshot_files):
    student_headers = auth_headers(student_token)
    admin_headers = auth_headers(admin_token)

    # 1 — a fresh account is not enrolled -----------------------------------
    assert stage_of(client, student_token) == "not_enrolled"

    # 2 — enrolling also generates the offer letter -------------------------
    response = client.post(
        "/api/v1/enrollments",
        headers=student_headers,
        json={
            "domain_id": str(catalogue["domain"].id),
            "batch_id": str(catalogue["batch"].id),
        },
    )
    assert response.status_code == 201
    assert stage_of(client, student_token) == "offer_letter_generated"

    journey = client.get("/api/v1/me/journey", headers=student_headers).json()
    assert journey["offerLetter"]["offer_letter_number"].startswith("KLS-ACAD-")

    # A student holds one internship at a time.
    assert (
        client.post(
            "/api/v1/enrollments",
            headers=student_headers,
            json={
                "domain_id": str(catalogue["domain"].id),
                "batch_id": str(catalogue["batch"].id),
            },
        ).status_code
        == 409
    )

    # 3 — technical tasks are locked until LinkedIn is verified -------------
    tasks = client.get("/api/v1/me/tasks", headers=student_headers).json()
    technical = sorted(
        [t for t in tasks if t["order_number"] > 0], key=lambda t: t["order_number"]
    )

    blocked = client.post(
        "/api/v1/task-submissions",
        headers=student_headers,
        data={
            "task_id": technical[0]["id"],
            "title": "Premature submission",
            "github_url": "https://github.com/ananya/repo",
            "description": "x" * 130,
        },
        files=screenshot_files,
    )
    assert blocked.status_code == 403

    # 4 — submit the LinkedIn post ------------------------------------------
    response = client.post(
        "/api/v1/linkedin-submissions",
        headers=student_headers,
        json={"linkedin_post_url": "https://www.linkedin.com/posts/ananya_kls-activity-1"},
    )
    assert response.status_code == 201
    assert stage_of(client, student_token) == "linkedin_submitted"

    # 5 — an admin approves it ----------------------------------------------
    queue = client.get(
        "/api/v1/admin/linkedin-submissions?status=pending", headers=admin_headers
    ).json()
    assert len(queue) == 1

    response = client.patch(
        f"/api/v1/admin/linkedin-submissions/{queue[0]['id']}",
        headers=admin_headers,
        json={"status": "approved", "remarks": "Verified."},
    )
    assert response.status_code == 200
    assert stage_of(client, student_token) == "linkedin_approved"

    # 6 — tasks are sequential: nothing can be skipped -----------------------
    out_of_order = client.post(
        "/api/v1/task-submissions",
        headers=student_headers,
        data={
            "task_id": technical[1]["id"],
            "title": "Skipping ahead",
            "github_url": "https://github.com/ananya/repo",
            "description": "x" * 130,
        },
        files=screenshot_files,
    )
    assert out_of_order.status_code == 403

    # 7 — submit task 1 ------------------------------------------------------
    response = client.post(
        "/api/v1/task-submissions",
        headers=student_headers,
        data={
            "task_id": technical[0]["id"],
            "title": "REST API foundation",
            "github_url": "https://github.com/ananya/kls-task-1",
            "description": "I built a FastAPI service with JWT auth. " * 5,
        },
        files=screenshot_files,
    )
    assert response.status_code == 201
    submission_id = response.json()["id"]
    assert len(response.json()["screenshots"]) == 3
    assert stage_of(client, student_token) == "tasks_in_progress"

    # 8 — reject, then resubmit ---------------------------------------------
    response = client.post(
        f"/api/v1/admin/task-submissions/{submission_id}/review",
        headers=admin_headers,
        json={"status": "rejected", "remarks": "Repository is private. Make it public."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["review"]["remarks"].startswith("Repository is private")

    response = client.post(
        "/api/v1/task-submissions",
        headers=student_headers,
        data={
            "task_id": technical[0]["id"],
            "title": "REST API foundation",
            "github_url": "https://github.com/ananya/kls-task-1",
            "description": "Now public, with the responsive screenshot added. " * 4,
        },
        files=screenshot_files,
    )
    assert response.status_code == 201
    assert response.json()["attempt"] == 2

    client.post(
        f"/api/v1/admin/task-submissions/{submission_id}/review",
        headers=admin_headers,
        json={"status": "approved", "remarks": "Approved."},
    )

    # 9 — final task, then everything is approved ---------------------------
    response = client.post(
        "/api/v1/task-submissions",
        headers=student_headers,
        data={
            "task_id": technical[1]["id"],
            "title": "React front end",
            "github_url": "https://github.com/ananya/kls-task-2",
            "description": "Responsive React interface consuming the API. " * 4,
        },
        files=screenshot_files,
    )
    assert response.status_code == 201
    second_id = response.json()["id"]

    client.post(
        f"/api/v1/admin/task-submissions/{second_id}/review",
        headers=admin_headers,
        json={"status": "approved", "remarks": "Approved."},
    )

    # 10 — approving the last task completes the internship ---------------
    # There is no payment step: the platform is free, so the reviewer's click
    # on the final task is what issues the certificate.
    assert stage_of(client, student_token) == "certificate_issued"

    journey = client.get("/api/v1/me/journey", headers=student_headers).json()
    assert journey["certificate"]["certificate_number"].startswith("KLS-CERT-")
    assert journey["can_enroll_again"] is True

    certificate = client.get("/api/v1/me/certificate", headers=student_headers).json()
    assert certificate["certificate_number"].startswith("KLS-CERT-")
    assert certificate["student_name"] == "Ananya Rao"

    # 11 — the student got told at every step -------------------------------
    notifications = client.get("/api/v1/me/notifications", headers=student_headers).json()
    titles = {n["title"] for n in notifications}
    assert "Welcome to KLS Academy" in titles
    assert "Offer letter generated" in titles
    assert "LinkedIn task approved" in titles
    assert "Certificate issued" in titles


def test_student_cannot_reach_admin_routes(client, student_token):
    response = client.get(
        "/api/v1/admin/task-submissions", headers=auth_headers(student_token)
    )
    assert response.status_code == 403


def test_admin_sees_student_journey_in_the_same_shape(
    client, catalogue, student_token, admin_token
):
    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(student_token),
        json={
            "domain_id": str(catalogue["domain"].id),
            "batch_id": str(catalogue["batch"].id),
        },
    )

    students = client.get("/api/v1/admin/students", headers=auth_headers(admin_token)).json()
    assert len(students) == 1
    assert students[0]["stage"] == "offer_letter_generated"

    journey = client.get(
        f"/api/v1/admin/students/{students[0]['id']}", headers=auth_headers(admin_token)
    ).json()
    assert set(journey) >= {
        "stage", "user", "domain", "batch", "enrollment", "offerLetter",
        "tasks", "submissions", "certificate", "notifications",
    }
