from datetime import date, timedelta

from app.models import Certificate, CertificateStatus, Difficulty, InternshipDomain, User, UserRole
from app.core.security import hash_password


def test_domain_listing_and_detail(client, db_session):
    db_session.add(
        InternshipDomain(
            slug="cyber-security",
            title="Cyber Security",
            description="Practical security engineering.",
            duration="4 weeks",
            difficulty=Difficulty.ADVANCED,
            icon="shield",
        )
    )
    db_session.commit()

    listing = client.get("/api/v1/internship-domains")
    assert listing.status_code == 200
    assert listing.json()[0]["slug"] == "cyber-security"

    detail = client.get("/api/v1/internship-domains/cyber-security")
    assert detail.status_code == 200

    assert client.get("/api/v1/internship-domains/nope").status_code == 404


def test_certificate_verification(client, db_session):
    student = User(
        full_name="Rohit Menon",
        email="rohit@example.com",
        phone="+919845012345",
        password_hash=hash_password("kls12345"),
        role=UserRole.STUDENT,
    )
    db_session.add(student)
    db_session.flush()

    db_session.add(
        Certificate(
            student_id=student.id,
            certificate_number="KLS-ACAD-2026-00185",
            status=CertificateStatus.ISSUED,
        )
    )
    db_session.commit()

    found = client.get("/api/v1/certificates/verify/KLS-ACAD-2026-00185")
    assert found.status_code == 200
    assert found.json()["student_name"] == "Rohit Menon"

    # Case-insensitive, and unknown numbers are a normal 404.
    assert client.get("/api/v1/certificates/verify/kls-acad-2026-00185").status_code == 200
    assert client.get("/api/v1/certificates/verify/KLS-ACAD-2026-99999").status_code == 404


def test_revoked_certificate_does_not_verify(client, db_session):
    student = User(
        full_name="Test Student",
        email="revoked@example.com",
        phone="+919845012345",
        password_hash=hash_password("kls12345"),
        role=UserRole.STUDENT,
    )
    db_session.add(student)
    db_session.flush()
    db_session.add(
        Certificate(
            student_id=student.id,
            certificate_number="KLS-ACAD-2026-00999",
            status=CertificateStatus.REVOKED,
        )
    )
    db_session.commit()

    assert client.get("/api/v1/certificates/verify/KLS-ACAD-2026-00999").status_code == 404
