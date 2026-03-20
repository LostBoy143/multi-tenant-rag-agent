from fastapi import APIRouter

from app.dependencies import CurrentTenantDep, QdrantDep
from app.schemas.chat import QueryRequest, QueryResponse
from app.services.rag import answer_query

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/query")
async def query_documents(
    body: QueryRequest,
    tenant: CurrentTenantDep,
    qdrant: QdrantDep,
) -> QueryResponse:
    return await answer_query(
        qdrant=qdrant,
        tenant_id=tenant.id,
        question=body.question,
        top_k=body.top_k,
    )
