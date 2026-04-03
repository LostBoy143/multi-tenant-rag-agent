import io
import json
import base64
from datetime import timedelta
from typing import Any
from uuid import UUID

import bcrypt
import pyotp
import qrcode
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import sign_access_token, sign_refresh_token, verify_token
from app.auth.schemas import LoginRequest, LoginResponse, TokenResponse, UserInToken, ForceResetRequest
from app.core.redis import redis_client
from app.models.user import User

# Configuration for temp tokens
TEMP_TOKEN_TTL = 300  # 5 minutes
REFRESH_TOKEN_TTL = 7 * 24 * 60 * 60 # 7 days


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed_password.encode())

    async def login(self, db: AsyncSession, request: LoginRequest) -> LoginResponse:
        result = await db.execute(select(User).where(User.email == request.email))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not self.verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # 1. Check if password change is forced
        if user.must_change_password:
            temp_token = self._generate_temp_token()
            await redis_client.set(
                f"pwd_change:{temp_token}",
                json.dumps({"user_id": str(user.id), "org_id": str(user.organization_id)}),
                ex=TEMP_TOKEN_TTL
            )
            return LoginResponse(
                success=True,
                require_password_change=True,
                temp_token=temp_token,
                user=UserInToken(
                    id=user.id,
                    email=user.email,
                    role=user.role,
                    orgId=user.organization_id
                )
            )

        # 2. Check if 2FA is required
        if user.two_factor_enabled:
            temp_token = self._generate_temp_token()
            await redis_client.set(
                f"2fa:{temp_token}",
                json.dumps({
                    "user_id": str(user.id), 
                    "org_id": str(user.organization_id),
                    "role": user.role
                }),
                ex=TEMP_TOKEN_TTL
            )
            return LoginResponse(
                success=True,
                require_2fa=True,
                temp_token=temp_token
            )

        # 3. Standard Login
        tokens = await self.issue_tokens(user.id, user.organization_id, user.role, user.email)
        return LoginResponse(
            success=True,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            user=tokens.user
        )

    async def issue_tokens(self, user_id: UUID, org_id: UUID, role: str, email: str) -> TokenResponse:
        import uuid
        token_id = str(uuid.uuid4())
        
        access_token = sign_access_token({
            "sub": str(user_id), 
            "org_id": str(org_id), 
            "role": role,
            "email": email
        })
        refresh_token = sign_refresh_token({"sub": str(user_id), "jti": token_id})
        
        # Store refresh token in Redis
        await redis_client.set(f"refresh:{token_id}", str(user_id), ex=REFRESH_TOKEN_TTL)
        
        return TokenResponse(
            accessToken=access_token,
            refreshToken=refresh_token,
            user=UserInToken(id=user_id, email=email, role=role, orgId=org_id)
        )

    async def logout(self, refresh_token: str):
        try:
            payload = verify_token(refresh_token)
            if payload.get("type") == "refresh" and "jti" in payload:
                await redis_client.delete(f"refresh:{payload['jti']}")
        except Exception:
            pass

    async def refresh_tokens(self, db: AsyncSession, refresh_token: str) -> TokenResponse:
        payload = verify_token(refresh_token)
        if payload.get("type") != "refresh" or "jti" not in payload:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        token_id = payload["jti"]
        user_id_str = await redis_client.get(f"refresh:{token_id}")
        
        if not user_id_str:
            raise HTTPException(status_code=401, detail="Refresh token expired or revoked")
            
        # Revoke old token
        await redis_client.delete(f"refresh:{token_id}")
        
        user_id = UUID(user_id_str.decode())
        
        # Verify user still exists and is active
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")
            
        return await self.issue_tokens(user.id, user.organization_id, user.role, user.email)

    async def force_reset_with_temp_token(self, db: AsyncSession, request: ForceResetRequest) -> TokenResponse:
        key = f"pwd_change:{request.temp_token}"
        data_str = await redis_client.get(key)
        
        if not data_str:
            raise HTTPException(status_code=400, detail="Invalid or expired temp token")
            
        data = json.loads(data_str.decode())
        user_id = UUID(data["user_id"])
        
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Update user
        user.password_hash = self.hash_password(request.new_password)
        user.must_change_password = False
        
        await db.commit()
        await redis_client.delete(key)
        
        return await self.issue_tokens(user.id, user.organization_id, user.role, user.email)

    async def setup_2fa(self, user: User) -> dict[str, str]:
        """Generate a new TOTP secret and QR code for the user."""
        if user.two_factor_enabled:
            raise HTTPException(status_code=400, detail="2FA is already enabled")
            
        # We store the potential secret in Redis temporarily until they verify it
        secret = pyotp.random_base32()
        await redis_client.set(f"2fa_secret:{user.id}", secret, ex=TEMP_TOKEN_TTL)
        
        provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="BolChat AI"
        )
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        return {
            "secret": secret,
            "qrCode": f"data:image/png;base64,{qr_base64}"
        }

    async def verify_2fa_setup(self, db: AsyncSession, user: User, code: str) -> bool:
        """Confirm the code and enable 2FA for the user."""
        secret = await redis_client.get(f"2fa_secret:{user.id}")
        if not secret:
            raise HTTPException(status_code=400, detail="2FA setup session expired. Please start over.")
            
        totp = pyotp.TOTP(secret.decode())
        if not totp.verify(code):
            raise HTTPException(status_code=400, detail="Invalid verification code")
            
        user.two_factor_enabled = True
        user.two_factor_secret = secret.decode()
        await db.commit()
        
        await redis_client.delete(f"2fa_secret:{user.id}")
        return True

    async def validate_2fa_login(self, db: AsyncSession, temp_token: str, code: str) -> TokenResponse:
        """Validate 2FA code during the login flow using a temp token."""
        key = f"2fa:{temp_token}"
        data_str = await redis_client.get(key)
        
        if not data_str:
            raise HTTPException(status_code=400, detail="Invalid or expired 2FA session")
            
        data = json.loads(data_str.decode())
        user_id = UUID(data["user_id"])
        
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(status_code=404, detail="User not found")
            
        if not user.two_factor_secret:
            raise HTTPException(status_code=400, detail="2FA not configured for this user")
            
        totp = pyotp.TOTP(user.two_factor_secret)
        if not totp.verify(code):
            raise HTTPException(status_code=400, detail="Invalid 2FA code")
            
        # Revoke temp token
        await redis_client.delete(key)
        
        return await self.issue_tokens(user.id, user.organization_id, user.role, user.email)

    async def disable_2fa(self, db: AsyncSession, user: User, password: str) -> bool:
        """Disable 2FA for the user after verifying their password."""
        if not self.verify_password(password, user.password_hash):
            raise HTTPException(status_code=400, detail="Invalid password")
            
        user.two_factor_enabled = False
        user.two_factor_secret = None
        await db.commit()
        return True

    def _generate_temp_token(self) -> str:
        import secrets
        return secrets.token_urlsafe(32)


auth_service = AuthService()
