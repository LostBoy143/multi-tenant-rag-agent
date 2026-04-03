import asyncio
import uuid
from sqlalchemy import select
from app.database import async_session_factory
from app.models.user import User
from app.models.organization import Organization
from app.auth.service import auth_service
from app.config import settings

async def bootstrap():
    email = "singhshubham620278@gmail.com"
    password = "AdminLogin123!" # Temporary password
    system_org_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    
    print(f"Bootstrapping Superadmin: {email}")
    
    async with async_session_factory() as db:
        # 1. Ensure System Organization exists
        result = await db.execute(select(Organization).where(Organization.id == system_org_id))
        org = result.scalar_one_or_none()
        
        if not org:
            print("Creating System Organization...")
            org = Organization(
                id=system_org_id,
                name="System Organization",
                slug="system-org",
                plan="enterprise"
            )
            db.add(org)
            await db.flush()
        
        # 2. Handle Superadmin User
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if user:
            print("User exists. Updating role to superadmin and resetting password...")
            user.role = "superadmin"
            user.organization_id = system_org_id
            user.password_hash = auth_service.hash_password(password)
            user.must_change_password = True
        else:
            print("Creating new superadmin user...")
            user = User(
                email=email,
                password_hash=auth_service.hash_password(password),
                role="superadmin",
                organization_id=system_org_id,
                must_change_password=True
            )
            db.add(user)
        
        await db.commit()
        print("\n✅ Success!")
        print(f"Email: {email}")
        print(f"Password: {password}")
        print("Note: Use these credentials to log in to the dashboard.")

if __name__ == "__main__":
    asyncio.run(bootstrap())
