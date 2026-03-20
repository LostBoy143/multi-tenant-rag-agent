from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SourceChunk(BaseModel):
    filename: str
    chunk_index: int
    text_snippet: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
