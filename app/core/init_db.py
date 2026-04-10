"""
Database Initialization & Superadmin Seeding
=============================================
Industry-standard startup hook that ensures:
1. All database tables exist (idempotent CREATE IF NOT EXISTS).
2. A "System" organization is always present for platform-level ownership.
3. A superadmin user is seeded from environment variables on first boot.
4. On subsequent boots, the superadmin email/password are synced with .env
   so that rotating credentials in the environment takes effect immediately.

This module is invoked once during FastAPI's lifespan startup event.
"""

import logging

from sqlalchemy import select

from app.auth.service import AuthService
from app.config import settings
from app.database import Base, async_session_factory, engine

# Import all models so Base.metadata knows about every table.
# Without these, create_all() would silently skip tables.
from app.models.agent import Agent  # noqa: F401
from app.models.conversation import Conversation, Message  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.organization import APIKey, Organization  # noqa: F401
from app.models.user import User

logger = logging.getLogger(__name__)
_auth = AuthService()


async def _ensure_schema() -> None:
    """Create any missing tables. Safe to call repeatedly (uses IF NOT EXISTS)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema verified.")


async def _ensure_system_org(db) -> Organization:
    """Return the 'System' organization, creating it on first run."""
    result = await db.execute(
        select(Organization).where(Organization.slug == "system")
    )
    org = result.scalar_one_or_none()

    if org is None:
        org = Organization(name="BolChat Platform", slug="system", plan="enterprise")
        db.add(org)
        await db.flush()
        logger.info("Created platform organization: BolChat Platform (slug=system)")

    return org


async def _ensure_superadmin(db, org: Organization) -> None:
    """
    Seed or sync the superadmin user.

    Behavior:
    - First boot  → creates user with email & hashed password from .env
    - Later boots → if .env email changed, updates the existing superadmin record
                     if .env password changed, re-hashes and updates
    - Always ensures role='superadmin' and is_active=True
    """
    # Look up by role first (there should be exactly one superadmin)
    result = await db.execute(
        select(User).where(User.role == "superadmin")
    )
    admin = result.scalar_one_or_none()

    target_email = settings.superadmin_email
    target_hash = _auth.hash_password(settings.superadmin_password)

    if admin is None:
        # --- First boot: create from scratch ---
        admin = User(
            email=target_email,
            password_hash=target_hash,
            organization_id=org.id,
            role="superadmin",
            must_change_password=False,
            is_active=True,
        )
        db.add(admin)
        logger.info("Superadmin created: %s", target_email)
    else:
        # --- Subsequent boots: sync with .env ---
        changed = False

        if admin.email != target_email:
            logger.info(
                "Superadmin email rotated: %s → %s", admin.email, target_email
            )
            admin.email = target_email
            changed = True

        if not _auth.verify_password(settings.superadmin_password, admin.password_hash):
            admin.password_hash = target_hash
            logger.info("Superadmin password synced from environment.")
            changed = True

        if not admin.is_active:
            admin.is_active = True
            changed = True

        if admin.organization_id != org.id:
            admin.organization_id = org.id
            changed = True

        if changed:
            logger.info("Superadmin record updated.")
        else:
            logger.info("Superadmin verified: %s (no changes needed)", admin.email)


async def init_superadmin() -> None:
    """Top-level entrypoint called from FastAPI lifespan."""
    await _ensure_schema()

    async with async_session_factory() as db:
        try:
            org = await _ensure_system_org(db)
            await _ensure_superadmin(db, org)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Failed to initialize database defaults.")
            raise
