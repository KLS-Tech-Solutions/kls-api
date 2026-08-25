"""
Offer letter and certificate generation.

Rendered with ReportLab, which is pure Python with prebuilt wheels — it works
on Windows, macOS and Linux with no system libraries. WeasyPrint needed GTK,
which does not install cleanly on Windows and silently downgraded documents to
HTML; a student clicking "Download PDF" and getting a web page is not
acceptable, so the renderer was replaced.

Only ReportLab's base-14 fonts are used (Helvetica and Times), so a document
renders identically on a developer's Windows machine and on the Linux VPS.
Shipping a font file would look marginally nicer and introduce a whole class of
"why does the server output differ" bugs; it is not worth the trade.

Neither document carries a signature line. Both are issued electronically and
verified through the QR code or the verification cell, and a printed signature
line on an unsigned document is worse than none at all.

Every document is produced on demand and cached in storage, so a missing or
stale file can always be regenerated from the database record.
"""

import base64
import io
import logging
from datetime import date, datetime, timezone
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

COMPANY = "KLS Tech Solutions"
COMPANY_ADDRESS = "Bangalore - 560027"
COMPANY_EMAIL = "klstechsolutions2025@gmail.com"
COMPANY_SITE = "www.klstechsolutions.in"

ELECTRONIC_NOTE = (
    "This is an electronically generated document. No physical signature is "
    f"required. For verification, contact the {COMPANY} Verification Cell at "
    f"{COMPANY_SITE}"
)

# Brand palette, matching src/styles/theme.css in both frontends.
INK = colors.HexColor("#0a1a2b")
NAVY = colors.HexColor("#0b3a5e")
BRAND = colors.HexColor("#1387c8")
BODY = colors.HexColor("#4a5b6b")
MUTED = colors.HexColor("#7b8b99")
LINE = colors.HexColor("#e4eaf0")
CANVAS = colors.HexColor("#f7fafc")
PAPER = colors.HexColor("#fcfdfe")
STRIP = colors.HexColor("#f1f6fa")
GOLD = colors.HexColor("#c9a227")

BOLD = "Helvetica-Bold"
REGULAR = "Helvetica"
SERIF_BOLD = "Times-Bold"
SERIF_ITALIC = "Times-Italic"


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------

# Brand assets are decoded once. They are read on every enrolment and every
# certificate issue, and the seal is decoded twice per document.
_assets: dict = {}


def _image(name: str) -> ImageReader | None:
    if name not in _assets:
        path = BRAND_DIR / name
        if not path.exists():
            logger.warning("Brand asset missing: %s", path)
            _assets[name] = None
        else:
            _assets[name] = ImageReader(str(path))
    return _assets[name]


def _faded(name: str, alpha: float) -> ImageReader | None:
    """A washed-out copy of a brand asset, for use as a watermark."""
    key = (name, alpha)
    if key not in _assets:
        path = BRAND_DIR / name
        if not path.exists():
            logger.warning("Brand asset missing: %s", path)
            _assets[key] = None
        else:
            try:
                from PIL import Image

                image = Image.open(path).convert("RGBA")
                channels = list(image.split())
                channels[3] = channels[3].point(lambda v: int(v * alpha))
                image.putalpha(channels[3])
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                _assets[key] = ImageReader(io.BytesIO(buffer.getvalue()))
            except Exception:  # noqa: BLE001 — a watermark is never worth a 500
                # Deliberately drop the mark rather than fall back to the full
                # opacity asset: a solid seal behind the body text would be far
                # worse than no watermark at all.
                logger.warning("Could not fade %s; omitting the watermark", name)
                _assets[key] = None
    return _assets[key]


def _draw(c, image: ImageReader | None, x: float, y: float, width: float) -> float:
    """Draws with the aspect ratio preserved. Returns the height used."""
    if image is None:
        return 0.0
    iw, ih = image.getSize()
    height = width * ih / iw
    c.drawImage(image, x, y, width=width, height=height, mask="auto")
    return height


def _draw_image(c, name: str, x: float, y: float, width: float) -> float:
    return _draw(c, _image(name), x, y, width)


def _gradient_bar(c, x: float, y: float, width: float, height: float,
                  start=NAVY, end=BRAND, steps: int = 160) -> None:
    """Navy→blue bar, approximated in thin strips."""
    for i in range(steps):
        t = i / (steps - 1)
        c.setFillColorRGB(
            start.red + (end.red - start.red) * t,
            start.green + (end.green - start.green) * t,
            start.blue + (end.blue - start.blue) * t,
        )
        c.rect(x + width * i / steps, y, width / steps + 0.7, height,
               stroke=0, fill=1)


def _tracked_width(text: str, font: str, size: float, tracking: float) -> float:
    return pdfmetrics.stringWidth(text, font, size) + tracking * (len(text) - 1)


def _tracked(c, text: str, x: float, y: float, *, font=BOLD, size=9,
             tracking=2.2, colour=MUTED, centre=None, right=None) -> None:
    """
    Letterspaced label. `centre` or `right` override `x`.

    Wrapped in save/restore because character spacing is part of the PDF
    graphics state — without it every subsequent string on the page inherits
    the tracking, which is not obvious until you look at the rendered output.
    """
    width = _tracked_width(text, font, size, tracking)
    if centre is not None:
        x = centre - width / 2
    elif right is not None:
        x = right - width

    c.saveState()
    text_object = c.beginText(x, y)
    text_object.setFont(font, size)
    text_object.setFillColor(colour)
    text_object.setCharSpace(tracking)
    text_object.textOut(text)
    c.drawText(text_object)
    c.restoreState()


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
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


def _paragraph(c, text: str, x: float, y: float, max_width: float, *,
               size=10.5, leading=15.4, font=REGULAR, colour=BODY) -> float:
    """Draws wrapped text downward from `y`. Returns the new y."""
    c.setFillColor(colour)
    c.setFont(font, size)
    for line in _wrap(text, font, size, max_width):
        c.drawString(x, y, line)
        y -= leading
    return y


# --------------------------------------------------------------------------
# Offer letter — A4 portrait
# --------------------------------------------------------------------------


def _render_offer_letter(
    *, offer_number: str, student_name: str, domain_title: str, duration: str,
    batch_name: str, task_count: int, issued_on: datetime,
    starts_on: date | None = None,
) -> bytes:
    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left, right = 20 * mm, width - 20 * mm
    text_width = right - left

    c.setTitle(f"KLS Academy Offer Letter {offer_number}")
    c.setAuthor(COMPANY)
    c.setSubject(f"Internship offer for {student_name}")

    # --- letterhead band --------------------------------------------------
    band_height = 34 * mm
    band_y = height - band_height
    _gradient_bar(c, 0, band_y, width, band_height)

    # The KLS mark is dark navy artwork, so it needs a light card to sit on —
    # placed straight onto the band it would all but disappear.
    chip_w, chip_h = 32 * mm, 23 * mm
    chip_x, chip_y = left, band_y + (band_height - chip_h) / 2
    c.setFillColor(colors.white)
    c.roundRect(chip_x, chip_y, chip_w, chip_h, 2.6 * mm, stroke=0, fill=1)

    logo = _image("kls-logo.png")
    logo_w = 24 * mm
    if logo is not None:
        iw, ih = logo.getSize()
        _draw(c, logo, chip_x + (chip_w - logo_w) / 2,
              chip_y + (chip_h - logo_w * ih / iw) / 2, logo_w)

    tx = chip_x + chip_w + 7 * mm
    _tracked(c, "KLS ACADEMY", tx, band_y + band_height - 13.5 * mm,
             font=BOLD, size=13, tracking=3.4, colour=colors.white)
    c.setFont(REGULAR, 8.6)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.82))
    c.drawString(tx, band_y + band_height - 19.5 * mm,
                 "Virtual Internship Programme")
    c.drawString(tx, band_y + band_height - 24 * mm,
                 f"A learning initiative of {COMPANY}")

    _tracked(c, "REFERENCE", 0, band_y + band_height - 13.5 * mm, font=BOLD,
             size=7, tracking=1.8, colour=colors.Color(1, 1, 1, alpha=0.7),
             right=right)
    c.setFont(BOLD, 10.5)
    c.setFillColor(colors.white)
    c.drawRightString(right, band_y + band_height - 19 * mm, offer_number)
    c.setFont(REGULAR, 8.4)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.75))
    c.drawRightString(right, band_y + band_height - 24.5 * mm,
                      f"Issued {issued_on.strftime('%d %B %Y')}")

    # --- seal watermark ---------------------------------------------------
    mark = 92 * mm
    _draw(c, _faded("seal.png", 0.05), width / 2 - mark / 2,
          height / 2 - mark / 2 - 10 * mm, mark)

    # --- title ------------------------------------------------------------
    y = band_y - 16 * mm
    _tracked(c, "INTERNSHIP OFFER LETTER", left, y, font=BOLD, size=15,
             tracking=1.6, colour=INK)
    y -= 5 * mm
    _gradient_bar(c, left, y, 26 * mm, 1.4 * mm)
    y -= 12 * mm

    c.setFont(REGULAR, 10.5)
    c.setFillColor(BODY)
    c.drawString(left, y, "Dear")
    c.setFont(BOLD, 12)
    c.setFillColor(INK)
    c.drawString(left + pdfmetrics.stringWidth("Dear ", REGULAR, 10.5), y,
                 f"{student_name},")
    y -= 9 * mm

    plural = "s" if task_count != 1 else ""
    paragraphs = [
        f"It is our pleasure to offer you a place as a Virtual Intern in "
        f"{domain_title} with KLS Academy, the learning division of {COMPANY}, "
        f"an MSME registered organisation based in Bangalore.",

        f"The programme runs for {duration} and is conducted entirely online. "
        f"You will work through {task_count} structured technical task{plural}, "
        f"each one reviewed individually by a KLS engineer who returns written "
        f"feedback before the task is approved.",

        "On completion, you receive a QR-verified certificate that any employer "
        "can check independently against our public verification page — no "
        "email, no phone call, no waiting.",
    ]
    for paragraph in paragraphs:
        y = _paragraph(c, paragraph, left, y, text_width)
        y -= 3.6 * mm

    # --- programme at a glance -------------------------------------------
    y -= 2 * mm
    rows = [
        [("Domain", domain_title), ("Batch", batch_name),
         ("Duration", duration or "—")],
        [("Technical tasks", str(task_count)), ("Mode", "Fully remote"),
         ("Commences", starts_on.strftime("%d %b %Y") if starts_on else "—")],
    ]
    head_h, row_h = 9 * mm, 14 * mm
    table_h = head_h + row_h * len(rows)
    table_top = y
    table_bottom = table_top - table_h

    c.setFillColor(PAPER)
    c.roundRect(left, table_bottom, text_width, table_h, 2.4 * mm,
                stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.roundRect(left, table_top - head_h, text_width, head_h, 2.4 * mm,
                stroke=0, fill=1)
    # Square off the bottom of the header so it meets the first row cleanly.
    c.rect(left, table_top - head_h, text_width, 2.4 * mm, stroke=0, fill=1)
    _tracked(c, "PROGRAMME AT A GLANCE", left + 6 * mm, table_top - 6 * mm,
             font=BOLD, size=8.2, tracking=2.2, colour=colors.white)

    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.roundRect(left, table_bottom, text_width, table_h, 2.4 * mm,
                stroke=1, fill=0)

    col_w = text_width / 3
    for index, row in enumerate(rows):
        row_y = table_top - head_h - row_h * index
        if index:
            c.line(left, row_y, right, row_y)
        for column, (label, value) in enumerate(row):
            cell_x = left + col_w * column
            if column:
                c.line(cell_x, row_y, cell_x, row_y - row_h)
            _tracked(c, label.upper(), cell_x + 6 * mm, row_y - 5.6 * mm,
                     font=BOLD, size=7, tracking=1.3, colour=MUTED)
            # Long domain titles are truncated rather than allowed to run into
            # the neighbouring cell.
            c.setFont(BOLD, 10.5)
            c.setFillColor(INK)
            text = value
            while (pdfmetrics.stringWidth(text, BOLD, 10.5) > col_w - 12 * mm
                   and len(text) > 4):
                text = text[:-2] + "…"
            c.drawString(cell_x + 6 * mm, row_y - 11 * mm, text)

    y = table_bottom - 7 * mm

    # --- what this internship involves ------------------------------------
    terms = [
        "Self-paced within the batch window — you set your own hours.",
        "Each task requires the evidence configured for it: usually a public "
        "repository, screenshots and a short written explanation.",
        "A reviewer reads every submission and returns feedback if changes are "
        "needed. The next task unlocks as soon as you submit, not when you are "
        "approved, so review time never holds you up.",
        "Everything here is free — the study notes, the internship and the "
        "certificate. There is no fee at any stage and we never ask for card "
        "or bank details.",
        "Each domain includes chapter-wise study notes as downloadable PDFs, "
        "ordered from beginner to advanced. They are yours to keep.",
        "This is a learning engagement and does not constitute an offer of "
        "employment or a contract of service.",
    ]
    bullet_lines = sum(
        len(_wrap(term, REGULAR, 9.2, text_width - 20 * mm)) for term in terms
    )
    panel_h = 15 * mm + bullet_lines * 12.6
    panel_top = y

    c.setFillColor(CANVAS)
    c.roundRect(left, panel_top - panel_h, text_width, panel_h, 2.4 * mm,
                stroke=0, fill=1)
    c.setFillColor(BRAND)
    c.rect(left, panel_top - panel_h, 1.2 * mm, panel_h, stroke=0, fill=1)

    ty = panel_top - 8 * mm
    _tracked(c, "WHAT THIS INTERNSHIP INVOLVES", left + 7 * mm, ty, font=BOLD,
             size=8.2, tracking=2, colour=INK)
    ty -= 7 * mm
    for term in terms:
        c.setFillColor(BRAND)
        c.setFont(BOLD, 9.2)
        c.drawString(left + 7.5 * mm, ty, "—")
        ty = _paragraph(c, term, left + 13 * mm, ty, text_width - 20 * mm,
                        size=9.2, leading=12.6)

    # --- closing, seal and the electronic-document note -------------------
    # The closing block is bottom-anchored: its note box always clears the
    # footer band by the same margin, however many lines the paragraphs above
    # happened to take. Flowing it downward instead put the note under the
    # footer as soon as a long domain title wrapped onto an extra line.
    note_w = text_width - 46 * mm
    note_lines = _wrap(ELECTRONIC_NOTE, REGULAR, 8.4, note_w - 12 * mm)
    note_h = 8 * mm + len(note_lines) * 11.6

    # The note box ends 19 mm below this baseline, so this is the lowest the
    # closing line can sit while the box still clears the footer band.
    floor = 20 * mm + note_h + 19 * mm
    y = max(panel_top - panel_h - 10 * mm, floor)

    c.setFont(REGULAR, 10.5)
    c.setFillColor(BODY)
    c.drawString(left, y, "We are glad to have you with us, and we look "
                          "forward to seeing what you build.")
    y -= 12 * mm

    _tracked(c, f"FOR {COMPANY.upper()}", left, y, font=BOLD, size=7.6,
             tracking=1.4, colour=MUTED)

    # The seal is the mark of issue. There is no signature line, because
    # nothing here is signed by hand.
    seal_size = 33 * mm
    c.saveState()
    c.translate(right - seal_size + 3 * mm, y - 24 * mm)
    c.rotate(-8)
    _draw(c, _faded("seal.png", 0.9), 0, 0, seal_size)
    c.restoreState()

    note_top = y - 7 * mm

    c.setFillColor(CANVAS)
    c.roundRect(left, note_top - note_h, note_w, note_h, 2 * mm,
                stroke=0, fill=1)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.roundRect(left, note_top - note_h, note_w, note_h, 2 * mm,
                stroke=1, fill=0)

    ny = note_top - 5.5 * mm
    c.setFont(REGULAR, 8.4)
    c.setFillColor(BODY)
    for line in note_lines:
        c.drawString(left + 6 * mm, ny, line)
        ny -= 11.6

    # --- footer -----------------------------------------------------------
    footer_h = 15 * mm
    c.setFillColor(CANVAS)
    c.rect(0, 0, width, footer_h, stroke=0, fill=1)
    _gradient_bar(c, 0, footer_h, width, 0.9 * mm)

    msme_w = 13 * mm
    _draw_image(c, "msme.png", right - msme_w, 2.6 * mm, msme_w)

    c.setFillColor(MUTED)
    c.setFont(REGULAR, 7.8)
    c.drawString(left, 9 * mm,
                 f"{COMPANY} · {COMPANY_ADDRESS} · {COMPANY_EMAIL}")
    c.drawString(left, 5 * mm,
                 f"{offer_number}  ·  {_host(settings.ACADEMY_BASE_URL)}  ·  "
                 f"MSME registered")

    c.showPage()
    c.save()
    return buffer.getvalue()


def _host(url: str) -> str:
    """`https://academy.klstechsolutions.in/` → `academy.klstechsolutions.in`."""
    return url.split("://", 1)[-1].rstrip("/")


# --------------------------------------------------------------------------
# Certificate — A4 landscape
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
    *, certificate_number: str, student_name: str, domain_title: str,
    duration: str, issued_on: datetime, verify_url: str, qr_png: bytes,
) -> bytes:
    buffer = io.BytesIO()
    page = landscape(A4)
    c = pdf_canvas.Canvas(buffer, pagesize=page)
    width, height = page
    centre = width / 2

    c.setTitle(f"KLS Academy Certificate {certificate_number}")
    c.setAuthor(COMPANY)
    c.setSubject(f"Certificate of completion for {student_name}")

    # --- paper, edges and frame -------------------------------------------
    c.setFillColor(PAPER)
    c.rect(0, 0, width, height, stroke=0, fill=1)

    _gradient_bar(c, 0, height - 5 * mm, width, 5 * mm)
    _gradient_bar(c, 0, 0, width, 5 * mm)

    outer = 11 * mm
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.6)
    c.rect(outer, outer, width - 2 * outer, height - 2 * outer, stroke=1, fill=0)

    inner = 14 * mm
    c.setStrokeColor(BRAND)
    c.setLineWidth(0.5)
    c.rect(inner, inner, width - 2 * inner, height - 2 * inner, stroke=1, fill=0)

    # Corner ornaments — a gold dot with two short rules running out of it.
    arm = 13 * mm
    corners = [(inner, inner, 1, 1), (width - inner, inner, -1, 1),
               (inner, height - inner, 1, -1),
               (width - inner, height - inner, -1, -1)]
    for ox, oy, sx, sy in corners:
        px, py = ox + sx * 3 * mm, oy + sy * 3 * mm
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.4)
        c.line(px, py, ox + sx * arm, py)
        c.line(px, py, px, oy + sy * arm)
        c.setFillColor(GOLD)
        c.circle(px, py, 0.9 * mm, stroke=0, fill=1)

    # --- seal watermark ---------------------------------------------------
    mark = 108 * mm
    _draw(c, _faded("seal.png", 0.045), centre - mark / 2,
          height / 2 - mark / 2 - 6 * mm, mark)

    # --- crest ------------------------------------------------------------
    # Positions here are absolute rather than flowed. A certificate is a fixed
    # composition; letting blocks stack downward means one long name or domain
    # title silently collides with the row beneath it.
    _draw_image(c, "kls-logo.png", centre - 15 * mm, height - 44 * mm, 30 * mm)

    _tracked(c, "KLS ACADEMY", 0, height - 51 * mm, font=BOLD, size=9.5,
             tracking=5, colour=NAVY, centre=centre)
    c.setFont(REGULAR, 7.6)
    c.setFillColor(MUTED)
    c.drawCentredString(centre, height - 56 * mm,
                        f"A learning initiative of {COMPANY} · MSME registered")

    # --- title ------------------------------------------------------------
    _tracked(c, "CERTIFICATE OF COMPLETION", 0, height - 70 * mm,
             font=SERIF_BOLD, size=21, tracking=5.2, colour=INK, centre=centre)
    _gradient_bar(c, centre - 26 * mm, height - 76 * mm, 52 * mm, 1.2 * mm)

    c.setFont(SERIF_ITALIC, 12)
    c.setFillColor(BODY)
    c.drawCentredString(centre, height - 85 * mm, "This is to certify that")

    # --- recipient --------------------------------------------------------
    # A long name steps down a size rather than running into the border.
    name_size = 38.0
    while (pdfmetrics.stringWidth(student_name, SERIF_BOLD, name_size) > 200 * mm
           and name_size > 18):
        name_size -= 1
    c.setFont(SERIF_BOLD, name_size)
    c.setFillColor(NAVY)
    c.drawCentredString(centre, height - 101 * mm, student_name)

    rule_w = min(
        max(pdfmetrics.stringWidth(student_name, SERIF_BOLD, name_size)
            + 26 * mm, 90 * mm),
        220 * mm,
    )
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(centre - rule_w / 2, height - 107 * mm,
           centre + rule_w / 2, height - 107 * mm)

    # --- statement --------------------------------------------------------
    statement = (
        f"has successfully completed the {duration} Virtual Internship in "
        f"{domain_title} at KLS Academy, having finished and passed review on "
        f"every assigned technical task."
    )
    sy = height - 117 * mm
    c.setFillColor(BODY)
    c.setFont(REGULAR, 11.5)
    for line in _wrap(statement, REGULAR, 11.5, 190 * mm):
        c.drawCentredString(centre, sy, line)
        sy -= 16.5

    # --- detail strip -----------------------------------------------------
    details = [
        ("CERTIFICATE NO.", certificate_number),
        ("DOMAIN", domain_title),
        ("DURATION", duration or "—"),
        ("ISSUED ON", issued_on.strftime("%d %B %Y")),
    ]
    strip_w, strip_h = 236 * mm, 17 * mm
    strip_x = centre - strip_w / 2
    strip_top = 82 * mm

    c.setFillColor(STRIP)
    c.roundRect(strip_x, strip_top - strip_h, strip_w, strip_h, 2 * mm,
                stroke=0, fill=1)

    col_w = strip_w / len(details)
    for index, (label, value) in enumerate(details):
        cell_centre = strip_x + col_w * index + col_w / 2
        if index:
            c.setStrokeColor(LINE)
            c.setLineWidth(0.6)
            c.line(strip_x + col_w * index, strip_top - strip_h + 3 * mm,
                   strip_x + col_w * index, strip_top - 3 * mm)
        _tracked(c, label, 0, strip_top - 6.4 * mm, font=BOLD, size=6.6,
                 tracking=1.4, colour=MUTED, centre=cell_centre)
        c.setFont(BOLD, 9.6)
        c.setFillColor(INK)
        text = value
        while (pdfmetrics.stringWidth(text, BOLD, 9.6) > col_w - 8 * mm
               and len(text) > 4):
            text = text[:-2] + "…"
        c.drawCentredString(cell_centre, strip_top - 12.4 * mm, text)

    # --- verification · seal · issuing body -------------------------------
    base = 27 * mm
    qr_size = 24 * mm
    qr_x = 26 * mm

    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.rect(qr_x - 1.5 * mm, base - 1.5 * mm, qr_size + 3 * mm, qr_size + 3 * mm,
           stroke=1, fill=0)
    c.drawImage(ImageReader(io.BytesIO(qr_png)), qr_x, base,
                width=qr_size, height=qr_size, mask="auto")

    tx = qr_x + qr_size + 6 * mm
    _tracked(c, "SCAN TO VERIFY", tx, base + qr_size - 4 * mm, font=BOLD,
             size=7.2, tracking=1.6, colour=INK)
    c.setFont(REGULAR, 7.4)
    c.setFillColor(MUTED)
    c.drawString(tx, base + qr_size - 9.5 * mm, _host(settings.ACADEMY_BASE_URL))
    c.drawString(tx, base + qr_size - 13.5 * mm, f"/verify/{certificate_number}")
    c.drawString(tx, base + qr_size - 19.5 * mm,
                 "Independently checkable by any employer,")
    c.drawString(tx, base + qr_size - 23.5 * mm, "with no need to contact us.")

    seal_size = 33 * mm
    c.saveState()
    c.translate(centre - seal_size / 2 + 3 * mm, base - 1 * mm)
    c.rotate(-7)
    _draw(c, _faded("seal.png", 0.92), 0, 0, seal_size)
    c.restoreState()

    issuer_right = width - 26 * mm
    msme_w = 14 * mm
    _draw_image(c, "msme.png", issuer_right - msme_w, base + 12 * mm, msme_w)

    _tracked(c, "ISSUED BY", 0, base + 7.5 * mm, font=BOLD, size=6.6,
             tracking=1.4, colour=MUTED, right=issuer_right)
    c.setFont(BOLD, 9.6)
    c.setFillColor(INK)
    c.drawRightString(issuer_right, base + 2.5 * mm, COMPANY)
    c.setFont(REGULAR, 8)
    c.setFillColor(MUTED)
    c.drawRightString(issuer_right, base - 2 * mm,
                      f"{COMPANY_ADDRESS} · MSME registered")

    # --- foot -------------------------------------------------------------
    c.setFillColor(MUTED)
    c.setFont(REGULAR, 7.4)
    c.drawCentredString(centre, 18.5 * mm, ELECTRONIC_NOTE)

    c.showPage()
    c.save()
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def generate_offer_letter(
    *, offer_number: str, student_name: str, domain_title: str, duration: str,
    batch_name: str, task_count: int, issued_on: datetime | None = None,
    starts_on: date | None = None,
) -> str:
    """Renders the offer letter, stores it, and returns its URL."""
    pdf = _render_offer_letter(
        offer_number=offer_number,
        student_name=student_name,
        domain_title=domain_title,
        duration=duration,
        batch_name=batch_name,
        task_count=task_count,
        issued_on=issued_on or datetime.now(timezone.utc),
        starts_on=starts_on,
    )
    key = f"offer-letters/{offer_number.replace('/', '-')}.pdf"
    return upload_bytes(pdf, key, "application/pdf")


def generate_certificate(
    *, certificate_number: str, student_name: str, domain_title: str,
    duration: str, issued_on: datetime | None = None,
) -> tuple[str, str]:
    """Renders the certificate and its QR. Returns (certificate_url, qr_url)."""
    verify_url = f"{settings.ACADEMY_BASE_URL}/verify/{certificate_number}"
    qr = _qr_png(verify_url)

    pdf = _render_certificate(
        certificate_number=certificate_number,
        student_name=student_name,
        domain_title=domain_title,
        duration=duration,
        issued_on=issued_on or datetime.now(timezone.utc),
        verify_url=verify_url,
        qr_png=qr,
    )

    certificate_url = upload_bytes(
        pdf, f"certificates/{certificate_number}.pdf", "application/pdf"
    )
    qr_url = upload_bytes(qr, f"certificates/{certificate_number}-qr.png", "image/png")
    return certificate_url, qr_url
