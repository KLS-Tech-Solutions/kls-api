"""
A student may take more than one internship.

This is the change most likely to break quietly. Every journey query used to
read by `student_id` alone, which was correct while a student could only hold
one enrolment — the moment they can hold two, a student-wide certificate
lookup makes a brand new internship report `certificate_issued` on day one.
These tests pin the scoping down.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    Certificate,
    Difficulty,
    Enrollment,
    EnrollmentStatus,
    InternshipBatch,
    InternshipDomain,
    Task,
)
from tests.conftest import auth_headers
from tests.test_journey import STUDENT, admin_token, student_token  # noqa: F401


def make_domain(db, slug: str, title: str, tasks: int = 1):
    domain = InternshipDomain(
        slug=slug,
        title=title,
        description="Build and ship something real.",
        duration="4 weeks",
        difficulty=Difficulty.INTERMEDIATE,
    )
    db.add(domain)
    db.flush()

    batch = InternshipBatch(
        domain_id=domain.id,
        batch_name=f"{title} — Batch 01",
        start_date=date.today(),
        end_date=date.today() + timedelta(weeks=4),
    )
    db.add(batch)
    db.flush()

    db.add(
        Task(
            batch_id=batch.id,
            title="Share your offer letter on LinkedIn",
            description="Post it and submit the URL.",
            order_number=0,
        )
    )
    for index in range(1, tasks + 1):
        db.add(
            Task(
                batch_id=batch.id,
                title=f"Task {index}",
                description="Build the thing and document it thoroughly.",
                order_number=index,
            )
        )
    db.commit()
    return domain, batch


@pytest.fixture()
def two_domains(db_session):
    first = make_domain(db_session, "backend", "Backend Development")
    second = make_domain(db_session, "frontend", "Frontend Development")
    return {"first": first, "second": second}


def stage_of(client, token) -> str:
    return client.get("/api/v1/me/journey", headers=auth_headers(token)).json()["stage"]


def complete(client, db_session, token, admin, batch, screenshot_files):
    """Drives one internship from enrolment to certificate."""
    headers = auth_headers(token)
    admin_headers = auth_headers(admin)

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
        response = client.post(
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
            f"/api/v1/admin/task-submissions/{response.json()['id']}/review",
            headers=admin_headers,
            json={"status": "approved", "remarks": "Approved."},
        )

    order = client.post("/api/v1/payments/order", headers=headers).json()
    client.post(
        "/api/v1/payments/verify",
        headers=headers,
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "sig_test",
        },
    )


def test_a_second_internship_starts_from_scratch(
    client, db_session, two_domains, student_token, admin_token, screenshot_files
):
    headers = auth_headers(student_token)
    first_domain, first_batch = two_domains["first"]
    second_domain, second_batch = two_domains["second"]

    client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(first_domain.id), "batch_id": str(first_batch.id)},
    )
    complete(client, db_session, student_token, admin_token, first_batch, screenshot_files)
    assert stage_of(client, student_token) == "certificate_issued"

    journey = client.get("/api/v1/me/journey", headers=headers).json()
    assert journey["can_enroll_again"] is True
    first_certificate = journey["certificate"]["certificate_number"]

    # The second enrolment must not inherit anything from the first.
    response = client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(second_domain.id), "batch_id": str(second_batch.id)},
    )
    assert response.status_code == 201

    journey = client.get("/api/v1/me/journey", headers=headers).json()
    assert journey["stage"] == "offer_letter_generated", (
        "a fresh internship must not report the previous one's certificate"
    )
    assert journey["certificate"] is None
    assert journey["payment"] is None
    assert journey["linkedinSubmission"] is None
    assert journey["submissions"] == []
    assert journey["domain"]["title"] == "Frontend Development"
    assert journey["can_enroll_again"] is False

    # …and the first certificate is still there, in history.
    history = journey["history"]
    assert len(history) == 2
    assert history[0]["is_current"] is True
    assert history[0]["domain_title"] == "Frontend Development"
    assert history[1]["certificate_number"] == first_certificate
    assert history[1]["offer_letter_url"]
    assert history[1]["status"] == "completed"


def test_a_second_internship_is_refused_until_the_first_is_certificated(
    client, db_session, two_domains, student_token
):
    headers = auth_headers(student_token)
    first_domain, first_batch = two_domains["first"]
    second_domain, second_batch = two_domains["second"]

    client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(first_domain.id), "batch_id": str(first_batch.id)},
    )

    response = client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(second_domain.id), "batch_id": str(second_batch.id)},
    )
    assert response.status_code == 409
    assert "Finish your current internship" in response.json()["detail"]

    journey = client.get("/api/v1/me/journey", headers=headers).json()
    assert journey["can_enroll_again"] is False


def test_the_same_internship_cannot_be_taken_twice(
    client, db_session, two_domains, student_token, admin_token, screenshot_files
):
    """
    Submissions are keyed by task, so re-enrolling in a batch already taken
    would let the old approvals count towards the new internship.
    """
    headers = auth_headers(student_token)
    domain, batch = two_domains["first"]

    client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(domain.id), "batch_id": str(batch.id)},
    )
    complete(client, db_session, student_token, admin_token, batch, screenshot_files)

    response = client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(domain.id), "batch_id": str(batch.id)},
    )
    assert response.status_code == 409
    assert "already taken" in response.json()["detail"]


def test_each_internship_gets_its_own_certificate(
    client, db_session, two_domains, student_token, admin_token, screenshot_files
):
    headers = auth_headers(student_token)
    first_domain, first_batch = two_domains["first"]
    second_domain, second_batch = two_domains["second"]

    client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(first_domain.id), "batch_id": str(first_batch.id)},
    )
    complete(client, db_session, student_token, admin_token, first_batch, screenshot_files)

    client.post(
        "/api/v1/enrollments",
        headers=headers,
        json={"domain_id": str(second_domain.id), "batch_id": str(second_batch.id)},
    )
    complete(client, db_session, student_token, admin_token, second_batch, screenshot_files)

    certificates = list(db_session.scalars(select(Certificate)))
    assert len(certificates) == 2, "the second internship must issue its own certificate"
    assert len({c.certificate_number for c in certificates}) == 2
    assert len({c.enrollment_id for c in certificates}) == 2

    # Both remain publicly verifiable, for good.
    for certificate in certificates:
        response = client.get(
            f"/api/v1/certificates/verify/{certificate.certificate_number}"
        )
        assert response.status_code == 200
        assert response.json()["student_name"] == STUDENT["full_name"]

    enrollments = list(db_session.scalars(select(Enrollment)))
    assert len(enrollments) == 2
    assert all(e.status == EnrollmentStatus.COMPLETED for e in enrollments)
