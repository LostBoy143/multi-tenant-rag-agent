import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable
from uuid import uuid4

import sqlalchemy
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.router import router as auth_router
from app.config import settings
from app.core.init_db import init_superadmin
from app.core.limiter import limiter
from app.core.logging_config import setup_logging
from app.database import engine
from app.dependencies import close_qdrant, get_qdrant, get_redis_client
from app.routers import (
    admin,
    agents,
    analytics,
    api_keys,
    chat,
    conversations,
    documents,
    knowledge_base,
    leads,
    public,
    widgets,
)

setup_logging()
logger = logging.getLogger(__name__)

StartupAction = Callable[[], Awaitable[None]]


def _deployment_context() -> dict[str, Any]:
    """Non-secret deployment details that make Azure startup logs searchable."""
    return {
        "environment": settings.environment,
        "port": os.getenv("PORT"),
        "websites_port": os.getenv("WEBSITES_PORT"),
        "website_hostname": os.getenv("WEBSITE_HOSTNAME"),
        "website_instance_id": os.getenv("WEBSITE_INSTANCE_ID"),
        "startup_fail_fast": settings.startup_fail_fast,
    }


def _qdrant_target() -> str:
    if settings.qdrant_url:
        return "qdrant_url_configured"
    return f"{settings.qdrant_host}:{settings.qdrant_port}"


async def _reset_orphaned_documents() -> None:
    """Mark documents stuck in 'processing' as 'failed' after an interrupted worker."""
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
            logger.warning(
                "Reset orphaned PROCESSING documents to FAILED.",
                extra={"document_count": result.rowcount},
            )


async def _check_database() -> None:
    async with engine.connect() as conn:
        await conn.execute(sqlalchemy.text("SELECT 1"))


async def _check_qdrant() -> None:
    qdrant = await get_qdrant()
    await qdrant.get_collections()


async def _check_redis() -> None:
    redis_client = await get_redis_client()
    await redis_client.ping()


async def _initialize_database_defaults() -> None:
    await _check_database()
    await init_superadmin()
    await _reset_orphaned_documents()


async def _run_startup_action(
    name: str,
    action: StartupAction,
    startup_checks: dict[str, str],
    startup_errors: dict[str, str],
) -> None:
    """Run a startup action with bounded retries and noisy failure logging."""
    retries = max(settings.startup_check_retries, 1)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            await asyncio.wait_for(
                action(),
                timeout=settings.startup_check_timeout_seconds,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Startup dependency check failed.",
                extra={
                    "dependency": name,
                    "attempt": attempt,
                    "max_attempts": retries,
                    "timeout_seconds": settings.startup_check_timeout_seconds,
                    "error": str(exc),
                },
                exc_info=attempt == retries,
            )
            if attempt < retries:
                await asyncio.sleep(settings.startup_check_interval_seconds)
            continue

        startup_checks[name] = "ok"
        startup_errors.pop(name, None)
        logger.info(
            "Startup dependency check passed.",
            extra={"dependency": name, "attempt": attempt},
        )
        return

    startup_checks[name] = "unavailable"
    startup_errors[name] = str(last_error) if last_error else "unknown startup failure"
    logger.error(
        "Startup dependency unavailable after retries.",
        extra={"dependency": name, "error": startup_errors[name]},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_checks: dict[str, str] = {
        "database": "unknown",
        "qdrant": "unknown",
        "redis": "unknown",
    }
    startup_errors: dict[str, str] = {}
    app.state.startup_checks = startup_checks
    app.state.startup_errors = startup_errors

    logger.info("Starting RAG SaaS API.", extra=_deployment_context())
    logger.info(
        "External dependency targets configured.",
        extra={
            "database": "database_url_configured",
            "qdrant": _qdrant_target(),
            "redis": "redis_url_configured",
        },
    )

    await _run_startup_action(
        "database",
        _initialize_database_defaults,
        startup_checks,
        startup_errors,
    )
    await _run_startup_action("qdrant", _check_qdrant, startup_checks, startup_errors)
    await _run_startup_action("redis", _check_redis, startup_checks, startup_errors)

    failed = [name for name, state in startup_checks.items() if state != "ok"]
    if failed:
        logger.error(
            "API started with degraded dependencies.",
            extra={"failed_dependencies": failed, "startup_errors": startup_errors},
        )
        if settings.startup_fail_fast:
            raise RuntimeError(f"Startup checks failed: {', '.join(failed)}")
    else:
        logger.info("All startup dependency checks passed.")

    try:
        yield
    finally:
        logger.info("Shutting down RAG SaaS API.")
        await close_qdrant()
        redis_client = await get_redis_client()
        redis_close = getattr(redis_client, "aclose", None)
        if redis_close is not None:
            await redis_close()
        else:
            await redis_client.close()
        await engine.dispose()
        logger.info("Application resources closed.")


app = FastAPI(
    title="BolChat AI API",
    description="Secure Multi-tenant RAG service.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.environment == "development" else None,
    redoc_url="/api/redoc" if settings.environment == "development" else None,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        started_at = perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
            return response
        except Exception:
            logger.exception(
                "Unhandled request error.",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client": request.client.host if request.client else None,
                },
            )
            raise
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            status_code = response.status_code if response else 500
            if response is not None:
                response.headers["X-Request-ID"] = request_id
            logger.info(
                "HTTP request completed.",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client": request.client.host if request.client else None,
                },
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        csp = (
            "default-src 'self'; "
            "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 "
            "ws://localhost:8000 ws://127.0.0.1:8000; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
            "https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        return response


def _cors_allow_credentials() -> bool:
    if "*" in settings.cors_origins and settings.cors_allow_credentials:
        logger.warning(
            "CORS wildcard origin cannot be combined with credentialed browser requests. "
            "Credentials are disabled until CORS_ORIGINS is restricted to explicit origins.",
            extra={"cors_origins": settings.cors_origins},
        )
        return False
    return settings.cors_allow_credentials


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    logger.warning(
        "Rate limit exceeded.",
        extra={"path": request.url.path, "client": request.client.host if request.client else None},
    )
    return JSONResponse(
        content={"detail": "Rate limit exceeded. Please slow down."},
        status_code=429,
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=_cors_allow_credentials(),
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
app.include_router(leads.router)
app.include_router(public.router)


@app.get("/", include_in_schema=False)
async def root_liveness() -> dict[str, str]:
    """Lightweight endpoint for platform pings that only need the HTTP worker alive."""
    return {"status": "ok", "service": "bolchat-api"}


@app.get("/api/v1/health", tags=["health"])
async def health_check() -> Response:
    """Detailed health diagnostics for all core services."""
    checks: dict[str, Any] = {
        "status": "ok",
        "qdrant": "unknown",
        "database": "unknown",
        "redis": "unknown",
        "environment": settings.environment,
        "startup": getattr(app.state, "startup_checks", {}),
    }

    try:
        await _check_qdrant()
        checks["qdrant"] = "ok"
    except Exception as exc:
        logger.warning("Health check failed for Qdrant.", extra={"error": str(exc)}, exc_info=True)
        checks["qdrant"] = "unavailable"
        checks["status"] = "degraded"

    try:
        await _check_database()
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning(
            "Health check failed for database.",
            extra={"error": str(exc)},
            exc_info=True,
        )
        checks["database"] = "unavailable"
        checks["status"] = "degraded"

    try:
        await _check_redis()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.warning("Health check failed for Redis.", extra={"error": str(exc)}, exc_info=True)
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
