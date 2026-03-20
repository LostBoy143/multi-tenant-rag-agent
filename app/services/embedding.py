import logging

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using Gemini's embedding model. Synchronous call."""
    client = _get_client()
    BATCH_LIMIT = 100
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_LIMIT):
        batch = texts[i : i + BATCH_LIMIT]
        result = client.models.embed_content(
            model=settings.embedding_model,
            contents=batch,
        )
        for emb in result.embeddings:
            all_embeddings.append(emb.values)

    return all_embeddings


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    client = _get_client()
    result = client.models.embed_content(
        model=settings.embedding_model,
        contents=text,
    )
    return result.embeddings[0].values
