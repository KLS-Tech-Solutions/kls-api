"""
Document generation.

ReportLab is pure Python, so these assert real PDF bytes are produced — not
just that a record was written. A student clicking "Download PDF" must get a
PDF on every platform.
"""

import io

from pypdf import PdfReader

from app.services.documents import (
    build_qr_data_uri,
    generate_certificate,
    generate_offer_letter,
)


def pdf_text(data: bytes) -> str:
    """ReportLab compresses content streams, so the text must be extracted."""
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def test_offer_letter_renders_and_stores():
    url = generate_offer_letter(
        offer_number="KLS/ACAD/2026/00001",
        student_name="Ananya Rao",
        domain_title="Full Stack Python Development",
        duration="4 weeks",
        batch_name="Batch 01",
        task_count=3,
    )
    assert url.endswith("offer-letters/KLS-ACAD-2026-00001.pdf")


def test_offer_letter_produces_a_real_pdf(monkeypatch):
    from app.services import documents

    captured: dict[str, bytes] = {}

    def fake_upload(data: bytes, key: str, content_type: str) -> str:
        captured[key] = data
        return f"/media/{key}"

    monkeypatch.setattr(documents, "upload_bytes", fake_upload)

    documents.generate_offer_letter(
        offer_number="KLS/ACAD/2026/00002",
        student_name="Rohit Menon",
        domain_title="Cyber Security",
        duration="4 weeks",
        batch_name="Batch 01",
        task_count=4,
    )

    pdf = next(iter(captured.values()))
    assert pdf.startswith(b"%PDF"), "must be a real PDF, not HTML"
    assert len(pdf) > 10_000, "a PDF this small has no branding in it"

    text = pdf_text(pdf)
    assert "Rohit Menon" in text
    assert "Cyber Security" in text
    assert "MSME registered" in text
    # The hard naming rule for this project.
    assert "Pvt. Ltd" not in text and "Pvt Ltd" not in text


def test_certificate_produces_a_real_pdf_and_a_qr(monkeypatch):
    from app.services import documents

    captured: dict[str, bytes] = {}

    def fake_upload(data: bytes, key: str, content_type: str) -> str:
        captured[key] = data
        return f"/media/{key}"

    monkeypatch.setattr(documents, "upload_bytes", fake_upload)

    certificate_url, qr_url = documents.generate_certificate(
        certificate_number="KLS-ACAD-2026-00184",
        student_name="Ananya Rao",
        domain_title="Full Stack Python Development",
        duration="4 weeks",
    )

    assert certificate_url.endswith(".pdf")
    assert qr_url.endswith("-qr.png")

    pdf = captured["certificates/KLS-ACAD-2026-00184.pdf"]
    assert pdf.startswith(b"%PDF")

    text = pdf_text(pdf)
    assert "KLS-ACAD-2026-00184" in text
    assert "/verify/KLS-ACAD-2026-00184" in text

    assert captured["certificates/KLS-ACAD-2026-00184-qr.png"].startswith(b"\x89PNG")


def test_qr_encodes_the_url():
    uri = build_qr_data_uri("https://academy.klstechsolutions.in/verify/KLS-ACAD-2026-00184")
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > 200


def test_student_can_download_the_offer_letter(client, db_session):
    """The whole path: enrol → GET the download route → receive PDF bytes."""
    from datetime import date, timedelta

    from app.models import Difficulty, InternshipBatch, InternshipDomain, Task
    from tests.conftest import auth_headers

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
        Task(batch_id=batch.id, title="Task 1", description="Build it.", order_number=1)
    )
    db_session.commit()

    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ananya Rao",
            "email": "ananya@example.com",
            "phone": "9845012345",
            "password": "kls12345",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "ananya@example.com", "password": "kls12345"},
    ).json()["access_token"]

    # No enrolment yet — nothing to download.
    assert (
        client.get("/api/v1/me/offer-letter/download", headers=auth_headers(token)).status_code
        == 404
    )

    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(token),
        json={"domain_id": str(domain.id), "batch_id": str(batch.id)},
    )

    response = client.get("/api/v1/me/offer-letter/download", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

    text = pdf_text(response.content)
    assert "Ananya Rao" in text
    assert "Full Stack Python" in text


def test_offer_letter_regenerates_when_the_file_is_missing(client, db_session, tmp_path):
    """
    Deleting the stored file must not break the download — the database record
    is the source of truth and the PDF is a rendering of it.
    """
    from datetime import date, timedelta
    from pathlib import Path

    from app.models import Difficulty, InternshipBatch, InternshipDomain, OfferLetter
    from tests.conftest import auth_headers

    domain = InternshipDomain(
        slug="d",
        title="Cyber Security",
        description="Practical security engineering.",
        duration="4 weeks",
        difficulty=Difficulty.ADVANCED,
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
    db_session.commit()

    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Rohit Menon",
            "email": "rohit@example.com",
            "phone": "9845012345",
            "password": "kls12345",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "rohit@example.com", "password": "kls12345"},
    ).json()["access_token"]
    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(token),
        json={"domain_id": str(domain.id), "batch_id": str(batch.id)},
    )

    letter = db_session.query(OfferLetter).first()
    stored = Path("media") / letter.pdf_url.removeprefix("/media/")
    if stored.exists():
        stored.unlink()

    response = client.get("/api/v1/me/offer-letter/download", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
