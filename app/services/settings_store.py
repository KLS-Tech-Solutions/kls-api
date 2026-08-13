"""
Operational settings a super admin can change at runtime.

Values live in `platform_settings` rather than the environment because the
certificate fee is a business lever, not a deployment detail — changing it
should not need a redeploy or SSH access to the VPS.

Each key has a reader that falls back to the `.env` value when the row does
not exist yet, so a fresh database behaves exactly as it did before this table
existed and no seeding step is mandatory.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PlatformSetting

logger = logging.getLogger(__name__)

CERTIFICATE_FEE_KEY = "certificate_fee_paise"

# The fee is stored in paise, matching Razorpay. The bounds are deliberately
# wide but not unbounded: a fat-fingered extra zero is the classic payments
# mistake, and ₹0 would silently make certificates free.
MIN_FEE_PAISE = 100        # ₹1
MAX_FEE_PAISE = 5_000_000  # ₹50,000


def _row(db: Session, key: str) -> PlatformSetting | None:
    """
    Reads a setting, tolerating a database that has not been migrated yet.

    `platform_settings` is newer than the rest of the schema, so an
    installation running `alembic upgrade head` late would otherwise throw
    `no such table` from inside `/me/journey` and `/admin/settings` — taking
    down the student dashboard and the admin payments screen over a value that
    has a perfectly good default. The read is rolled back so the failed
    statement does not poison the surrounding transaction.
    """
    try:
        return db.scalar(select(PlatformSetting).where(PlatformSetting.key == key))
    except (OperationalError, ProgrammingError):
        logger.warning(
            "platform_settings is missing — run `alembic upgrade head`. "
            "Falling back to the value from the environment."
        )
        db.rollback()
        return None


def certificate_fee_paise(db: Session) -> int:
    """
    The current certificate fee. Falls back to `CERTIFICATE_FEE_PAISE` from the
    environment until a super admin sets one, so nothing breaks before the
    first edit.
    """
    row = _row(db, CERTIFICATE_FEE_KEY)
    if row is None:
        return settings.CERTIFICATE_FEE_PAISE
    try:
        return int(row.value)
    except ValueError:
        # A corrupt row must not stop a student paying.
        return settings.CERTIFICATE_FEE_PAISE


def set_certificate_fee_paise(
    db: Session, amount: int, *, actor_id: uuid.UUID | None = None
) -> int:
    """
    Writes the new fee. Callers validate the range first; this asserts it again
    because the amount ends up on a real payment.

    **Payments already created keep their own amount.** `Payment.amount` is
    written at order time and never re-read from here, so a student who opened
    checkout before a price change pays what they were quoted.
    """
    if not MIN_FEE_PAISE <= amount <= MAX_FEE_PAISE:
        raise ValueError("Fee out of range")

    row = _row(db, CERTIFICATE_FEE_KEY)
    if row is None:
        row = PlatformSetting(key=CERTIFICATE_FEE_KEY, value=str(amount))
        db.add(row)
    else:
        row.value = str(amount)

    row.updated_by = actor_id
    row.updated_at_utc = datetime.now(timezone.utc)
    db.flush()
    return amount
