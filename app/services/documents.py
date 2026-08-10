"""
Offer letter and certificate generation.

Rendered with ReportLab, which is pure Python with prebuilt wheels — it works
on Windows, macOS and Linux with no system libraries. WeasyPrint needed GTK,
which does not install cleanly on Windows and silently downgraded documents to
HTML; a student clicking "Download PDF" and getting a web page is not
acceptable, so the renderer was replaced.

Every document is produced on demand and cached in storage, so a missing or
stale file can always be regenerated from the database record.
"""

import base64
import io
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as pdf_canvas

from app.core.config import settings
from app.services.storage import upload_bytes

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
BRAND_DIR = STATIC_DIR / "brand"

# Brand palette, matching src/styles/theme.css in both frontends.
INK = colors.HexColor("#0a1a2b")
NAVY = colors.HexColor("#0b3a5e")
BRAND = colors.HexColor("#1387c8")
BODY = colors.HexColor("#4a5b6b")
MUTED = colors.HexColor("#7b8b99")
LINE = colors.HexColor("#e4eaf0")
CANVAS = colors.HexColor("#f7fafc")

BOLD = "Helvetica-Bold"
REGULAR = "Helvetica"


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------


def _image(name: str) -> ImageReader | None:
    path = BRAND_DIR / name
    if not path.exists():
        logger.warning("Brand asset missing: %s", path)
        return None
    return ImageReader(str(path))


def _draw_image(c, name: str, x: float, y: float, width: float) -> float:
    """Draws with the aspect ratio preserved. Returns the height used."""
    image = _image(name)
    if image is None:
        return 0.0

    iw, ih = image.getSize()
    height = width * ih / iw
    c.drawImage(image, x, y, width=width, height=height, mask="auto")
    return height


def _gradient_bar(c, x: float, y: float, width: float, height: float) -> None:
    """Navy→blue bar, approximated in thin strips."""
    steps = 120
    for i in range(steps):
        t = i / (steps - 1)
        c.setFillColorRGB(
            NAVY.red + (BRAND.red - NAVY.red) * t,
            NAVY.green + (BRAND.green - NAVY.green) * t,
            NAVY.blue + (BRAND.blue - NAVY.blue) * t,
        )
        c.rect(x + width * i / steps, y, width / steps + 0.6, height, stroke=0, fill=1)


def _wrap(c, text: str, font: str, size: float, max_width: float) -> list[str]:
    c.setFont(font, size)
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words, current = paragraph.split(), ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines


def _paragraph(
    c, text: str, x: float, y: float, max_width: float, *, size=10.5, leading=15.5,
    font=REGULAR, colour=BODY,
) -> float:
    """Draws wrapped text downward from `y`. Returns the new y."""
    c.setFillColor(colour)
    for line in _wrap(c, text, font, size, max_width):
        c.setFont(font, size)
        c.drawString(x, y, line)
        y -= leading
    return y


# --------------------------------------------------------------------------
# Offer letter
# --------------------------------------------------------------------------


def _render_offer_letter(
    *, offer_number: str, student_name: str, domain_title: str, duration: str,
    batch_name: str, task_count: int, issued_on: datetime,
) -> bytes:
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 20 * mm, width - 20 * mm
    text_width = right - left

    c.setTitle(f"KLS Academy Offer Letter {offer_number}")
    c.setAuthor("KLS Tech Solutions")

    _gradient_bar(c, 0, height - 6 * mm, width, 6 * mm)

    # --- header ---------------------------------------------------------
    y = height - 20 * mm
    logo_height = _draw_image(c, "kls-logo.png", left, y - 16 * mm, 36 * mm)

    c.setFont(REGULAR, 9)
    c.setFillColor(MUTED)
    c.drawRightString(right, y - 4 * mm, f"Ref: {offer_number}")
    c.drawRightString(right, y - 9 * mm, f"Date: {issued_on.strftime('%d %b %Y')}")

    y = y - max(logo_height, 16 * mm) - 14 * mm

    # --- title ----------------------------------------------------------
    c.setFillColor(INK)
    c.setFont(BOLD, 20)
    c.drawString(left, y, "Internship Offer Letter")
    y -= 12 * mm

    c.setFont(REGULAR, 11.5)
    c.drawString(left, y, f"Dear {student_name},")
    y -= 9 * mm

    # --- body -----------------------------------------------------------
    paragraphs = [
        f"We are pleased to offer you a position as a Virtual Intern in {domain_title} "
        "with KLS Academy, the learning division of KLS Tech Solutions, an MSME "
        "registered organisation.",
        f"This internship runs for {duration} and is conducted entirely remotely as part "
        f"of {batch_name}. You will complete {task_count} structured technical "
        f"task{'s' if task_count != 1 else ''}, each reviewed by a KLS engineer before "
        "approval.",
        "On successful completion of all assigned tasks, you will receive a QR-verified "
        "certificate of completion that any employer can independently verify.",
    ]
    for paragraph in paragraphs:
        y = _paragraph(c, paragraph, left, y, text_width)
        y -= 4 * mm

    # --- terms panel ------------------------------------------------------
    terms = [
        "Fully remote and self-paced within the batch window.",
        "Each task requires the evidence configured for it — typically a public "
        "repository, screenshots and a written explanation.",
        "Submissions are reviewed by a KLS engineer and returned with feedback if "
        "changes are needed.",
        "The internship is free. A one-time fee of Rs. 50 applies only when your "
        "certificate is issued.",
        "This is a learning engagement and does not constitute an offer of employment.",
    ]

    panel_lines = sum(len(_wrap(c, t, REGULAR, 9.5, text_width - 18 * mm)) for t in terms)
    panel_height = 14 * mm + panel_lines * 13
    panel_top = y - 2 * mm

    c.setFillColor(CANVAS)
    c.roundRect(left, panel_top - panel_height, text_width, panel_height, 3 * mm,
                stroke=0, fill=1)

    ty = panel_top - 9 * mm
    c.setFillColor(INK)
    c.setFont(BOLD, 10.5)
    c.drawString(left + 7 * mm, ty, "What this internship involves")
    ty -= 7 * mm

    for term in terms:
        c.setFillColor(BRAND)
        c.setFont(BOLD, 9.5)
        c.drawString(left + 7 * mm, ty, "•")
        ty = _paragraph(c, term, left + 12 * mm, ty, text_width - 19 * mm,
                        size=9.5, leading=13)

    # Anchor the closing near the foot of the page so the letter reads like a
    # letter, rather than leaving a block of dead space above the footer.
    y = min(panel_top - panel_height - 14 * mm, 76 * mm)

    # --- signature block, with the company seal on the right ------------
    c.setFillColor(INK)
    c.setFont(REGULAR, 10.5)
    c.drawString(left, y, "We look forward to seeing what you build.")
    y -= 12 * mm

    c.setFont(BOLD, 11)
    c.drawString(left, y, "KLS Tech Solutions")
    c.setFont(REGULAR, 9.5)
    c.setFillColor(BODY)
    c.drawString(left, y - 5 * mm, "Sudhamanagar, Bangalore - 560027")
    c.drawString(left, y - 10 * mm, "MSME registered")

    # The seal sits to the right of the signature, as a physical stamp would.
    seal_size = 34 * mm
    _draw_image(c, "seal.png", right - seal_size, y - 14 * mm, seal_size)

    # --- footer ---------------------------------------------------------
    footer_y = 18 * mm
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(left, footer_y + 12 * mm, right, footer_y + 12 * mm)

    msme_width = 16 * mm
    _draw_image(c, "msme.png", right - msme_width, footer_y - 2 * mm, msme_width)

    c.setFillColor(MUTED)
    c.setFont(REGULAR, 8.5)
    c.drawString(left, footer_y + 6 * mm, f"KLS Academy · {settings.ACADEMY_BASE_URL}")
    c.drawString(left, footer_y + 1.5 * mm, offer_number)

    c.showPage()
    c.save()
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Certificate
# --------------------------------------------------------------------------


def build_qr_data_uri(payload: str) -> str:
    import qrcode

    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"


def _qr_png(payload: str) -> bytes:
    import qrcode

    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _render_certificate(
    *, certificate_number: str, student_name: str, domain_title: str, duration: str,
    issued_on: datetime, verify_url: str, qr_png: bytes,
) -> bytes:
    buffer = io.BytesIO()
    page = landscape(A4)
    c = pdf_canvas.Canvas(buffer, pagesize=page)
    width, height = page
    left, right = 22 * mm, width - 22 * mm
    centre = width / 2

    c.setTitle(f"KLS Academy Certificate {certificate_number}")
    c.setAuthor("KLS Tech Solutions")

    _gradient_bar(c, 0, height - 6 * mm, width, 6 * mm)

    # Hairline border, inset — reads as a certificate without being ornate.
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.rect(12 * mm, 12 * mm, width - 24 * mm, height - 30 * mm, stroke=1, fill=0)

    y = height - 20 * mm
    logo_height = _draw_image(c, "kls-logo.png", left, y - 15 * mm, 34 * mm)
    msme_width = 18 * mm
    _draw_image(c, "msme.png", right - msme_width, y - 16 * mm, msme_width)

    y -= max(logo_height, 16 * mm) + 12 * mm

    c.setFillColor(MUTED)
    c.setFont(BOLD, 9)
    c.drawCentredString(centre, y, "C E R T I F I C A T E   O F   C O M P L E T I O N")
    y -= 16 * mm

    c.setFillColor(INK)
    c.setFont(BOLD, 30)
    c.drawCentredString(centre, y, student_name)
    y -= 8 * mm

    _gradient_bar(c, centre - 30 * mm, y, 60 * mm, 1.2 * mm)
    y -= 12 * mm

    statement = (
        f"has successfully completed the virtual internship in {domain_title} at "
        "KLS Academy, including every assigned technical task and all reviewed "
        "project submissions."
    )
    c.setFillColor(BODY)
    for line in _wrap(c, statement, REGULAR, 12, 180 * mm):
        c.setFont(REGULAR, 12)
        c.drawCentredString(centre, y, line)
        y -= 17

    y -= 10 * mm

    # --- details row -----------------------------------------------------
    details = [
        ("Certificate number", certificate_number),
        ("Duration", duration),
        ("Issued on", issued_on.strftime("%d %b %Y")),
    ]
    spacing = 62 * mm
    start = centre - spacing
    for index, (label, value) in enumerate(details):
        x = start + index * spacing
        c.setFillColor(MUTED)
        c.setFont(REGULAR, 8.5)
        c.drawCentredString(x, y, label)
        c.setFillColor(INK)
        c.setFont(BOLD, 10.5)
        c.drawCentredString(x, y - 6 * mm, value)

    y -= 20 * mm

    # --- QR + seal -------------------------------------------------------
    qr_size = 28 * mm
    c.drawImage(ImageReader(io.BytesIO(qr_png)), centre - qr_size / 2, y - qr_size,
                width=qr_size, height=qr_size, mask="auto")

    seal_size = 32 * mm
    _draw_image(c, "seal.png", right - seal_size - 6 * mm, y - seal_size + 2 * mm,
                seal_size)

    c.setFillColor(MUTED)
    c.setFont(REGULAR, 8)
    c.drawCentredString(centre, y - qr_size - 5 * mm, f"Scan to verify · {verify_url}")

    # --- footer ----------------------------------------------------------
    c.setFont(REGULAR, 8.5)
    c.drawString(left, 20 * mm, "KLS Tech Solutions · Sudhamanagar, Bangalore - 560027")
    c.drawString(left, 15.5 * mm, "MSME registered")
    c.drawRightString(right, 20 * mm, "Verify any certificate at")
    c.drawRightString(right, 15.5 * mm, f"{settings.ACADEMY_BASE_URL}/verify")

    c.showPage()
    c.save()
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def generate_offer_letter(
    *, offer_number: str, student_name: str, domain_title: str, duration: str,
    batch_name: str, task_count: int, issued_on: datetime | None = None,
) -> str:
    """Renders the offer letter, stores it, and returns its URL."""
    pdf = _render_offer_letter(
        offer_number=offer_number,
        student_name=student_name,
        domain_title=domain_title,
        duration=duration,
        batch_name=batch_name,
        task_count=task_count,
        issued_on=issued_on or datetime.now(),
    )
    key = f"offer-letters/{offer_number.replace('/', '-')}.pdf"
    return upload_bytes(pdf, key, "application/pdf")


def generate_certificate(
    *, certificate_number: str, student_name: str, domain_title: str, duration: str,
    issued_on: datetime | None = None,
) -> tuple[str, str]:
    """Renders the certificate and its QR. Returns (certificate_url, qr_url)."""
    verify_url = f"{settings.ACADEMY_BASE_URL}/verify/{certificate_number}"
    qr = _qr_png(verify_url)

    pdf = _render_certificate(
        certificate_number=certificate_number,
        student_name=student_name,
        domain_title=domain_title,
        duration=duration,
        issued_on=issued_on or datetime.now(),
        verify_url=verify_url,
        qr_png=qr,
    )

    certificate_url = upload_bytes(
        pdf, f"certificates/{certificate_number}.pdf", "application/pdf"
    )
    qr_url = upload_bytes(qr, f"certificates/{certificate_number}-qr.png", "image/png")
    return certificate_url, qr_url
