import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import UserRole, UserStatus
from app.schemas.common import ORMModel


class AdminOut(ORMModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AdminInviteRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    role: UserRole = UserRole.ADMIN


class AdminInviteResponse(BaseModel):
    admin: AdminOut
    # Always present. Even with email working a new sending domain often lands
    # in spam, so the inviter needs a link they can pass on directly.
    invite_url: str | None = None
    email_delivered: bool = False


class AdminUpdateRequest(BaseModel):
    role: UserRole | None = None
    status: UserStatus | None = None


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=72)


class InvitePreview(BaseModel):
    """Shown on the accept-invite screen before a password is chosen."""

    full_name: str
    email: str
    role: UserRole
