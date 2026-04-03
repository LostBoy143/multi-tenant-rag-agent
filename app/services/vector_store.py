import uuid
import logging

from qdrant_client import AsyncQdrantClient, models

from app.config import settings

logger = logging.getLogger(__name__)


def _collection_name(organization_id: uuid.UUID) -> str:
    return f"org_{organization_id.hex}"


async def create_organization_collection(client: AsyncQdrantClient, organization_id: uuid.UUID) -> None:
    name = _collection_name(organization_id)
    exists = await client.collection_exists(name)
    if exists:
        logger.info("Collection %s already exists, skipping creation.", name)
        return
    await client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(
            size=settings.embedding_dimensions,
            distance=models.Distance.COSINE,
        ),
    )
    logger.info("Created Qdrant collection: %s", name)


async def delete_organization_collection(client: AsyncQdrantClient, organization_id: uuid.UUID) -> None:
    name = _collection_name(organization_id)
    exists = await client.collection_exists(name)
    if exists:
        await client.delete_collection(name)
        logger.info("Deleted Qdrant collection: %s", name)


async def upsert_chunks(
    client: AsyncQdrantClient,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    chunks: list[str],
    embeddings: list[list[float]],
    filename: str,
) -> None:
    name = _collection_name(organization_id)
    points = [
        models.PointStruct(
            id=uuid.uuid4().hex,
            vector=emb,
            payload={
                "document_id": str(document_id),
                "knowledge_base_id": str(knowledge_base_id),
                "chunk_index": idx,
                "text": chunk,
                "filename": filename,
            },
        )
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    BATCH = 100
    for i in range(0, len(points), BATCH):
        await client.upsert(collection_name=name, points=points[i : i + BATCH])

    logger.info("Upserted %d chunks for doc %s in %s", len(points), document_id, name)


async def search_chunks(
    client: AsyncQdrantClient,
    organization_id: uuid.UUID,
    query_vector: list[float],
    knowledge_base_ids: list[uuid.UUID] | None = None,
    top_k: int = 5,
    score_threshold: float | None = None,
) -> list[models.ScoredPoint]:
    name = _collection_name(organization_id)
    
    filter_obj = None
    if knowledge_base_ids:
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="knowledge_base_id",
                    match=models.MatchAny(any=[str(kb_id) for kb_id in knowledge_base_ids]),
                )
            ]
        )
        
    results = await client.query_points(
        collection_name=name,
        query=query_vector,
        query_filter=filter_obj,
        limit=top_k,
        score_threshold=score_threshold or settings.rag_score_threshold,
    )
    return results.points


async def delete_document_chunks(
    client: AsyncQdrantClient,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    name = _collection_name(organization_id)
    await client.delete(
        collection_name=name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    )
                ]
            )
        ),
    )
    logger.info("Deleted chunks for doc %s from %s", document_id, name)
