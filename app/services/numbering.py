from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Certificate, OfferLetter


def next_offer_letter_number(db: Session) -> str:
    """KLS/ACAD/2026/00184 — sequential within the calendar year."""
    year = datetime.now().year
    prefix = f"KLS/ACAD/{year}/"
    count = db.scalar(
        select(func.count(OfferLetter.id)).where(OfferLetter.offer_letter_number.startswith(prefix))
    )
    return f"{prefix}{(count or 0) + 1:05d}"


def next_certificate_number(db: Session) -> str:
    """KLS-ACAD-2026-00184 — the format the public verification page parses."""
    year = datetime.now().year
    prefix = f"KLS-ACAD-{year}-"
    count = db.scalar(
        select(func.count(Certificate.id)).where(Certificate.certificate_number.startswith(prefix))
    )
    return f"{prefix}{(count or 0) + 1:05d}"
