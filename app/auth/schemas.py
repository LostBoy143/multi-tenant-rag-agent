from pydantic import BaseModel, EmailStr, Field
from typing import Any
from uuid import UUID


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterUserRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: UUID
    role: str = "member"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., alias="currentPassword")
    new_password: str = Field(..., min_length=8, alias="newPassword")

    class Config:
        populate_by_name = True


class ForceResetRequest(BaseModel):
    temp_token: str = Field(..., alias="tempToken")
    new_password: str = Field(..., min_length=8, alias="newPassword")

    class Config:
        populate_by_name = True


class UserInToken(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    organization_id: UUID = Field(..., alias="orgId")

    class Config:
        populate_by_name = True


class TokenResponse(BaseModel):
    access_token: str = Field(..., alias="accessToken")
    refresh_token: str = Field(..., alias="refreshToken")
    user: UserInToken

    class Config:
        populate_by_name = True


class LoginResponse(BaseModel):
    # This matches the Node API's tiered response for 2FA/Password change
    success: bool = True
    require_password_change: bool = Field(False, alias="requirePasswordChange")
    require_2fa: bool = Field(False, alias="require2FA")
    temp_token: str | None = Field(None, alias="tempToken")
    access_token: str | None = Field(None, alias="accessToken")
    refresh_token: str | None = Field(None, alias="refreshToken")
    user: UserInToken | None = None

    class Config:
        populate_by_name = True


class TwoFactorSetupResponse(BaseModel):
    secret: str
    qr_code: str = Field(..., alias="qrCode")

    class Config:
        populate_by_name = True


class TwoFactorVerifyRequest(BaseModel):
    code: str


class TwoFactorValidateRequest(BaseModel):
    temp_token: str = Field(..., alias="tempToken")
    code: str

    class Config:
        populate_by_name = True


class Disable2FARequest(BaseModel):
    password: str
