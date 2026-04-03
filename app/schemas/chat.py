import uuid
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    agent_id: uuid.UUID = Field(..., alias="agentId")
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)

    class Config:
        populate_by_name = True


class SourceChunk(BaseModel):
    filename: str
    chunk_index: int
    text_snippet: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
