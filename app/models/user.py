import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.dates import completed_years, today_in_ist
from app.models.base import GUID, TimestampMixin, UUIDMixin
from app.models.enums import UserRole, UserStatus


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        default=UserRole.STUDENT,
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", native_enum=False),
        default=UserStatus.PENDING,
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Nullable because accounts created before this column existed have no
    # value and there is no honest way to invent one. New registrations
    # require it — see `RegisterRequest`.
    date_of_birth: Mapped[date | None] = mapped_column(Date)

    # Bumped to invalidate every token this account has ever been issued.
    #
    # Access and refresh tokens are stateless: once signed, nothing can call
    # one back. A refresh token lives for 30 days, so without this a stolen
    # one survives the password reset performed *because* it was stolen. The
    # version is minted into every token and compared on every request, which
    # turns "revoke everything" into a single integer write.
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    admin_profile: Mapped["AdminProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def age(self) -> int | None:
        """
        Completed years, or None when the date of birth was never recorded.

        Computed rather than stored: an age column is wrong from the day after
        it is written. Judged on the Indian calendar — see `app.core.dates`.
        """
        if self.date_of_birth is None:
            return None
        return completed_years(self.date_of_birth, today_in_ist())

    @property
    def is_minor(self) -> bool:
        """
        Under 18, which is what the DPDP Act calls a child.

        Unknown ages return False. That is deliberate: this flag exists to
        trigger extra protection, and the accounts with no date of birth are
        pre-existing ones we have no basis to treat as children. Anyone
        registering now must supply a date, so the unknown set only shrinks.
        """
        age = self.age
        return age is not None and age < 18

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN


class StudentProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    college_name: Mapped[str | None] = mapped_column(String(150))
    degree: Mapped[str | None] = mapped_column(String(60))
    branch: Mapped[str | None] = mapped_column(String(80))
    year: Mapped[str | None] = mapped_column(String(20))
    linkedin_url: Mapped[str | None] = mapped_column(String(255))
    github_url: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="student_profile")


class AdminProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "admin_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    designation: Mapped[str | None] = mapped_column(String(100))
    permissions: Mapped[str | None] = mapped_column(String(500))

    user: Mapped[User] = relationship(back_populates="admin_profile")


class EmailToken(Base, UUIDMixin, TimestampMixin):
    """Single-use tokens for email verification and password reset."""

    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)  # verify_email | reset_password
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
