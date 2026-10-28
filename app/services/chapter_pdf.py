"""
Study-note PDFs, in the KLS house style.

These are the chapter notes students download from their dashboard. Unlike the
offer letter and the certificate — single-page fixed compositions — a chapter
is flowed text of unpredictable length, so this is a paginating renderer: it
measures each block, breaks pages where they need to break, and repeats the
letterhead and footer on every one.

**Why the notes are branded this heavily.** They are the one thing the platform
gives away before a student has done anything, which makes them the one thing
most worth lifting. A diagonal watermark on every page, the seal, and a footer
naming the chapter and the organisation mean a copy that turns up elsewhere is
visibly ours. Copy and extraction are also switched off at the PDF level — see
`_encryption` for what that is and is not worth.

Fonts are the base-14 set only, exactly as in `documents.py`: no font file is
embedded, so the output is byte-identical on Windows and on the Linux server.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas

from app.core.dates import today_in_ist
from app.services.documents import (
    BOLD,
    BRAND,
    CANVAS,
    COMPANY,
    INK,
    LINE,
    MUTED,
    NAVY,
    REGULAR,
    _draw,
    _draw_image,
    _faded,
    _gradient_bar,
    _tracked,
    _wrap,
)

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

HEADER_H = 26 * mm
FOOTER_H = 16 * mm
TOP = PAGE_H - HEADER_H - 10 * mm
BOTTOM = FOOTER_H + 8 * mm

MONO = "Courier"
MONO_BOLD = "Courier-Bold"

CODE_BG = colors.HexColor("#0d2033")
CODE_INK = colors.HexColor("#e8f1f8")
CODE_DIM = colors.HexColor("#7fa8c4")
NOTE_BG = colors.HexColor("#eef6fc")
WARN_BG = colors.HexColor("#fdf4e3")
WARN_EDGE = colors.HexColor("#c9a227")


# ---------------------------------------------------------------------------
# The content model
# ---------------------------------------------------------------------------
#
# A chapter is a list of blocks. Keeping content as data rather than as a
# string of markup means the renderer owns every typographic decision, and the
# curriculum module stays readable by someone who is not thinking about PDFs.


@dataclass
class Block:
    kind: str          # h2 | h3 | p | bullets | steps | code | note | warn | key
    text: str = ""
    items: list[str] = field(default_factory=list)
    caption: str = ""


def h2(text: str) -> Block:
    return Block("h2", text)


def h3(text: str) -> Block:
    return Block("h3", text)


def p(text: str) -> Block:
    return Block("p", text)


def bullets(*items: str) -> Block:
    return Block("bullets", items=list(items))


def steps(*items: str) -> Block:
    return Block("steps", items=list(items))


def code(body: str, caption: str = "") -> Block:
    return Block("code", text=body.strip("\n"), caption=caption)


def note(text: str) -> Block:
    return Block("note", text)


def warn(text: str) -> Block:
    return Block("warn", text)


def key(text: str) -> Block:
    """A single sentence worth remembering. Set large, in the brand colour."""
    return Block("key", text)


@dataclass
class Chapter:
    domain: str
    number: int
    title: str
    level: str          # Beginner | Intermediate | Advanced
    summary: str
    minutes: int
    outcomes: list[str]
    blocks: list[Block]


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------


def _header(c: pdfcanvas.Canvas, chapter: Chapter, page: int) -> None:
    """Letterhead. Full on page 1, a slim rule on the rest."""
    if page == 1:
        _gradient_bar(c, 0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, NAVY, BRAND)

        card_w, card_h = 34 * mm, 15 * mm
        c.setFillColor(colors.white)
        c.roundRect(
            MARGIN, PAGE_H - HEADER_H + (HEADER_H - card_h) / 2,
            card_w, card_h, 2.5 * mm, stroke=0, fill=1,
        )
        _draw_image(
            c, "kls-logo.png",
            MARGIN + 4 * mm, PAGE_H - HEADER_H + (HEADER_H - card_h) / 2 + 2.6 * mm,
            26 * mm,
        )

        x = MARGIN + card_w + 8 * mm
        _tracked(c, "KLS ACADEMY", x, PAGE_H - 11 * mm,
                 font=BOLD, size=10, tracking=3.4, colour=colors.white)
        c.setFont(REGULAR, 7.8)
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.85))
        c.drawString(x, PAGE_H - 15.5 * mm, "Study Notes")
        c.drawString(x, PAGE_H - 19.5 * mm,
                     f"A learning initiative of {COMPANY} · MSME registered")

        c.setFont(BOLD, 8.4)
        c.setFillColor(colors.white)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - 12.5 * mm, chapter.domain.upper())
        c.setFont(REGULAR, 7.6)
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.85))
        c.drawRightString(
            PAGE_W - MARGIN, PAGE_H - 17 * mm,
            f"Chapter {chapter.number} · {chapter.level}",
        )
    else:
        _gradient_bar(c, 0, PAGE_H - 4 * mm, PAGE_W, 4 * mm, NAVY, BRAND)
        c.setFont(REGULAR, 7.4)
        c.setFillColor(MUTED)
        c.drawString(MARGIN, PAGE_H - 11 * mm, f"KLS Academy · {chapter.domain}")
        c.drawRightString(
            PAGE_W - MARGIN, PAGE_H - 11 * mm,
            f"Chapter {chapter.number} — {chapter.title}",
        )
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(MARGIN, PAGE_H - 13.5 * mm, PAGE_W - MARGIN, PAGE_H - 13.5 * mm)


def _watermark(c: pdfcanvas.Canvas) -> None:
    """
    The seal, very faint, plus a diagonal line of text.

    Neither stops a determined copy — a screenshot defeats both. What they do
    is make an unattributed copy obviously an unattributed copy, which is the
    realistic goal for material that is given away for free.
    """
    seal = _faded("seal.png", 0.035)
    if seal is not None:
        size = 95 * mm
        _draw(c, seal, (PAGE_W - size) / 2, (PAGE_H - size) / 2, size)

    c.saveState()
    c.translate(PAGE_W / 2, PAGE_H / 2)
    c.rotate(54)
    c.setFont(BOLD, 34)
    c.setFillColor(colors.Color(0.07, 0.53, 0.78, alpha=0.055))
    c.drawCentredString(0, 0, "KLS ACADEMY")
    c.setFont(REGULAR, 11)
    c.drawCentredString(0, -16, "FOR ENROLLED STUDENTS · NOT FOR REDISTRIBUTION")
    c.restoreState()


def _footer(c: pdfcanvas.Canvas, chapter: Chapter, page: int) -> None:
    y = FOOTER_H
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)

    c.setFont(REGULAR, 6.9)
    c.setFillColor(MUTED)
    c.drawString(
        MARGIN, y - 5 * mm,
        f"© {today_in_ist().year} {COMPANY} · MSME registered · Bangalore",
    )
    c.drawString(
        MARGIN, y - 8.6 * mm,
        "Issued free to enrolled students of KLS Academy. Not for resale or "
        "redistribution.",
    )
    c.setFont(BOLD, 7.4)
    c.setFillColor(NAVY)
    c.drawRightString(PAGE_W - MARGIN, y - 5 * mm, f"Page {page}")


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------


def _code_lines(body: str) -> list[str]:
    """
    Code is not reflowed — wrapping a line of code changes what it means.

    Over-long lines are cut with a marker instead, which is visible rather than
    silent. In practice the curriculum keeps lines under the limit; this exists
    so a long line degrades predictably rather than running off the page.
    """
    limit = int((CONTENT_W - 12 * mm) / stringWidth("x", MONO, 8))
    out: list[str] = []
    for line in body.split("\n"):
        out.append(line if len(line) <= limit else line[: limit - 2] + " >")
    return out


CALLOUT_LABEL = {"note": "NOTE", "warn": "WATCH OUT"}


def _callout_indent(kind: str) -> float:
    """
    Where the first line of a callout starts, measured from the label.

    Hard-coding this was a bug: "WATCH OUT" is wider than "NOTE", so a fixed
    indent that cleared one ran straight through the other. Measuring means a
    future label of any length still lands clear of its text.
    """
    return 6 * mm + stringWidth(CALLOUT_LABEL[kind], BOLD, 8.6) + 4.5 * mm


def _callout_inner(kind: str) -> float:
    """Width available to the first line, which is the narrowest one."""
    return CONTENT_W - _callout_indent(kind) - 6 * mm


def _height(block: Block) -> float:
    """
    How tall this block will be. Measured before drawing so a block can be
    moved to the next page whole, rather than being split across the break.
    """
    if block.kind == "h2":
        return 13 * mm
    if block.kind == "h3":
        return 9 * mm
    if block.kind == "p":
        return len(_wrap(block.text, REGULAR, 9.3, CONTENT_W)) * 4.9 * mm + 2.4 * mm
    if block.kind in ("bullets", "steps"):
        total = 1.6 * mm
        for item in block.items:
            total += len(_wrap(item, REGULAR, 9.3, CONTENT_W - 8 * mm)) * 4.9 * mm
            total += 1.8 * mm
        return total
    if block.kind == "code":
        lines = _code_lines(block.text)
        height = len(lines) * 3.9 * mm + 9 * mm
        if block.caption:
            height += 4.8 * mm
        return height
    if block.kind in ("note", "warn"):
        return (
            len(_wrap(block.text, REGULAR, 9, _callout_inner(block.kind)))
            * 4.7 * mm
            + 9 * mm
        )
    if block.kind == "key":
        return len(_wrap(block.text, BOLD, 11.5, CONTENT_W - 10 * mm)) * 5.8 * mm + 8 * mm
    return 0


def _draw_block(c: pdfcanvas.Canvas, block: Block, y: float) -> float:
    """Draws one block with its top at `y`; returns the new cursor."""
    if block.kind == "h2":
        y -= 3.5 * mm
        c.setFillColor(BRAND)
        c.roundRect(MARGIN, y - 4.6 * mm, 3.2 * mm, 6.4 * mm, 1.2 * mm, stroke=0, fill=1)
        c.setFont(BOLD, 13.5)
        c.setFillColor(NAVY)
        c.drawString(MARGIN + 7 * mm, y - 3.4 * mm, block.text)
        return y - 9.5 * mm

    if block.kind == "h3":
        y -= 2.4 * mm
        c.setFont(BOLD, 10.4)
        c.setFillColor(INK)
        c.drawString(MARGIN, y - 3 * mm, block.text)
        return y - 6.6 * mm

    if block.kind == "p":
        c.setFont(REGULAR, 9.3)
        c.setFillColor(colors.HexColor("#3f5160"))
        for line in _wrap(block.text, REGULAR, 9.3, CONTENT_W):
            y -= 4.9 * mm
            c.drawString(MARGIN, y, line)
        return y - 2.4 * mm

    if block.kind in ("bullets", "steps"):
        y -= 1.6 * mm
        for index, item in enumerate(block.items, start=1):
            lines = _wrap(item, REGULAR, 9.3, CONTENT_W - 8 * mm)
            first = y - 4.9 * mm

            if block.kind == "steps":
                c.setFillColor(BRAND)
                c.circle(MARGIN + 2.1 * mm, first + 0.9 * mm, 2.1 * mm, stroke=0, fill=1)
                c.setFont(BOLD, 6.4)
                c.setFillColor(colors.white)
                c.drawCentredString(MARGIN + 2.1 * mm, first - 0.8 * mm, str(index))
            else:
                c.setFillColor(BRAND)
                c.circle(MARGIN + 2 * mm, first + 0.9 * mm, 0.95 * mm, stroke=0, fill=1)

            c.setFont(REGULAR, 9.3)
            c.setFillColor(colors.HexColor("#3f5160"))
            for line in lines:
                y -= 4.9 * mm
                c.drawString(MARGIN + 8 * mm, y, line)
            y -= 1.8 * mm
        return y

    if block.kind == "code":
        if block.caption:
            c.setFont(BOLD, 7.2)
            c.setFillColor(MUTED)
            c.drawString(MARGIN, y - 3.4 * mm, block.caption.upper())
            y -= 4.8 * mm

        lines = _code_lines(block.text)
        height = len(lines) * 3.9 * mm + 7 * mm
        c.setFillColor(CODE_BG)
        c.roundRect(MARGIN, y - height, CONTENT_W, height, 2 * mm, stroke=0, fill=1)
        # A brand-coloured spine, so a code block reads as part of the document
        # rather than as a pasted screenshot.
        c.setFillColor(BRAND)
        c.roundRect(MARGIN, y - height, 1.6 * mm, height, 0.8 * mm, stroke=0, fill=1)

        text_y = y - 5.6 * mm
        for line in lines:
            stripped = line.lstrip()
            comment = stripped.startswith("#") or stripped.startswith("//")
            c.setFont(MONO, 8)
            c.setFillColor(CODE_DIM if comment else CODE_INK)
            c.drawString(MARGIN + 5.5 * mm, text_y, line)
            text_y -= 3.9 * mm
        return y - height - 3 * mm

    if block.kind in ("note", "warn"):
        indent = _callout_indent(block.kind)
        lines = _wrap(block.text, REGULAR, 9, _callout_inner(block.kind))
        height = len(lines) * 4.7 * mm + 7 * mm

        c.setFillColor(NOTE_BG if block.kind == "note" else WARN_BG)
        c.roundRect(MARGIN, y - height, CONTENT_W, height, 1.8 * mm, stroke=0, fill=1)
        c.setFillColor(BRAND if block.kind == "note" else WARN_EDGE)
        c.roundRect(MARGIN, y - height, 1.6 * mm, height, 0.8 * mm, stroke=0, fill=1)

        c.setFont(BOLD, 8.6)
        c.setFillColor(NAVY if block.kind == "note" else colors.HexColor("#8a6d10"))
        c.drawString(MARGIN + 6 * mm, y - 5.4 * mm, CALLOUT_LABEL[block.kind])

        c.setFont(REGULAR, 9)
        c.setFillColor(colors.HexColor("#3f5160"))
        text_y = y - 5.4 * mm
        for index, line in enumerate(lines):
            if index == 0:
                # Beside the label, clear of it by measurement rather than hope.
                c.drawString(MARGIN + indent, text_y, line)
            else:
                text_y -= 4.7 * mm
                c.drawString(MARGIN + 6 * mm, text_y, line)
        return y - height - 3 * mm

    if block.kind == "key":
        lines = _wrap(block.text, BOLD, 11.5, CONTENT_W - 10 * mm)
        height = len(lines) * 5.8 * mm + 6 * mm
        c.setFillColor(CANVAS)
        c.roundRect(MARGIN, y - height, CONTENT_W, height, 2 * mm, stroke=0, fill=1)
        c.setFont(BOLD, 11.5)
        c.setFillColor(NAVY)
        text_y = y - 5.6 * mm
        for line in lines:
            c.drawString(MARGIN + 6 * mm, text_y, line)
            text_y -= 5.8 * mm
        return y - height - 3 * mm

    return y


# ---------------------------------------------------------------------------
# Title block and the document itself
# ---------------------------------------------------------------------------


def _title_block(c: pdfcanvas.Canvas, chapter: Chapter, y: float) -> float:
    c.setFont(BOLD, 7.6)
    c.setFillColor(BRAND)
    _tracked(c, f"CHAPTER {chapter.number} · {chapter.level.upper()}",
             MARGIN, y, font=BOLD, size=7.6, tracking=1.8, colour=BRAND)
    y -= 9 * mm

    for line in _wrap(chapter.title, BOLD, 20, CONTENT_W):
        c.setFont(BOLD, 20)
        c.setFillColor(INK)
        c.drawString(MARGIN, y, line)
        y -= 9 * mm

    y -= 1 * mm
    c.setFillColor(BRAND)
    c.rect(MARGIN, y, 26 * mm, 1.4 * mm, stroke=0, fill=1)
    y -= 7 * mm

    c.setFont(REGULAR, 9.6)
    c.setFillColor(colors.HexColor("#3f5160"))
    for line in _wrap(chapter.summary, REGULAR, 9.6, CONTENT_W):
        y -= 5.2 * mm
        c.drawString(MARGIN, y, line)

    y -= 7 * mm

    # What you will be able to do, boxed. Students skim; this is the part that
    # tells them whether the next twenty minutes are worth it.
    inner = CONTENT_W - 12 * mm
    wrapped = [_wrap(o, REGULAR, 9, inner - 6 * mm) for o in chapter.outcomes]
    height = sum(len(w) * 4.7 * mm + 1.6 * mm for w in wrapped) + 13 * mm

    c.setFillColor(CANVAS)
    c.roundRect(MARGIN, y - height, CONTENT_W, height, 2 * mm, stroke=0, fill=1)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.roundRect(MARGIN, y - height, CONTENT_W, height, 2 * mm, stroke=1, fill=0)

    _tracked(c, "BY THE END OF THIS CHAPTER", MARGIN + 6 * mm, y - 6.4 * mm,
             font=BOLD, size=7.4, tracking=1.6, colour=NAVY)
    c.setFont(REGULAR, 7.4)
    c.setFillColor(MUTED)
    c.drawRightString(PAGE_W - MARGIN - 6 * mm, y - 6.4 * mm,
                      f"About {chapter.minutes} minutes")

    item_y = y - 11 * mm
    for lines in wrapped:
        c.setFillColor(BRAND)
        c.circle(MARGIN + 8 * mm, item_y - 1.6 * mm, 0.95 * mm, stroke=0, fill=1)
        c.setFont(REGULAR, 9)
        c.setFillColor(colors.HexColor("#3f5160"))
        for line in lines:
            item_y -= 4.7 * mm
            c.drawString(MARGIN + 13 * mm, item_y, line)
        item_y -= 1.6 * mm

    return y - height - 6 * mm


def _encryption():
    """
    Turns off copy, extraction and modification in the produced PDF.

    Worth being clear about what this is: it is a flag that compliant readers
    honour, not encryption that resists an attacker. Anyone determined can
    strip it in a minute, and a screenshot ignores it entirely. What it does do
    is stop the casual case — selecting the text and pasting it into a blog —
    which is the case that actually happens.

    The user password stays empty so the file opens without a prompt. A
    password students would have to be told is a support burden that protects
    nothing, since they would tell each other.
    """
    from reportlab.lib.pdfencrypt import StandardEncryption

    return StandardEncryption(
        userPassword="",
        ownerPassword="KLS-" + COMPANY.replace(" ", "-"),
        canPrint=1,
        canModify=0,
        canCopy=0,
        canAnnotate=0,
        strength=128,
    )


def render_chapter(chapter: Chapter) -> bytes:
    """Renders one chapter to PDF bytes."""
    buffer = io.BytesIO()
    c = pdfcanvas.Canvas(buffer, pagesize=A4, encrypt=_encryption())
    c.setTitle(f"{chapter.domain} — Chapter {chapter.number}: {chapter.title}")
    c.setAuthor(COMPANY)
    c.setSubject(f"KLS Academy study notes · {chapter.level}")
    c.setCreator("KLS Academy")

    page = 1
    _watermark(c)
    _header(c, chapter, page)
    _footer(c, chapter, page)
    y = _title_block(c, chapter, TOP)

    for block in chapter.blocks:
        height = _height(block)

        # A heading alone at the foot of a page is an orphan; push it over with
        # the text it introduces.
        lookahead = height
        if block.kind in ("h2", "h3"):
            lookahead += 18 * mm

        if y - lookahead < BOTTOM:
            c.showPage()
            page += 1
            _watermark(c)
            _header(c, chapter, page)
            _footer(c, chapter, page)
            y = PAGE_H - 20 * mm

        y = _draw_block(c, block, y)

    c.showPage()
    c.save()
    return buffer.getvalue()
