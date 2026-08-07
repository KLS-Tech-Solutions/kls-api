"""
Email delivery.

Phase 8 will wire real SMTP. Until then this records every message in
`email_logs` and returns the action link to the caller, so an invite can be
sent by hand without the flow being blocked on infrastructure. The call sites
never change when delivery is switched on — only `_send` does.
"""

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EmailLog, EmailStatus

logger = logging.getLogger(__name__)


@dataclass
class Outbox:
    """What was sent, or would have been. `action_url` is surfaced in the UI."""

    recipient: str
    subject: str
    body: str
    action_url: str | None = None
    delivered: bool = False


def _send(to: str, subject: str, body: str) -> bool:
    if not settings.SMTP_HOST:
        logger.info("Email suppressed (SMTP not configured): %s → %s", subject, to)
        return False

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as exc:  # noqa: BLE001 — delivery must never break a request
        logger.warning("Email delivery failed for %s: %s", to, exc)
        return False


def send_email(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    to: str,
    subject: str,
    body: str,
    action_url: str | None = None,
) -> Outbox:
    delivered = _send(to, subject, body)

    db.add(
        EmailLog(
            user_id=user_id,
            recipient_email=to,
            subject=subject,
            status=EmailStatus.SENT if delivered else EmailStatus.QUEUED,
            error=None if delivered else "SMTP not configured",
        )
    )

    return Outbox(
        recipient=to,
        subject=subject,
        body=body,
        action_url=action_url,
        delivered=delivered,
    )


# --------------------------------------------------------------------------


def send_admin_invite(
    db: Session,
    *,
    user_id: uuid.UUID,
    to: str,
    full_name: str,
    invited_by: str,
    token: str,
    role: str,
) -> Outbox:
    role_label = "super administrator" if role == "super_admin" else "administrator"
    url = f"{settings.ADMIN_BASE_URL}/accept-invite?token={token}"

    body = (
        f"Hello {full_name},\n\n"
        f"{invited_by} has invited you to join the KLS Academy admin console as a "
        f"{role_label}.\n\n"
        f"Set your password and sign in:\n{url}\n\n"
        "This link expires in 7 days. If you weren't expecting this, ignore it — "
        "no account is active until the link is used.\n\n"
        "KLS Tech Solutions"
    )

    return send_email(
        db,
        user_id=user_id,
        to=to,
        subject="You've been invited to the KLS Academy admin console",
        body=body,
        action_url=url,
    )
