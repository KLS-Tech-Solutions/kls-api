import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import UserRole, UserStatus
from app.schemas.common import ORMModel

PHONE_RE = re.compile(r"^(\+91)?[6-9]\d{9}$")


class UserOut(ORMModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    created_at: datetime


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str
    password: str = Field(min_length=8, max_length=72)

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
