from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentTenantDep, QdrantDep
from app.schemas.chat import QueryRequest, QueryResponse
from app.services.rag import LLMProviderError, answer_query

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/query")
async def query_documents(
    body: QueryRequest,
    organization: CurrentTenantDep,
    qdrant: QdrantDep,
) -> QueryResponse:
    """
    RAG Chat endpoint for authenticated organization users.
    Uses the specified agent's custom instructions and linked knowledge bases.
    """
    try:
        response, _ = await answer_query(
            qdrant=qdrant,
            organization_id=organization.id,
            agent_id=body.agent_id,
            question=body.question,
            top_k=body.top_k,
        )
    except LLMProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI provider is temporarily unavailable. Please try again shortly.",
        ) from e

    return response
