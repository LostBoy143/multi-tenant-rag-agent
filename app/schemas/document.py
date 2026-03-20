import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    status: str
    chunk_count: int
    error_message: str | None = None
    created_at: datetime


class UploadResponse(BaseModel):
    document: DocumentResponse
    message: str = "Document uploaded and processing started."
