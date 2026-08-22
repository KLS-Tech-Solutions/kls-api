"""
Document generation.

ReportLab is pure Python, so these assert real PDF bytes are produced — not
just that a record was written. A student clicking "Download PDF" must get a
PDF on every platform.
"""

import io
from datetime import date

from pypdf import PdfReader
from sqlalchemy import select

from app.core.dates import today_in_ist
from app.services.documents import (
    build_qr_data_uri,
    generate_certificate,
    generate_offer_letter,
)

# Comfortably an adult, and stays that way — the alternative is a literal that
# quietly ages into a test failure.
ADULT_DOB = date(today_in_ist().year - 22, 6, 15).isoformat()


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
            "date_of_birth": ADULT_DOB,
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
            "date_of_birth": ADULT_DOB,
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


# --------------------------------------------------------------------------
# The redesigned documents — the invariants that must not regress
# --------------------------------------------------------------------------

def _render_pair(monkeypatch, **overrides):
    """Renders both documents and returns their extracted text."""
    from datetime import date

    from app.services import documents

    captured: dict[str, bytes] = {}
    monkeypatch.setattr(
        documents, "upload_bytes",
        lambda data, key, content_type: captured.setdefault(key, data) and f"/media/{key}",
    )

    name = overrides.get("student_name", "Ananya Rao")
    domain = overrides.get("domain_title", "Backend Development")

    documents.generate_offer_letter(
        offer_number="KLS-ACAD-2026-00500",
        student_name=name,
        domain_title=domain,
        duration="8 weeks",
        batch_name="Batch 01",
        task_count=4,
        starts_on=overrides.get("starts_on", date(2026, 8, 18)),
    )
    documents.generate_certificate(
        certificate_number="KLS-CERT-2026-00500",
        student_name=name,
        domain_title=domain,
        duration="8 weeks",
    )

    offer = captured["offer-letters/KLS-ACAD-2026-00500.pdf"]
    certificate = captured["certificates/KLS-CERT-2026-00500.pdf"]
    return pdf_text(offer), pdf_text(certificate)


def test_neither_document_carries_a_signature_line(monkeypatch):
    """
    Both are issued electronically. A printed 'Authorised Signatory' on an
    unsigned document is worse than none at all, so it must stay gone.
    """
    offer, certificate = _render_pair(monkeypatch)
    for text in (offer, certificate):
        assert "Signatory" not in text
        assert "Signature" not in text.replace("signature is required", "")


def test_both_documents_explain_that_they_are_electronic(monkeypatch):
    offer, certificate = _render_pair(monkeypatch)
    for text in (offer, certificate):
        assert "electronically generated document" in text
        assert "No physical signature is required" in text
        assert "Verification Cell" in text
        assert "www.klstechsolutions.in" in text


def test_the_fee_amount_appears_on_neither_document(monkeypatch):
    """
    The amount belongs in the terms of service, the refund policy and at
    checkout. Nowhere else, so it can only ever be changed in one place.
    """
    offer, certificate = _render_pair(monkeypatch)
    for text in (offer, certificate):
        for form in ("Rs. 50", "Rs 50", "₹50", "₹ 50", "50 rupees", "INR 50"):
            assert form not in text
        # No currency marker at all, in any amount.
        assert "₹" not in text and "Rs." not in text


def test_the_offer_letter_summarises_the_programme(monkeypatch):
    offer, _ = _render_pair(monkeypatch)
    assert "PROGRAMME AT A GLANCE" in offer
    for label in ("DOMAIN", "BATCH", "DURATION", "TECHNICAL TASKS", "MODE",
                  "COMMENCES"):
        assert label in offer
    assert "18 Aug 2026" in offer


def test_a_batch_with_no_start_date_still_renders(monkeypatch):
    """`starts_on` is optional — an em dash, never a crash or a 'None'."""
    offer, _ = _render_pair(monkeypatch, starts_on=None)
    assert "COMMENCES" in offer
    assert "None" not in offer


def test_long_names_and_domains_do_not_overflow(monkeypatch):
    """
    The recipient name steps down a size and table values are truncated, so a
    45-character name cannot push text through the certificate border.
    """
    name = "Venkatanarasimharajuvaripeta Lakshminarayanan"
    domain = "Artificial Intelligence and Machine Learning Engineering"
    offer, certificate = _render_pair(
        monkeypatch, student_name=name, domain_title=domain
    )
    assert name in certificate
    assert name in offer
    # The narrow cells ellipsise rather than run into their neighbour.
    assert "…" in offer
    assert "…" in certificate


def test_neither_document_mentions_sudhamanagar_or_pvt_ltd(monkeypatch):
    offer, certificate = _render_pair(monkeypatch)
    for text in (offer, certificate):
        assert "Sudhamanagar" not in text
        assert "Pvt" not in text


def test_history_downloads_are_scoped_to_the_caller(client, db_session):
    """
    The per-internship download routes take an enrolment id from the URL.
    Someone else's id must not resolve — and must 404, not 403, so a student
    cannot probe which ids exist.
    """
    from datetime import date, timedelta

    from app.models import Difficulty, Enrollment, InternshipBatch, InternshipDomain
    from tests.conftest import auth_headers

    domain = InternshipDomain(
        slug="d", title="Backend", description="Build services.",
        duration="4 weeks", difficulty=Difficulty.INTERMEDIATE,
    )
    db_session.add(domain)
    db_session.flush()
    batch = InternshipBatch(
        domain_id=domain.id, batch_name="Batch 01",
        start_date=date.today(), end_date=date.today() + timedelta(weeks=4),
    )
    db_session.add(batch)
    db_session.commit()

    def register(email: str) -> str:
        client.post("/api/v1/auth/register", json={
            "full_name": "Student", "email": email,
            "phone": "9845012345", "password": "kls12345",
            "date_of_birth": ADULT_DOB,
        })
        return client.post(
            "/api/v1/auth/login", json={"email": email, "password": "kls12345"}
        ).json()["access_token"]

    owner = register("owner@example.com")
    intruder = register("intruder@example.com")

    client.post(
        "/api/v1/enrollments",
        headers=auth_headers(owner),
        json={"domain_id": str(domain.id), "batch_id": str(batch.id)},
    )
    enrollment_id = str(
        db_session.scalar(select(Enrollment.id).where(Enrollment.batch_id == batch.id))
    )

    mine = client.get(
        f"/api/v1/me/internships/{enrollment_id}/offer-letter/download",
        headers=auth_headers(owner),
    )
    assert mine.status_code == 200
    assert mine.content.startswith(b"%PDF")

    theirs = client.get(
        f"/api/v1/me/internships/{enrollment_id}/offer-letter/download",
        headers=auth_headers(intruder),
    )
    assert theirs.status_code == 404, "one student must not read another's documents"
