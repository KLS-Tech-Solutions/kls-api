"""
Platform settings — super-admin-only operational levers.

Kept in its own router because these endpoints change how money is charged.
Reviewers can approve submissions all day; only a super admin moves the price.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_super_admin
from app.models import User
from app.schemas.settings import PlatformSettingsOut, UpdateCertificateFeeRequest
from app.services.notifications import log_activity
from app.services.settings_store import (
    MAX_FEE_PAISE,
    MIN_FEE_PAISE,
    certificate_fee_paise,
    set_certificate_fee_paise,
)

router = APIRouter(tags=["settings"])


def _current(db: Session) -> PlatformSettingsOut:
    return PlatformSettingsOut(
        certificate_fee_paise=certificate_fee_paise(db),
        min_fee_paise=MIN_FEE_PAISE,
        max_fee_paise=MAX_FEE_PAISE,
    )


@router.get("/admin/settings", response_model=PlatformSettingsOut)
def read_settings(
    _: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """Readable by any admin — the console shows the fee on the payments screen."""
    return _current(db)


@router.patch("/admin/settings/certificate-fee", response_model=PlatformSettingsOut)
def update_certificate_fee(
    payload: UpdateCertificateFeeRequest,
    actor: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Change the certificate issuance fee.

    Orders already created keep the amount they were quoted — `Payment.amount`
    is written at order time and never re-read, so a student mid-checkout is
    never surprised by a new price.
    """
    previous = certificate_fee_paise(db)

    try:
        set_certificate_fee_paise(db, payload.amount_paise, actor_id=actor.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"The fee must be between ₹{MIN_FEE_PAISE // 100} and "
                f"₹{MAX_FEE_PAISE // 100}"
            ),
        ) from exc

    log_activity(
        db,
        actor.id,
        f"Changed the certificate fee from ₹{previous / 100:.2f} "
        f"to ₹{payload.amount_paise / 100:.2f}",
        "settings",
        "certificate_fee_paise",
    )
    db.commit()
    return _current(db)
