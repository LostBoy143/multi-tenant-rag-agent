# Production Optimization Guide

This guide covers how to take the RAG SaaS API from a working prototype to a production-grade AI service that handles real traffic, scales efficiently, and stays reliable.

---

## 1. Embedding & Vector Search Optimization

### Use Quantization

Qdrant supports scalar and binary quantization to reduce memory usage and speed up search.

```python
from qdrant_client import models

await client.create_collection(
    collection_name=name,
    vectors_config=models.VectorParams(
        size=3072,
        distance=models.Distance.COSINE,
    ),
    quantization_config=models.ScalarQuantization(
        scalar=models.ScalarQuantizationConfig(
            type=models.ScalarType.INT8,
            always_ram=True,
        ),
    ),
)
```

INT8 quantization cuts memory usage by ~4x with minimal accuracy loss. For even more compression, binary quantization reduces memory by ~32x but requires oversampling during search.

### Tune HNSW Parameters

For larger collections, optimize the HNSW index:

```python
await client.update_collection(
    collection_name=name,
    hnsw_config=models.HnswConfigDiff(
        m=32,               # connections per node (default 16)
        ef_construct=200,   # build-time accuracy (default 100)
    ),
)
```

Higher `m` and `ef_construct` improve recall at the cost of indexing speed and memory. Tune based on your accuracy vs. latency requirements.

### Cache Frequent Queries

Add a short-lived cache (TTL 5-10 minutes) for embedding results:

```python
from functools import lru_cache
from cachetools import TTLCache

query_embedding_cache = TTLCache(maxsize=1000, ttl=300)

def embed_query_cached(text: str) -> list[float]:
    if text in query_embedding_cache:
        return query_embedding_cache[text]
    result = embed_query(text)
    query_embedding_cache[text] = result
    return result
```

This avoids re-embedding identical questions (common in chatbot scenarios where users rephrase slightly).

---

## 2. LLM Call Optimization

### Streaming Responses

Replace the current synchronous LLM call with streaming to reduce time-to-first-token:

```python
from fastapi.responses import StreamingResponse

async def stream_answer(question: str, context: str):
    client = _get_llm_client()
    response = client.models.generate_content_stream(
        model=settings.llm_model,
        contents=f"{context}\n\nUSER QUESTION: {question}",
        config=GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.4,
            max_output_tokens=1024,
        ),
    )
    for chunk in response:
        if chunk.text:
            yield chunk.text
```

This sends tokens to the client as they're generated instead of waiting for the full response. Users perceive this as much faster.

### Response Caching with Semantic Similarity

For repeated or near-identical questions, cache LLM responses keyed by the question's embedding vector:

1. Embed the incoming question.
2. Search a "cache collection" in Qdrant for vectors with similarity > 0.95.
3. If found, return the cached answer directly (skip LLM call).
4. If not found, generate the answer, then store both the question vector and answer in the cache collection.

This can dramatically reduce Gemini API costs for chatbots with repetitive queries.

### Prompt Optimization

- Keep the system instruction concise. Shorter prompts = faster inference and lower cost.
- Set `max_output_tokens` appropriately. For short Q&A, 512 tokens is usually enough. The current 1024 is a reasonable upper bound.
- `temperature=0.4` balances factual grounding with natural language. Lower (0.1-0.2) for purely factual domains; higher (0.6-0.7) for creative use cases.

---

## 3. Document Processing Pipeline

### Move to a Task Queue

The current implementation uses FastAPI `BackgroundTasks`, which runs in the same process. For production:

**Use Celery + Redis** or **ARQ (async Redis queue)**:

```
Client -> FastAPI -> enqueue job -> Redis
                                      |
                              Worker pool (N workers)
                                      |
                              parse -> chunk -> embed -> store
```

Benefits:
- Workers can run on separate machines with more CPU/memory.
- Failed jobs can be retried automatically.
- Job progress can be tracked.
- The API server's resources aren't consumed by processing.

ARQ is recommended for this stack since it's async-native:

```python
# worker.py
from arq import create_pool
from arq.connections import RedisSettings

async def process_document(ctx, document_id, tenant_id, file_bytes, content_type, filename):
    # ... same processing logic ...
    pass

class WorkerSettings:
    functions = [process_document]
    redis_settings = RedisSettings(host="redis")
```

### Parallel Embedding

Currently, chunks are embedded in sequential batches of 100. For large documents, parallelize:

```python
import asyncio

async def embed_texts_parallel(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    batches = [texts[i:i+batch_size] for i in range(0, len(texts), batch_size)]
    tasks = [asyncio.to_thread(embed_batch, batch) for batch in batches]
    results = await asyncio.gather(*tasks)
    return [emb for batch_result in results for emb in batch_result]
```

### Support More Formats

Extend the document processor for production use cases:

| Format | Library |
|---|---|
| HTML | `beautifulsoup4` |
| Markdown | `markdown` -> strip tags |
| CSV/Excel | `pandas` -> row-per-chunk |
| Images (OCR) | `pytesseract` or Google Document AI |
| PowerPoint | `python-pptx` |

### Smarter Chunking

Replace the character-based splitter with a semantic chunker for better retrieval:

1. **Sentence-level splitting** first (using `spacy` or `nltk`).
2. **Group sentences** by semantic similarity into coherent paragraphs.
3. This produces chunks that map to actual topics rather than arbitrary character boundaries.

Alternatively, use an overlapping sliding window at the token level (not character level) to align with how the embedding model processes text.

---

## 4. Database Optimization

### Connection Pooling

Configure SQLAlchemy's pool for production load:

```python
engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    echo=False,
)
```

For high-concurrency deployments, add **PgBouncer** as an external connection pooler between the API and PostgreSQL.

### Add Indexes

The current schema has basic indexes. Add these for production query patterns:

```sql
CREATE INDEX idx_documents_tenant_status ON documents (tenant_id, status);
CREATE INDEX idx_api_keys_prefix_active ON api_keys (prefix) WHERE is_active = true;
```

The partial index on `api_keys` speeds up authentication lookups by only indexing active keys.

### Read Replicas

For read-heavy workloads (listing documents, tenant info), route reads to PostgreSQL replicas:

```python
read_engine = create_async_engine(settings.database_read_url, echo=False)
write_engine = create_async_engine(settings.database_url, echo=False)
```

---

## 5. API Performance

### Add Response Compression

Enable gzip/brotli for API responses:

```python
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=500)
```

This reduces bandwidth for large query responses.

### Connection Keep-Alive

Uvicorn supports HTTP keep-alive by default. Ensure your reverse proxy (NGINX) preserves it:

```nginx
upstream api {
    server 127.0.0.1:8000;
    keepalive 32;
}
```

### Run Multiple Workers

Scale uvicorn with multiple workers:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Rule of thumb: `workers = 2 * CPU_CORES + 1`. Each worker runs its own event loop and can handle thousands of concurrent async requests.

For even better performance, use Gunicorn as the process manager:

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 6. Observability

### Structured Logging

Replace basic logging with structured JSON output:

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()
logger.info("document_processed", document_id=str(doc_id), chunks=len(chunks), tenant_id=str(tenant_id))
```

JSON logs are parseable by CloudWatch, Datadog, ELK, and every modern log aggregation system.

### Metrics with Prometheus

Add `prometheus-fastapi-instrumentator`:

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

This exposes `/metrics` with request count, latency histograms, and error rates. Scrape with Prometheus and visualize in Grafana.

Custom metrics to track:
- `rag_query_duration_seconds` -- total time for a RAG query (embed + search + LLM).
- `embedding_batch_size` -- number of chunks per embedding call.
- `llm_tokens_generated` -- output tokens per LLM call.
- `document_processing_duration_seconds` -- time to process each document.

### Distributed Tracing

Add OpenTelemetry for end-to-end request tracing:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

FastAPIInstrumentor.instrument_app(app)
```

This traces requests across the API, database, and external calls (Gemini, Qdrant), helping identify bottlenecks.

---

## 7. Security Hardening

### API Key Rotation

Add an endpoint to rotate API keys without downtime:

1. Generate a new key.
2. Mark both old and new keys as active.
3. Client switches to the new key.
4. Deactivate the old key.

### Input Sanitization

- Validate and sanitize all query inputs to prevent prompt injection.
- Add a content filter on LLM outputs to catch inappropriate content.
- Limit query length (already at 2000 characters) and rate limit per tenant.

### Network Security

- Qdrant should not be exposed to the public internet. Use private networking (VPC peering, private endpoints).
- PostgreSQL should only accept connections from the API server's IP/subnet.
- Enable TLS on all inter-service communication.

### Audit Logging

Log every API key usage, document upload, and query for compliance:

```python
logger.info("api_call", tenant_id=str(tenant.id), endpoint=request.url.path, method=request.method)
```

---

## 8. Scaling Architecture

### Horizontal Scaling

```
                    Load Balancer (ALB / NGINX)
                    ┌────────┼────────┐
                    ▼        ▼        ▼
                 API-1    API-2    API-3
                    │        │        │
                    └────────┼────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         PostgreSQL     Qdrant Cluster    Redis
         (Primary +     (3 nodes,       (rate limits,
          Replica)       sharded)        job queue,
                                         cache)
```

- **API tier**: Stateless -- add instances behind a load balancer.
- **PostgreSQL**: Vertical scaling + read replicas. Managed services handle failover.
- **Qdrant**: Supports clustering with sharding and replication for horizontal scaling.
- **Redis**: Used for rate limiting (shared state across API instances), job queues, and response caching.

### When to Scale What

| Signal | Action |
|---|---|
| API latency > 500ms P95 | Add more API workers/instances |
| Database connection pool exhausted | Add PgBouncer or increase pool size |
| Qdrant search latency > 200ms | Enable quantization, add nodes, tune HNSW |
| Document queue growing | Add more worker processes |
| Gemini API rate limited | Add request queuing with backoff, or upgrade API tier |
| Memory pressure on Qdrant | Enable disk-based storage or quantization |

---

## 9. Cost Optimization

### Gemini API Costs

- **Batch embedding calls** (already done): reduces per-request overhead.
- **Cache embeddings** for repeated queries.
- **Cache LLM responses** for common questions (semantic cache).
- **Use `gemini-2.0-flash`** (already done): cheapest model with good quality.
- Monitor token usage and set budget alerts in Google Cloud Console.

### Infrastructure Costs

- Use **spot/preemptible instances** for document processing workers (they're stateless and restartable).
- **Right-size** Qdrant nodes based on actual vector count, not projected peaks.
- **Auto-scale** API instances based on request rate (Kubernetes HPA or cloud auto-scaling).
- Use **reserved instances** for always-on components (database, API baseline).

### Qdrant Storage

- Enable **on-disk storage** with mmap for large collections:
  ```python
  optimizers_config=models.OptimizersConfigDiff(memmap_threshold=10000)
  ```
- Use quantization to reduce per-vector memory from ~12KB (3072 * float32) to ~3KB (INT8) or ~0.4KB (binary).

---

## 10. Production Readiness Checklist

**Performance**:
- [ ] Streaming LLM responses enabled
- [ ] Query embedding cache in place
- [ ] Qdrant quantization configured
- [ ] Multiple uvicorn workers running
- [ ] GZip middleware enabled

**Reliability**:
- [ ] Document processing moved to task queue (Celery/ARQ)
- [ ] Health check monitored by load balancer
- [ ] Database connection pooling tuned
- [ ] Retry logic on Gemini API calls (transient failures)
- [ ] Circuit breaker on external dependencies

**Observability**:
- [ ] Structured JSON logging
- [ ] Prometheus metrics exposed
- [ ] Dashboards for latency, error rate, throughput
- [ ] Alerts on P95 latency, error rate, health check failures
- [ ] Distributed tracing with OpenTelemetry

**Security**:
- [ ] API key rotation endpoint
- [ ] Qdrant behind private network
- [ ] TLS on all endpoints
- [ ] Audit logging enabled
- [ ] Prompt injection defenses

**Scaling**:
- [ ] Stateless API behind load balancer
- [ ] Redis for shared rate limiting and caching
- [ ] Database read replicas for read-heavy queries
- [ ] Auto-scaling configured
- [ ] Cost monitoring and budget alerts
