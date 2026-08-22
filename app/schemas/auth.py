import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings
from app.core.dates import completed_years, today_in_ist
from app.models import UserRole, UserStatus
from app.schemas.common import ORMModel

PHONE_RE = re.compile(r"^(\+91)?[6-9]\d{9}$")

# Nobody alive was born before this. It exists to catch a mistyped year —
# 1025 for 2025 — rather than to make a claim about human longevity.
EARLIEST_BIRTH_YEAR = 1900


class UserOut(ORMModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    date_of_birth: date | None = None
    created_at: datetime


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str
    password: str = Field(min_length=8, max_length=72)
    date_of_birth: date

    @field_validator("date_of_birth")
    @classmethod
    def old_enough(cls, value: date) -> date:
        """
        Three separate failures, three separate messages.

        A future date and a 1025 typo are mistakes — say so, so the person
        fixes the field. Being under age is not a mistake, and telling someone
        "invalid date" when the real answer is "you are too young" wastes their
        afternoon on a form that will never accept them.
        """
        today = today_in_ist()
        if value > today:
            raise ValueError("Date of birth cannot be in the future")
        if value.year < EARLIEST_BIRTH_YEAR:
            raise ValueError("Enter a valid date of birth")

        if completed_years(value, today) < settings.MINIMUM_AGE:
            raise ValueError(
                f"You must be at least {settings.MINIMUM_AGE} to register. "
                "Indian data protection law requires verifiable parental "
                "consent for under-18s, which we are not yet set up to collect."
            )
        return value

    @field_validator("phone")
    @classmethod
    def valid_indian_mobile(cls, value: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", value)
        if not PHONE_RE.match(cleaned):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return cleaned

    @field_validator("password")
    @classmethod
    def strong_enough(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one number")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class LogoutRequest(BaseModel):
    all_devices: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=72)


class VerifyEmailRequest(BaseModel):
    token: str


class DeleteAccountRequest(BaseModel):
    """
    Closing an account is irreversible, so it is re-authenticated rather than
    trusting whatever session happens to be open on the device.
    """

    password: str = Field(min_length=1)
