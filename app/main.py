import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.limiter import limiter
from app.core.logging_config import setup_logging
from app.database import engine
from app.dependencies import get_qdrant, get_redis_client
from app.auth.router import router as auth_router
from app.routers import admin, agents, analytics, api_keys, chat, conversations, documents, knowledge_base, public, widgets

# Configure structured logging
setup_logging()
logger = logging.getLogger(__name__)

from app.core.init_db import init_superadmin

# Start up application resources

async def _reset_orphaned_documents():
    """Mark documents stuck in 'processing' as 'failed' on startup.
    This handles the case where the server restarted mid-background-task."""
    from sqlalchemy import update
    from app.database import async_session_factory
    from app.models.document import Document, DocumentStatus

    async with async_session_factory() as db:
        result = await db.execute(
            update(Document)
            .where(Document.status == DocumentStatus.PROCESSING)
            .values(
                status=DocumentStatus.FAILED,
                error_message="Server restarted during processing. Please re-upload.",
            )
        )
        if result.rowcount > 0:
            await db.commit()
            logger.warning("Reset %d orphaned PROCESSING documents to FAILED.", result.rowcount)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RAG SaaS API...")
    
    # Run DB initializations (Superadmin)
    await init_superadmin()
    await _reset_orphaned_documents()
    
    qdrant = await get_qdrant()
    if settings.qdrant_url:
        logger.info("Qdrant client initialized (Cloud URL: %s)", settings.qdrant_url)
    else:
        logger.info(
            "Qdrant client initialized (host=%s, port=%s)",
            settings.qdrant_host,
            settings.qdrant_port,
        )
    yield
    logger.info("Shutting down RAG SaaS API...")
    if qdrant:
        await qdrant.close()


app = FastAPI(
    title="BolChat AI API",
    description="Secure Multi-tenant RAG service.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.environment == "development" else None,
    redoc_url="/api/redoc" if settings.environment == "development" else None,
)

# Custom Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # CSP allows CDN JS/CSS so Swagger Docs can load
        csp = (
            "default-src 'self'; "
            "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ws://localhost:8000 ws://127.0.0.1:8000; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    return Response(
        content='{"detail": "Rate limit exceeded. Please slow down."}',
        status_code=429,
        media_type="application/json",
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(agents.router)
app.include_router(widgets.router)
app.include_router(api_keys.router)
app.include_router(conversations.router)
app.include_router(knowledge_base.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(public.router)


@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Detailed health diagnostics for all core services."""
    checks: dict[str, str] = {
        "status": "ok", 
        "qdrant": "unknown", 
        "database": "unknown", 
        "redis": "unknown",
        "environment": settings.environment
    }

    # 1. Qdrant
    try:
        qdrant = await get_qdrant()
        await qdrant.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        logger.error("HealthCheck Qdrant Fail: %s", str(e))
        checks["qdrant"] = "unavailable"
        checks["status"] = "degraded"

    # 2. Database
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        logger.error("HealthCheck Database Fail: %s", str(e))
        checks["database"] = "unavailable"
        checks["status"] = "degraded"

    # 3. Redis
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.error("HealthCheck Redis Fail: %s", str(e))
        checks["redis"] = "unavailable"
        checks["status"] = "degraded"

    status_code = 200 if checks["status"] == "ok" else 503
    return Response(
        content=json.dumps(checks),
        status_code=status_code,
        media_type="application/json",
    )


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

