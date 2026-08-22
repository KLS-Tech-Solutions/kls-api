"""
Email delivery.

Every message is queued as a background task so a slow SMTP handshake never
delays a student's request, and every attempt is recorded in `email_logs`.

**Delivery failure never breaks a workflow.** If SMTP is down, an enrolment
still succeeds and the offer letter still exists — the student simply doesn't
get the notification. The in-app notification is always written regardless, so
nothing is lost.
"""

import logging
import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from fastapi import BackgroundTasks
from sqlalchemy import select

from app.core.config import settings
from app.models import EmailLog, EmailStatus, EmailTemplate

logger = logging.getLogger(__name__)

SUPPORT_EMAIL = "klstechsolutions2025@gmail.com"

# Shown in every email. New senders land in spam far more often than people
# expect, and a student who never checks the junk folder is a student stuck at
# the verification step with no idea why.
SPAM_NOTE = (
    "Not seeing our emails? Check your <strong>Spam</strong>, <strong>Junk</strong> "
    "or <strong>Bin</strong> folder and mark this message as “Not spam” so future "
    "updates reach your inbox."
)
SPAM_NOTE_TEXT = (
    "Not seeing our emails? Check your Spam, Junk or Bin folder and mark this "
    "message as 'Not spam' so future updates reach your inbox."
)


@dataclass
class Outbox:
    """What was sent, or would have been. `action_url` is surfaced in the UI."""

    recipient: str
    subject: str
    action_url: str | None = None
    delivered: bool = False


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _layout(*, heading: str, body_html: str, cta: tuple[str, str] | None = None) -> str:
    """
    One branded shell for every email.

    Table-based with inline styles, because Gmail, Outlook and most mobile
    clients strip <style> blocks and ignore modern CSS.
    """
    button = ""
    if cta:
        label, url = cta
        button = f"""
        <tr>
          <td style="padding: 8px 0 24px;">
            <a href="{url}"
               style="display:inline-block;background:#0b3a5e;color:#ffffff;
                      text-decoration:none;font-weight:bold;font-size:15px;
                      padding:13px 26px;border-radius:999px;">{label}</a>
          </td>
        </tr>
        <tr>
          <td style="padding-bottom:24px;font-size:12px;color:#7b8b99;
                     line-height:1.6;word-break:break-all;">
            If the button doesn't work, copy this link into your browser:<br />
            <span style="color:#1387c8;">{url}</span>
          </td>
        </tr>"""

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f7fafc;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#f7fafc;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="max-width:560px;background:#ffffff;border-radius:16px;
                        border:1px solid #e4eaf0;overflow:hidden;
                        font-family:Helvetica,Arial,sans-serif;">
            <tr>
              <td style="height:5px;background:#0b3a5e;"></td>
            </tr>
            <tr>
              <td style="padding:32px 32px 0;">
                <div style="font-size:15px;font-weight:bold;color:#0a1a2b;
                            letter-spacing:0.5px;">KLS ACADEMY</div>
              </td>
            </tr>
            <tr>
              <td style="padding:22px 32px 0;">
                <h1 style="margin:0;font-size:22px;line-height:1.3;color:#0a1a2b;">
                  {heading}</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 32px 0;font-size:15px;line-height:1.65;
                         color:#4a5b6b;">{body_html}</td>
            </tr>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="padding:20px 32px 0;">{button}</table>
            <tr>
              <td style="padding:4px 32px 0;">
                <div style="background:#f7fafc;border-radius:10px;padding:14px 16px;
                            font-size:13px;line-height:1.6;color:#4a5b6b;">
                  {SPAM_NOTE}
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 30px;">
                <div style="border-top:1px solid #e4eaf0;padding-top:18px;
                            font-size:12px;line-height:1.7;color:#7b8b99;">
                  KLS Tech Solutions · Bangalore - 560027<br />
                  MSME registered · <a href="mailto:{SUPPORT_EMAIL}"
                     style="color:#1387c8;text-decoration:none;">{SUPPORT_EMAIL}</a><br />
                  You're receiving this because you have a KLS Academy account.
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _plain(*, heading: str, body_lines: list[str], cta: tuple[str, str] | None = None) -> str:
    parts = [heading, "", *body_lines]
    if cta:
        label, url = cta
        parts += ["", f"{label}: {url}"]
    parts += [
        "",
        SPAM_NOTE_TEXT,
        "",
        "--",
        "KLS Tech Solutions · Bangalore - 560027",
        f"MSME registered · {SUPPORT_EMAIL}",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------


def _send_now(to: str, subject: str, html: str, text: str) -> tuple[bool, str | None]:
    if not settings.SMTP_HOST:
        return False, "SMTP not configured"

    name, address = parseaddr(settings.EMAIL_FROM)
    message = EmailMessage()
    message["From"] = formataddr((name or "KLS Academy", address or SUPPORT_EMAIL))
    message["To"] = to
    message["Subject"] = subject
    message["Reply-To"] = SUPPORT_EMAIL
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        return True, None
    except Exception as exc:  # noqa: BLE001 — delivery must never break a request
        logger.warning("Email delivery failed for %s: %s", to, exc)
        return False, str(exc)[:500]


def _deliver_and_log(
    *, user_id: uuid.UUID | None, to: str, subject: str, html: str, text: str,
    template_name: str,
) -> None:
    """
    Runs after the response has been sent, on its own database session — the
    request's session is already closed by then.
    """
    from app.core.database import SessionLocal

    delivered, error = _send_now(to, subject, html, text)

    # Logging is best effort. If the audit write fails the email has already
    # been sent (or already failed) — losing the log entry must not turn into
    # an exception in a background task nobody is watching.
    try:
        db = SessionLocal()
        try:
            template = db.scalar(
                select(EmailTemplate).where(
                    EmailTemplate.template_name == template_name
                )
            )
            db.add(
                EmailLog(
                    user_id=user_id,
                    template_id=template.id if template else None,
                    recipient_email=to,
                    subject=subject,
                    status=EmailStatus.SENT if delivered else EmailStatus.FAILED,
                    error=error,
                    sent_at=datetime.now(timezone.utc) if delivered else None,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not write email_logs entry for %s: %s", to, exc)


def queue_email(
    background: BackgroundTasks | None,
    *,
    user_id: uuid.UUID | None,
    to: str,
    subject: str,
    heading: str,
    body_html: str,
    body_text: list[str],
    template_name: str,
    cta: tuple[str, str] | None = None,
) -> Outbox:
    """
    Queues one email. Pass `background=None` to send inline — used by scripts
    and tests where there is no request to attach to.
    """
    html = _layout(heading=heading, body_html=body_html, cta=cta)
    text = _plain(heading=heading, body_lines=body_text, cta=cta)

    payload = {
        "user_id": user_id,
        "to": to,
        "subject": subject,
        "html": html,
        "text": text,
        "template_name": template_name,
    }

    if background is not None:
        background.add_task(_deliver_and_log, **payload)
        # Optimistic: the caller only needs to know whether SMTP is configured.
        return Outbox(
            recipient=to,
            subject=subject,
            action_url=cta[1] if cta else None,
            delivered=bool(settings.SMTP_HOST),
        )

    _deliver_and_log(**payload)
    return Outbox(
        recipient=to,
        subject=subject,
        action_url=cta[1] if cta else None,
        delivered=bool(settings.SMTP_HOST),
    )


# --------------------------------------------------------------------------
# Workflow emails
# --------------------------------------------------------------------------


def _academy(path: str = "") -> str:
    return f"{settings.ACADEMY_BASE_URL.rstrip('/')}{path}"


def send_welcome_verification(
    background, *, user_id, to: str, full_name: str, token: str
) -> Outbox:
    url = _academy(f"/verify-email?token={token}")
    first = full_name.split()[0]
    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject="Verify your email — KLS Academy",
        template_name="welcome",
        heading=f"Welcome to KLS Academy, {first}",
        body_html=(
            "<p>Your account is created. Confirm this email address to activate it and "
            "choose your internship domain.</p>"
            "<p>This link expires in 24 hours.</p>"
        ),
        body_text=[
            "Your account is created. Confirm this email address to activate it and "
            "choose your internship domain.",
            "This link expires in 24 hours.",
        ],
        cta=("Verify my email", url),
    )


def send_password_reset(background, *, user_id, to: str, token: str) -> Outbox:
    url = _academy(f"/reset-password?token={token}")
    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject="Reset your KLS Academy password",
        template_name="password_reset",
        heading="Reset your password",
        body_html=(
            "<p>Use the button below to choose a new password. The link expires in "
            "30 minutes and works once.</p>"
            "<p>If you didn't ask for this, ignore this email — your password has "
            "not changed.</p>"
        ),
        body_text=[
            "Use the link below to choose a new password. It expires in 30 minutes "
            "and works once.",
            "If you didn't ask for this, ignore this email — your password has not changed.",
        ],
        cta=("Set a new password", url),
    )


def send_offer_letter_ready(
    background, *, user_id, to: str, full_name: str, offer_number: str, domain_title: str
) -> Outbox:
    first = full_name.split()[0]
    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject=f"Your offer letter is ready — {offer_number}",
        template_name="offer_letter",
        heading=f"You're enrolled, {first}",
        body_html=(
            f"<p>Your offer letter for <strong>{domain_title}</strong> has been "
            f"generated. Reference <strong>{offer_number}</strong>.</p>"
            "<p><strong>Your first task:</strong> download the letter, post it on "
            "LinkedIn tagging KLS Tech Solutions, then submit the post URL. Your "
            "technical tasks unlock once a reviewer verifies it.</p>"
        ),
        body_text=[
            f"Your offer letter for {domain_title} has been generated. "
            f"Reference {offer_number}.",
            "",
            "Your first task: download the letter, post it on LinkedIn tagging KLS "
            "Tech Solutions, then submit the post URL. Your technical tasks unlock "
            "once a reviewer verifies it.",
        ],
        cta=("Download your offer letter", _academy("/dashboard/offer-letter")),
    )


def send_linkedin_reviewed(
    background, *, user_id, to: str, approved: bool, remarks: str
) -> Outbox:
    if approved:
        return queue_email(
            background,
            user_id=user_id,
            to=to,
            subject="LinkedIn task approved — your tasks are unlocked",
            template_name="linkedin_approved",
            heading="LinkedIn post verified",
            body_html=(
                "<p>Your post has been verified and <strong>all technical tasks are "
                "now unlocked</strong>.</p>"
                f"<p style='color:#0a1a2b;'>“{remarks}”</p>"
            ),
            body_text=[
                "Your post has been verified and all technical tasks are now unlocked.",
                "",
                f"Reviewer's note: {remarks}",
            ],
            cta=("Start your first task", _academy("/dashboard/tasks")),
        )

    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject="Your LinkedIn submission needs changes",
        template_name="linkedin_rejected",
        heading="Your LinkedIn post needs changes",
        body_html=(
            "<p>A reviewer looked at your post and needs something adjusted before "
            "your tasks can unlock.</p>"
            f"<p style='background:#fdf4e3;border-radius:10px;padding:14px 16px;"
            f"color:#0a1a2b;'>{remarks}</p>"
            "<p>Update your post and submit the URL again — there's no limit on "
            "resubmissions.</p>"
        ),
        body_text=[
            "A reviewer looked at your post and needs something adjusted before your "
            "tasks can unlock.",
            "",
            f"What to change: {remarks}",
            "",
            "Update your post and submit the URL again — there's no limit on resubmissions.",
        ],
        cta=("Resubmit your post", _academy("/dashboard/linkedin")),
    )


def send_task_reviewed(
    background, *, user_id, to: str, approved: bool, task_title: str, remarks: str,
    all_approved: bool = False,
) -> Outbox:
    if approved:
        extra = (
            "<p><strong>Every task is now approved.</strong> Your "
            "certificate has been issued and is ready to download.</p>"
            if all_approved
            else "<p>Move on to your next task when you're ready.</p>"
        )
        return queue_email(
            background,
            user_id=user_id,
            to=to,
            subject=f"Approved — {task_title}",
            template_name="task_approved",
            heading="Your submission was approved",
            body_html=(
                f"<p><strong>{task_title}</strong> has been approved.</p>"
                f"<p style='color:#0a1a2b;'>“{remarks}”</p>{extra}"
            ),
            body_text=[
                f"{task_title} has been approved.",
                "",
                f"Reviewer's note: {remarks}",
                "",
                "Every task is now approved. Your certificate has been issued."
                if all_approved
                else "Move on to your next task when you're ready.",
            ],
            cta=(
                ("Download your certificate", _academy("/dashboard/certificate"))
                if all_approved
                else ("Continue your tasks", _academy("/dashboard/tasks"))
            ),
        )

    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject=f"Changes requested — {task_title}",
        template_name="task_rejected",
        heading="Your submission needs changes",
        body_html=(
            f"<p>A reviewer read your submission for <strong>{task_title}</strong> "
            "and returned it with notes.</p>"
            f"<p style='background:#fdf4e3;border-radius:10px;padding:14px 16px;"
            f"color:#0a1a2b;'>{remarks}</p>"
            "<p>Make the changes and resubmit. Resubmitting is normal and there's "
            "no penalty for it.</p>"
        ),
        body_text=[
            f"A reviewer read your submission for {task_title} and returned it with notes.",
            "",
            f"What to change: {remarks}",
            "",
            "Make the changes and resubmit. Resubmitting is normal and there's no "
            "penalty for it.",
        ],
        cta=("Review the feedback", _academy("/dashboard/tasks")),
    )




def send_certificate_issued(
    background, *, user_id, to: str, full_name: str, certificate_number: str,
    domain_title: str,
) -> Outbox:
    first = full_name.split()[0]
    verify = _academy(f"/verify/{certificate_number}")
    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject=f"Your certificate is ready — {certificate_number}",
        template_name="certificate_issued",
        heading=f"Congratulations, {first}",
        body_html=(
            f"<p>You've completed the <strong>{domain_title}</strong> virtual "
            "internship. Your certificate has been issued.</p>"
            f"<p><strong>Certificate number:</strong> {certificate_number}</p>"
            "<p>It carries a QR code anyone can scan to verify it, and a public "
            f"verification page at <span style='color:#1387c8;'>{verify}</span></p>"
        ),
        body_text=[
            f"You've completed the {domain_title} virtual internship. Your certificate "
            "has been issued.",
            f"Certificate number: {certificate_number}",
            "",
            f"Verify it any time at {verify}",
        ],
        cta=("Download your certificate", _academy("/dashboard/certificate")),
    )


def send_task_assigned(
    background, *, user_id, to: str, task_title: str, domain_title: str
) -> Outbox:
    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject=f"A new task was added — {task_title}",
        template_name="task_assigned",
        heading="A new task has been added",
        body_html=(
            f"<p><strong>{task_title}</strong> has been added to your "
            f"{domain_title} internship.</p>"
        ),
        body_text=[f"{task_title} has been added to your {domain_title} internship."],
        cta=("View your tasks", _academy("/dashboard/tasks")),
    )


def send_admin_invite(
    background, *, user_id, to: str, full_name: str, invited_by: str, token: str,
    role: str,
) -> Outbox:
    role_label = "super administrator" if role == "super_admin" else "administrator"
    url = f"{settings.ADMIN_BASE_URL.rstrip('/')}/accept-invite?token={token}"

    return queue_email(
        background,
        user_id=user_id,
        to=to,
        subject="You've been invited to the KLS Academy admin console",
        template_name="admin_invite",
        heading=f"Hello {full_name.split()[0]}",
        body_html=(
            f"<p><strong>{invited_by}</strong> has invited you to join the KLS Academy "
            f"admin console as a {role_label}.</p>"
            "<p>Set your own password using the button below. This link expires in "
            "7 days and works once.</p>"
            "<p>If you weren't expecting this, ignore it — no account is active until "
            "the link is used.</p>"
        ),
        body_text=[
            f"{invited_by} has invited you to join the KLS Academy admin console as a "
            f"{role_label}.",
            "",
            "Set your own password using the link below. It expires in 7 days and "
            "works once.",
            "",
            "If you weren't expecting this, ignore it — no account is active until the "
            "link is used.",
        ],
        cta=("Set my password", url),
    )
