import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import GUID, TimestampMixin, UUIDMixin
from app.models.enums import CertificateStatus, PaymentStatus


class Payment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "payments"

    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("enrollments.id", ondelete="SET NULL")
    )
    razorpay_order_id: Mapped[str | None] = mapped_column(String(100), index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(100), index=True)
    signature: Mapped[str | None] = mapped_column(String(255))
    # Stored in paise, matching Razorpay. ₹50 = 5000.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        default=PaymentStatus.CREATED,
        nullable=False,
        index=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(255))


class Certificate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "certificates"

    student_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("enrollments.id", ondelete="SET NULL")
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("payments.id", ondelete="SET NULL")
    )
    certificate_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    # Snapshot of the recipient's name at issue. The public verification page
    # reads this rather than the user row, so closing an account never
    # invalidates a credential that was earned and paid for.
    student_name: Mapped[str | None] = mapped_column(String(100))
    certificate_url: Mapped[str | None] = mapped_column(String(500))
    qr_code_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, name="certificate_status", native_enum=False),
        default=CertificateStatus.ISSUED,
        nullable=False,
    )
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(), nullable=False
    )


class CertificateVerificationLog(Base, UUIDMixin):
    """Every public verification attempt, for audit and abuse detection."""

    __tablename__ = "certificate_verification_logs"

    certificate_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("certificates.id", ondelete="CASCADE"), index=True
    )
    queried_number: Mapped[str] = mapped_column(String(50), nullable=False)
    found: Mapped[bool] = mapped_column(default=False, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(), nullable=False
    )
