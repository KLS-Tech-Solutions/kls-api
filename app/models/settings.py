import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import GUID, TimestampMixin, UUIDMixin


class PlatformSetting(Base, UUIDMixin, TimestampMixin):
    """
    Operational values a super admin can change without a deploy.

    A key/value table rather than a column per setting: adding a setting then
    costs a row, not a migration. Values are stored as text and parsed by the
    accessor that owns each key, so the parsing rule lives next to the meaning.

    `updated_by` and `updated_at` are kept because these are levers with money
    attached — knowing who moved the certificate fee, and when, matters.
    """

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
