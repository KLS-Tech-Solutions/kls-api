"""
Document numbers for offer letters and certificates.

**These are random, not sequential, and that is the whole point.**

The previous scheme was `count(rows) + 1`, which had two defects. It was not
atomic — two students enrolling in the same second both read the same count,
generated the same number, and one hit the unique constraint and got a 500 on
the most important click in the product. And it leaked: a certificate number is
public, so `KLS-ACAD-2026-00042` told anyone who saw it that forty-one others
existed and exactly what they were called.

A random suffix fixes both. There is no shared counter to race on, and knowing
one number tells you nothing about any other.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Certificate, OfferLetter

# Crockford's Base32: no I, L, O or U. Removing them means a number read off a
# printed certificate cannot be mistyped as a different valid one, and no
# unfortunate words appear by accident.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# 10 characters from a 32-symbol alphabet is 50 bits — a thousand million
# billion combinations. At any plausible scale for this platform the chance of
# ever generating a duplicate is negligible, and guessing one is not feasible.
LENGTH = 10

# How many times to retry on the astronomically unlikely collision before
# giving up. If this is ever exhausted something is badly wrong.
MAX_ATTEMPTS = 8


def _suffix() -> str:
    """A cryptographically random, unguessable identifier."""
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def _unique(db: Session, column, template: str) -> str:
    """
    Generates numbers until one is unused.

    The database still holds a unique constraint on both columns — this check
    is an optimisation that avoids a failed insert, not the guarantee. The
    constraint is the guarantee.
    """
    for _ in range(MAX_ATTEMPTS):
        candidate = template.format(suffix=_suffix())
        if db.scalar(select(column).where(column == candidate)) is None:
            return candidate

    raise RuntimeError(
        "Could not generate a unique document number after "
        f"{MAX_ATTEMPTS} attempts — check the random source"
    )


def next_offer_letter_number(db: Session) -> str:
    """KLS-ACAD-7QF3M2XKPB — random, unique, unguessable."""
    return _unique(db, OfferLetter.offer_letter_number, "KLS-ACAD-{suffix}")


def next_certificate_number(db: Session) -> str:
    """
    KLS-CERT-4B9WQZ1RHT — random, unique, unguessable.

    The prefix differs from the offer letter's so the two are never confused;
    the public verification page accepts either shape and only finds
    certificates.
    """
    return _unique(db, Certificate.certificate_number, "KLS-CERT-{suffix}")
