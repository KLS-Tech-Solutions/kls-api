"""
Document generation.

WeasyPrint is absent in CI, so these assert the *records and content* are
right — the code deliberately falls back to storing HTML when the renderer is
missing, because a paid student must always end up with a certificate record.
"""

from app.services.documents import (
    build_qr_data_uri,
    generate_certificate,
    generate_offer_letter,
)


def test_offer_letter_renders_and_stores():
    url = generate_offer_letter(
        offer_number="KLS/ACAD/2026/00001",
        student_name="Ananya Rao",
        domain_title="Full Stack Python Development",
        duration="4 weeks",
        batch_name="Batch 01",
        task_count=3,
    )
    assert "offer-letters/KLS-ACAD-2026-00001" in url


def test_offer_letter_names_the_organisation_correctly(tmp_path, monkeypatch):
    from app.services import documents

    captured: dict[str, bytes] = {}

    def fake_upload(data: bytes, key: str, content_type: str) -> str:
        captured["data"] = data
        return f"/media/{key}"

    monkeypatch.setattr(documents, "upload_bytes", fake_upload)
    monkeypatch.setattr(documents, "_render_pdf", lambda html: None)

    documents.generate_offer_letter(
        offer_number="KLS/ACAD/2026/00002",
        student_name="Rohit Menon",
        domain_title="Cyber Security",
        duration="4 weeks",
        batch_name="Batch 01",
        task_count=4,
    )

    html = captured["data"].decode()
    assert "Rohit Menon" in html
    assert "Cyber Security" in html
    assert "MSME registered" in html
    # The hard naming rule for this project.
    assert "Pvt. Ltd" not in html
    assert "Pvt Ltd" not in html


def test_certificate_embeds_a_qr_pointing_at_the_verification_page(monkeypatch):
    from app.services import documents

    captured: dict[str, bytes] = {}

    def fake_upload(data: bytes, key: str, content_type: str) -> str:
        captured[key] = data
        return f"/media/{key}"

    monkeypatch.setattr(documents, "upload_bytes", fake_upload)
    monkeypatch.setattr(documents, "_render_pdf", lambda html: None)

    certificate_url, qr_url = documents.generate_certificate(
        certificate_number="KLS-ACAD-2026-00184",
        student_name="Ananya Rao",
        domain_title="Full Stack Python Development",
        duration="4 weeks",
    )

    assert "KLS-ACAD-2026-00184" in certificate_url
    assert qr_url.endswith("-qr.png")

    html = next(v for k, v in captured.items() if k.endswith(".html")).decode()
    assert "/verify/KLS-ACAD-2026-00184" in html
    assert "data:image/png;base64," in html
    assert "Pvt. Ltd" not in html


def test_qr_encodes_the_url():
    uri = build_qr_data_uri("https://academy.klstechsolutions.in/verify/KLS-ACAD-2026-00184")
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > 200
