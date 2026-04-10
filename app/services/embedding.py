import logging

from fastembed import TextEmbedding

from app.config import settings

logger = logging.getLogger(__name__)

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    """Lazy-load the embedding model (singleton). First call downloads the model
    if it's not already cached (~50MB for bge-small-en-v1.5)."""
    global _model
    if _model is None:
        logger.info("Loading local embedding model: %s", settings.embedding_model)
        _model = TextEmbedding(model_name=settings.embedding_model)
        logger.info("Embedding model loaded successfully.")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using the local ONNX model. Synchronous call."""
    model = _get_model()
    embeddings = list(model.embed(texts))
    return [emb.tolist() for emb in embeddings]


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    model = _get_model()
    embeddings = list(model.query_embed(text))
    return embeddings[0].tolist()
