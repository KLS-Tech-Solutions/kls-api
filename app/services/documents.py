"""
Offer letter and certificate generation.

WeasyPrint needs system libraries (cairo, pango) that are present in the Docker
image but not everywhere, so the import is deferred and failures degrade to
storing the rendered HTML. A missing PDF renderer must never stop a student
enrolling or a certificate being issued — the record is what matters, the file
can be regenerated.
"""

import base64
import io
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.services.storage import upload_bytes

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _base_css() -> str:
    return (TEMPLATE_DIR / "base.css").read_text(encoding="utf-8")


def _asset_uri(name: str) -> str:
    """
    Images are inlined as data URIs so rendering never depends on the API being
    publicly reachable — a document generated on a private VPS still shows its
    logos.
    """
    path = STATIC_DIR / "brand" / name
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{encoded}"


def _render_pdf(html: str) -> bytes | None:
    try:
        from weasyprint import HTML  # imported lazily — see module docstring
    except Exception as exc:  # noqa: BLE001
        logger.warning("WeasyPrint unavailable, storing HTML instead: %s", exc)
        return None

    try:
        return HTML(string=html).write_pdf()
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF rendering failed, storing HTML instead: %s", exc)
        return None


def _store(html: str, folder: str, stem: str) -> str:
    pdf = _render_pdf(html)
    if pdf is not None:
        return upload_bytes(pdf, f"{folder}/{stem}.pdf", "application/pdf")
    return upload_bytes(html.encode("utf-8"), f"{folder}/{stem}.html", "text/html")


def build_qr_data_uri(payload: str) -> str:
    import qrcode

    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"


def generate_offer_letter(
    *,
    offer_number: str,
    student_name: str,
    domain_title: str,
    duration: str,
    batch_name: str,
    task_count: int,
    issued_on: datetime | None = None,
) -> str:
    """Returns the stored document URL."""
    html = _env.get_template("offer_letter.html").render(
        base_css=_base_css(),
        logo_url=_asset_uri("kls-logo.png"),
        msme_url=_asset_uri("msme.png"),
        offer_number=offer_number,
        student_name=student_name,
        domain_title=domain_title,
        duration=duration,
        batch_name=batch_name,
        task_count=task_count,
        issued_on=(issued_on or datetime.now()).strftime("%d %b %Y"),
        academy_url=settings.ACADEMY_BASE_URL,
    )

    stem = offer_number.replace("/", "-")
    return _store(html, "offer-letters", stem)


def generate_certificate(
    *,
    certificate_number: str,
    student_name: str,
    domain_title: str,
    duration: str,
    issued_on: datetime | None = None,
) -> tuple[str, str]:
    """Returns (certificate_url, qr_code_url)."""
    verify_url = f"{settings.ACADEMY_BASE_URL}/verify/{certificate_number}"
    qr_data_uri = build_qr_data_uri(verify_url)

    html = _env.get_template("certificate.html").render(
        base_css=_base_css(),
        logo_url=_asset_uri("kls-logo.png"),
        msme_url=_asset_uri("msme.png"),
        certificate_number=certificate_number,
        student_name=student_name,
        domain_title=domain_title,
        duration=duration,
        issued_on=(issued_on or datetime.now()).strftime("%d %b %Y"),
        verify_url=verify_url,
        qr_data_uri=qr_data_uri,
        academy_url=settings.ACADEMY_BASE_URL,
    )

    certificate_url = _store(html, "certificates", certificate_number)

    qr_png = base64.b64decode(qr_data_uri.split(",", 1)[1])
    qr_url = upload_bytes(qr_png, f"certificates/{certificate_number}-qr.png", "image/png")

    return certificate_url, qr_url
