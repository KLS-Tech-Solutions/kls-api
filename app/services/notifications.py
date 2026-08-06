import uuid

from sqlalchemy.orm import Session

from app.models import ActivityLog, Notification, NotificationType


def notify(
    db: Session,
    user_id: uuid.UUID,
    title: str,
    message: str,
    type_: NotificationType,
    *,
    commit: bool = False,
) -> Notification:
    """In-app notification. Email delivery is Phase 8."""
    notification = Notification(
        user_id=user_id, title=title, message=message, type=type_
    )
    db.add(notification)
    if commit:
        db.commit()
    return notification


def log_activity(
    db: Session,
    user_id: uuid.UUID | None,
    activity: str,
    module: str,
    entity_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        ActivityLog(
            user_id=user_id,
            activity=activity,
            module=module,
            entity_id=entity_id,
            ip_address=ip_address,
        )
    )
