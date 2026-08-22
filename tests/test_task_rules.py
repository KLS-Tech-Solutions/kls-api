"""
Per-task submission rules.

These are configured by a super admin and enforced by the API — the frontend
copy of each rule is a convenience, this is what actually holds.
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
def ready_student(client, db_session):
    """A student whose LinkedIn task is approved, so tasks are unlocked."""
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
        Task(
            batch_id=batch.id,
            title="Share on LinkedIn",
            description="Post it.",
            order_number=0,
        )
    )
    db_session.commit()

    client.post("/api/v1/auth/register", json=STUDENT)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT["email"], "password": STUDENT["password"]},
    ).json()["access_token"]

    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(token),
        json={"domain_id": str(domain.id), "batch_id": str(batch.id)},
    )

    # Approve the LinkedIn gate directly — this test is about task rules.
    offer = db_session.query(OfferLetter).first()
    db_session.add(
        LinkedInSubmission(
            student_id=offer.student_id,
            offer_letter_id=offer.id,
            linkedin_post_url="https://www.linkedin.com/posts/x_y-activity-1",
            status=ReviewStatus.APPROVED,
        )
    )
    db_session.commit()

    return {"token": token, "batch": batch, "db": db_session}


def add_task(db, batch, **config):
    task = Task(
        batch_id=batch.id,
        title="Task 1",
        description="Build the thing properly.",
        order_number=1,
        **config,
    )
    db.add(task)
    db.commit()
    return task


def submit(client, token, task, screenshots, **fields):
    data = {
        "task_id": str(task.id),
        "title": fields.get("title", "My submission"),
        "github_url": fields.get("github_url", "https://github.com/a/b"),
        "description": fields.get("description", "x" * 200),
    }
    if "live_demo_url" in fields:
        data["live_demo_url"] = fields["live_demo_url"]

    return client.post(
        "/api/v1/task-submissions",
        headers=auth_headers(token),
        data=data,
        files=screenshots,
    )


def test_screenshot_minimum_is_per_task(client, ready_student, screenshot_files):
    task = add_task(ready_student["db"], ready_student["batch"], min_screenshots=1)

    # One screenshot is enough for this task, even though the default is three.
    response = submit(client, ready_student["token"], task, screenshot_files[:1])
    assert response.status_code == 201


def test_screenshot_maximum_is_enforced(client, ready_student, screenshot_files):
    task = add_task(
        ready_student["db"], ready_student["batch"], min_screenshots=1, max_screenshots=2
    )

    response = submit(client, ready_student["token"], task, screenshot_files)
    assert response.status_code == 422
    assert "screenshots" in str(response.json()["detail"])


def test_github_can_be_made_optional(client, ready_student, screenshot_files):
    task = add_task(ready_student["db"], ready_student["batch"], require_github=False)

    response = submit(client, ready_student["token"], task, screenshot_files, github_url="")
    assert response.status_code == 201


def test_github_required_by_default(client, ready_student, screenshot_files):
    task = add_task(ready_student["db"], ready_student["batch"])

    response = submit(client, ready_student["token"], task, screenshot_files, github_url="")
    assert response.status_code == 422
    assert "github_url" in str(response.json()["detail"])


def test_explanation_length_is_configurable(client, ready_student, screenshot_files):
    task = add_task(
        ready_student["db"], ready_student["batch"], min_explanation_chars=500
    )

    short = submit(client, ready_student["token"], task, screenshot_files, description="x" * 200)
    assert short.status_code == 422
    assert "description" in str(short.json()["detail"])


def test_live_demo_can_be_required(client, ready_student, screenshot_files):
    task = add_task(ready_student["db"], ready_student["batch"], require_live_demo=True)

    missing = submit(client, ready_student["token"], task, screenshot_files)
    assert missing.status_code == 422
    assert "live_demo_url" in str(missing.json()["detail"])

    provided = submit(
        client,
        ready_student["token"],
        task,
        screenshot_files,
        live_demo_url="https://demo.example.com",
    )
    assert provided.status_code == 201


def test_disabled_task_refuses_submission(client, ready_student, screenshot_files):
    task = add_task(ready_student["db"], ready_student["batch"], is_active=False)

    response = submit(client, ready_student["token"], task, screenshot_files)
    assert response.status_code == 403


def test_disabled_task_is_hidden_from_the_student(client, ready_student):
    add_task(ready_student["db"], ready_student["batch"], is_active=False)

    tasks = client.get(
        "/api/v1/me/tasks", headers=auth_headers(ready_student["token"])
    ).json()
    assert all(t["order_number"] == 0 for t in tasks)


def test_disabled_task_does_not_block_completion(client, ready_student, screenshot_files):
    """A parked task must not strand a student who finished everything else."""
    db, batch = ready_student["db"], ready_student["batch"]
    live = add_task(db, batch, min_screenshots=1)

    disabled = Task(
        batch_id=batch.id,
        title="Task 2",
        description="Parked for now.",
        order_number=2,
        is_active=False,
    )
    db.add(disabled)
    db.commit()

    submission = submit(client, ready_student["token"], live, screenshot_files[:1])
    assert submission.status_code == 201

    # Approve it as an admin, and the internship completes.
    admin = User(
        full_name="Admin",
        email="admin@klsacademy.example.com",
        phone="+919000000000",
        password_hash=hash_password("admin12345"),
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db.add(admin)
    db.flush()
    db.add(AdminProfile(user_id=admin.id))
    db.commit()

    admin_token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@klsacademy.example.com", "password": "admin12345"},
    ).json()["access_token"]

    client.post(
        f"/api/v1/admin/task-submissions/{submission.json()['id']}/review",
        headers=auth_headers(admin_token),
        json={"status": "approved", "remarks": "Good."},
    )

    journey = client.get(
        "/api/v1/me/journey", headers=auth_headers(ready_student["token"])
    ).json()
    assert journey["stage"] == "certificate_issued"


def test_next_task_unlocks_on_submission_not_approval(
    client, ready_student, screenshot_files
):
    """
    A student who has submitted task 1 can start task 2 straight away.

    Review latency must never be the thing that slows an internship down —
    approval still gates the certificate, but not the next piece of work.
    """
    db, batch = ready_student["db"], ready_student["batch"]
    first = add_task(db, batch, min_screenshots=1)

    second = Task(
        batch_id=batch.id,
        title="Task 2",
        description="Build the second thing.",
        order_number=2,
        min_screenshots=1,
    )
    db.add(second)
    db.commit()

    # Task 2 is locked before task 1 is submitted.
    blocked = submit(client, ready_student["token"], second, screenshot_files[:1])
    assert blocked.status_code == 403
    assert "previous task" in blocked.json()["detail"].lower()

    # Submit task 1 — deliberately leave it unreviewed.
    submission = submit(client, ready_student["token"], first, screenshot_files[:1])
    assert submission.status_code == 201
    assert submission.json()["status"] == "under_review"

    # Task 2 is now open, with no reviewer involved.
    allowed = submit(client, ready_student["token"], second, screenshot_files[:1])
    assert allowed.status_code == 201


def test_a_rejected_task_still_unlocks_the_next_one(
    client, ready_student, screenshot_files, db_session
):
    """
    Being sent back on task 1 should not also block task 2 — the student can
    keep moving while they revise.
    """
    from app.models import AdminProfile, User, UserRole, UserStatus

    db, batch = ready_student["db"], ready_student["batch"]
    first = add_task(db, batch, min_screenshots=1)
    second = Task(
        batch_id=batch.id,
        title="Task 2",
        description="Build the second thing.",
        order_number=2,
        min_screenshots=1,
    )
    db.add(second)
    db.commit()

    submission = submit(client, ready_student["token"], first, screenshot_files[:1])

    admin = User(
        full_name="Admin",
        email="rejector@klsacademy.example.com",
        phone="+919000000000",
        password_hash=hash_password("admin12345"),
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db.add(admin)
    db.flush()
    db.add(AdminProfile(user_id=admin.id))
    db.commit()

    admin_token = client.post(
        "/api/v1/auth/login",
        json={"email": "rejector@klsacademy.example.com", "password": "admin12345"},
    ).json()["access_token"]

    client.post(
        f"/api/v1/admin/task-submissions/{submission.json()['id']}/review",
        headers=auth_headers(admin_token),
        json={"status": "rejected", "remarks": "Repository is private."},
    )

    allowed = submit(client, ready_student["token"], second, screenshot_files[:1])
    assert allowed.status_code == 201


def test_certificate_still_requires_every_task_approved(
    client, ready_student, screenshot_files
):
    """Submitting is enough to progress, but not enough to finish."""
    db, batch = ready_student["db"], ready_student["batch"]
    first = add_task(db, batch, min_screenshots=1)
    second = Task(
        batch_id=batch.id,
        title="Task 2",
        description="Build the second thing.",
        order_number=2,
        min_screenshots=1,
    )
    db.add(second)
    db.commit()

    submit(client, ready_student["token"], first, screenshot_files[:1])
    submit(client, ready_student["token"], second, screenshot_files[:1])

    journey = client.get(
        "/api/v1/me/journey", headers=auth_headers(ready_student["token"])
    ).json()
    assert journey["stage"] == "tasks_in_progress"

    # Payment is still shut until a reviewer has signed both off.
    # The certificate is withheld while any task is still unapproved.
    journey = client.get(
        "/api/v1/me/journey", headers=auth_headers(ready_student["token"])
    ).json()
    assert journey["certificate"] is None
    assert journey["stage"] != "certificate_issued"
