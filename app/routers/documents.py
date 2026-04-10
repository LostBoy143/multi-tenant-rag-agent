import logging
import uuid
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status, Query, Request
from app.core.limiter import limiter
from sqlalchemy import select

from app.config import settings
from app.dependencies import CurrentUserDep, DatabaseDep, QdrantDep
from app.models.document import Document, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.schemas.document import DocumentResponse, UploadResponse
from app.services.document_processor import ALLOWED_CONTENT_TYPES, extract_text
from app.services.chunker import recursive_chunk
from app.services.embedding import embed_texts
from app.services.vector_store import delete_document_chunks, upsert_chunks
from app.database import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def _process_document(
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    file_bytes: bytes,
    content_type: str,
    filename: str,
    qdrant_host: str,
    qdrant_port: int,
) -> None:
    """Background task: parse -> chunk -> embed -> store in Qdrant."""
    from qdrant_client import AsyncQdrantClient

    async with async_session_factory() as db:
        try:
            text = extract_text(file_bytes, content_type)
            chunks = recursive_chunk(
                text,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
            if not chunks:
                raise ValueError("No text chunks generated from document.")

            embeddings = embed_texts(chunks)

            qdrant = AsyncQdrantClient(host=qdrant_host, port=qdrant_port)
            await upsert_chunks(
                qdrant, organization_id, document_id, knowledge_base_id, chunks, embeddings, filename
            )
            await qdrant.close()

            result = await db.execute(select(Document).where(Document.id == document_id))
            doc = result.scalar_one()
            doc.status = DocumentStatus.READY
            doc.chunk_count = len(chunks)
            await db.commit()
            logger.info("Document %s processed: %d chunks", document_id, len(chunks))

        except Exception:
            logger.exception("Failed to process document %s", document_id)
            result = await db.execute(select(Document).where(Document.id == document_id))
            doc = result.scalar_one_or_none()
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.error_message = "Processing failed. Check server logs."
                await db.commit()


@router.post("/upload", status_code=202)
@limiter.limit("10/hour")
async def upload_document(
    request: Request,
    file: UploadFile,
    organization: CurrentUserDep,
    db: DatabaseDep,
    qdrant: QdrantDep,
    background_tasks: BackgroundTasks,
    kb_id: Annotated[uuid.UUID, Query(alias="kbId")]
) -> UploadResponse:
    # 1. Verify Knowledge Base belongs to Organization
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, 
            KnowledgeBase.organization_id == organization.organization_id
        )
    )
    if not kb_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Knowledge base not found or access denied")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {content_type}. Allowed: {list(ALLOWED_CONTENT_TYPES.keys())}",
        )

    file_bytes = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb}MB limit.",
        )

    doc_id = uuid.uuid4()
    document = Document(
        id=doc_id,
        organization_id=organization.organization_id,
        knowledge_base_id=kb_id,
        filename=file.filename or "untitled",
        file_type=ALLOWED_CONTENT_TYPES[content_type],
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    background_tasks.add_task(
        _process_document,
        document_id=doc_id,
        organization_id=organization.organization_id,
        knowledge_base_id=kb_id,
        file_bytes=file_bytes,
        content_type=content_type,
        filename=file.filename or "untitled",
        qdrant_host=settings.qdrant_host,
        qdrant_port=settings.qdrant_port,
    )

    return UploadResponse(
        document=DocumentResponse(
            id=document.id,
            filename=document.filename,
            file_type=document.file_type,
            status=document.status,
            chunk_count=document.chunk_count,
            error_message=document.error_message,
            created_at=document.created_at,
        )
    )


@router.get("")
@limiter.limit("60/minute")
async def list_documents(
    request: Request,
    organization: CurrentUserDep,
    db: DatabaseDep,
    kb_id: Annotated[uuid.UUID | None, Query(alias="kbId")] = None
):
    query = select(Document).where(Document.organization_id == organization.organization_id)
    if kb_id:
        query = query.where(Document.knowledge_base_id == kb_id)
        
    result = await db.execute(query.order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    data = [
        DocumentResponse(
            id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            status=d.status,
            chunk_count=d.chunk_count,
            error_message=d.error_message,
            created_at=d.created_at,
        )
        for d in docs
    ]
    return {"success": True, "data": data}


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    organization: CurrentUserDep,
    db: DatabaseDep,
    qdrant: QdrantDep,
) -> None:
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.organization_id == organization.organization_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    await delete_document_chunks(qdrant, organization.organization_id, document_id)
    await db.delete(doc)
    await db.commit()
