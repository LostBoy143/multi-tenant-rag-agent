import asyncio
import traceback
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session_factory
from app.auth.service import auth_service
from app.auth.schemas import LoginRequest

async def test_login():
    print("Testing login for: singhshubham620278@gmail.com")
    request = LoginRequest(
        email="singhshubham620278@gmail.com",
        password="AdminLogin123!"
    )
    
    async with async_session_factory() as db:
        try:
            result = await auth_service.login(db, request)
            print("Login success structure:", result.model_dump())
        except Exception as e:
            print("\n❌ Login Failed with Traceback:")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_login())
