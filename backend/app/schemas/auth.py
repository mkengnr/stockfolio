import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class OtpRequestIn(BaseModel):
    email: EmailStr


class OtpRequestOut(BaseModel):
    message: str = "OTP sent"
    expires_in_minutes: int = 10


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str
    remember_me: bool = False


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    user: UserOut
    expires_at: datetime
