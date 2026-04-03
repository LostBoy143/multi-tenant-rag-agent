from fastapi import APIRouter
from app.auth.schemas import (
    Disable2FARequest,
    ForceResetRequest,
    LoginRequest,
    LoginResponse,
    TokenResponse,
    TwoFactorSetupResponse,
    TwoFactorValidateRequest,
    TwoFactorVerifyRequest,
    UserInToken,
)
from app.auth.service import auth_service
from app.dependencies import CurrentUserDep, DatabaseDep
from app.core.limiter import limiter
from fastapi import Request

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    payload: LoginRequest,
    db: DatabaseDep,
    request: Request,
):
    """
    Login with email and password.
    Returns tokens or a challenge if 2FA/password reset is required.
    """
    result = await auth_service.login(db, payload)
    return {"success": True, "data": result.model_dump(by_alias=True, mode="json")}

@router.post("/refresh")
async def refresh(
    refresh_token: str,
    db: DatabaseDep,
):
    """ Issue a new set of tokens using a valid refresh token. """
    result = await auth_service.refresh_tokens(db, refresh_token)
    return {"success": True, "data": result.model_dump(by_alias=True, mode="json")}

@router.get("/me")
async def get_me(user: CurrentUserDep):
    """Get current authenticated user info."""
    data = UserInToken(
        id=user.id,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id
    )
    return {"success": True, "data": data.model_dump(by_alias=True, mode="json")}

@router.post("/logout")
async def logout(refresh_token: str):
    await auth_service.logout(refresh_token)
    return {"message": "Logged out successfully"}

@router.post("/force-reset")
async def force_reset(
    payload: ForceResetRequest,
    db: DatabaseDep,
):
    """Force password reset on first login."""
    result = await auth_service.force_reset_with_temp_token(db, payload)
    return {"success": True, "data": result.model_dump(by_alias=True, mode="json")}

@router.post("/2fa/setup")
async def setup_2fa(
    user: CurrentUserDep,
):
    """Generate 2FA secret and QR code for scanning."""
    result = await auth_service.setup_2fa(user)
    return {"success": True, "data": result}

@router.post("/2fa/verify")
async def verify_2fa(
    request: TwoFactorVerifyRequest,
    db: DatabaseDep,
    user: CurrentUserDep,
):
    """Confirm 2FA setup with a code from the app."""
    await auth_service.verify_2fa_setup(db, user, request.code)
    return {"message": "2FA enabled successfully"}

@router.post("/2fa/validate")
@limiter.limit("5/minute")
async def validate_2fa(
    payload: TwoFactorValidateRequest,
    db: DatabaseDep,
    request: Request,
):
    """Complete login by validating a 2FA code."""
    result = await auth_service.validate_2fa_login(db, payload.temp_token, payload.code)
    return {"success": True, "data": result.model_dump(by_alias=True, mode="json")}

@router.post("/2fa/disable")
async def disable_2fa(
    request: Disable2FARequest,
    db: DatabaseDep,
    user: CurrentUserDep,
):
    """Disable 2FA for the current user."""
    await auth_service.disable_2fa(db, user, request.password)
    return {"message": "2FA disabled successfully"}
