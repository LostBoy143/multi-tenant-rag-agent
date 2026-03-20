import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.database import engine
from app.dependencies import get_qdrant
from app.routers import chat, documents, tenants

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RAG SaaS API...")
    qdrant = await get_qdrant()
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
    title="RAG SaaS API",
    description="Multi-tenant RAG service with document upload, vector search, and Gemini-powered answers.",
    version="0.1.0",
    lifespan=lifespan,
)

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
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tenants.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/api/v1/health", tags=["health"])
async def health_check():
    checks: dict[str, str] = {"status": "ok", "qdrant": "unknown", "database": "unknown"}

    try:
        qdrant = await get_qdrant()
        await qdrant.get_collections()
        checks["qdrant"] = "ok"
    except Exception:
        checks["qdrant"] = "unavailable"
        checks["status"] = "degraded"

    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        checks["status"] = "degraded"

    status_code = 200 if checks["status"] == "ok" else 503
    return Response(
        content=json.dumps(checks),
        status_code=status_code,
        media_type="application/json",
    )


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
