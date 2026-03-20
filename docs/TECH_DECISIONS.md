# Tech Stack & Decisions

Every technology choice in this project was made with a specific rationale. This document explains what was chosen, why, and what the alternatives were.

---

## 1. Backend Framework: FastAPI

**Choice**: FastAPI 0.100+

**Why**:
- Native async support -- critical for I/O-heavy workloads (database queries, vector DB calls, external API calls to Gemini).
- Automatic OpenAPI/Swagger documentation with zero extra effort.
- Pydantic V2 integration for fast, type-safe request validation.
- Dependency injection system that cleanly handles DB sessions, auth, and service clients.
- Excellent performance benchmarks among Python frameworks.

**Alternatives considered**:

| Framework | Why not |
|---|---|
| **Django + DRF** | Heavier, synchronous by default. Async support exists but is bolted on. ORM is sync-only without workarounds. Overkill for an API-only service. |
| **Flask** | No built-in async. No automatic validation or docs. Would need many extensions to match FastAPI's built-in features. |
| **Litestar** | Strong contender with similar async-first design. Smaller ecosystem and community compared to FastAPI. |
| **Go (Gin/Echo)** | Better raw performance but loses Python's ML/AI library ecosystem. Embedding and LLM SDKs are Python-first. |
| **Node.js (Express/Fastify)** | Viable but Python is the lingua franca for AI/ML services. Google's GenAI SDK is Python-first. |

---

## 2. Vector Database: Qdrant

**Choice**: Qdrant (open-source, Apache 2.0)

**Why**:
- Fully open-source with no vendor lock-in.
- Native async Python client (`qdrant-client` with `AsyncQdrantClient`).
- Supports collection-level isolation -- each tenant gets its own collection, providing strong multi-tenancy boundaries.
- High-performance HNSW indexing with quantization options for production scaling.
- Simple Docker deployment for development; managed Qdrant Cloud for production.
- Free tier on Qdrant Cloud for initial deployments.

**Alternatives considered**:

| Database | Why not |
|---|---|
| **Pinecone** | Managed-only, no self-hosting option. Per-vector pricing becomes expensive at scale. Vendor lock-in. |
| **Weaviate** | Good option, but heavier to self-host (requires more resources). GraphQL-centric API is less straightforward for simple similarity search. |
| **Milvus** | Powerful but operationally complex. Requires multiple components (etcd, MinIO, Pulsar) for a production deployment. Overkill for a startup. |
| **ChromaDB** | Simple but designed for prototyping, not production multi-tenant workloads. No built-in collection-level access control. In-process mode doesn't scale. |
| **pgvector** | Uses existing PostgreSQL. Viable for small scale, but HNSW performance and features (filtering, payloads, quantization) lag behind dedicated vector DBs. Mixing OLTP and vector workloads on one DB creates resource contention. |

---

## 3. Metadata Database: PostgreSQL

**Choice**: PostgreSQL 16 with async SQLAlchemy + asyncpg

**Why**:
- Industry standard for relational data. Rock-solid ACID compliance.
- `asyncpg` is the fastest async PostgreSQL driver for Python.
- SQLAlchemy 2.0's `mapped_column` and type annotations provide a clean, modern ORM experience.
- Alembic handles schema migrations reliably.
- Every cloud provider offers managed PostgreSQL (RDS, Cloud SQL, Azure DB).

**Alternatives considered**:

| Database | Why not |
|---|---|
| **MySQL/MariaDB** | Viable but PostgreSQL has richer feature set (JSON, arrays, better indexing). Async driver ecosystem is weaker. |
| **SQLite** | Not suitable for concurrent production workloads or multi-process deployments. |
| **MongoDB** | Schema-less design doesn't add value here -- tenant/document metadata is inherently relational. Adds operational complexity without benefit. |

---

## 4. Embeddings & LLM: Google Gemini

**Choice**: `gemini-embedding-001` (embeddings) + `gemini-2.0-flash` (LLM)

**Why**:
- **Cost**: Gemini API has a generous free tier. `gemini-2.0-flash` is significantly cheaper than GPT-4 or Claude for comparable quality.
- **Speed**: Flash models are optimized for low latency -- important for chatbot UX.
- **Embedding quality**: `gemini-embedding-001` produces 3072-dimensional vectors with strong semantic understanding.
- **Single vendor**: One API key and SDK for both embedding and generation reduces integration complexity.
- `google-genai` SDK is well-maintained and supports both sync and async patterns.

**Alternatives considered**:

| Provider | Why not |
|---|---|
| **OpenAI (GPT-4o + text-embedding-3)** | Higher per-token cost. No free tier for production use. Excellent quality but premium pricing. |
| **Anthropic (Claude)** | No embedding API -- would need a separate provider for embeddings. Higher cost than Gemini Flash. |
| **Cohere** | Good embedding models (embed-v3) but smaller LLM ecosystem. Would need two providers. |
| **Open-source (Llama, Mistral via Ollama)** | Requires GPU infrastructure. Higher operational burden. Quality gap vs. frontier models for RAG grounding. Good for on-prem requirements. |
| **AWS Bedrock** | Multi-model access but adds AWS dependency. Per-token pricing varies by model. More complex setup than a direct API key. |

---

## 5. Document Processing

### Text Extraction

| Format | Library | Why |
|---|---|---|
| PDF | **PyMuPDF** | Fastest Python PDF parser. Handles complex layouts well. MIT licensed. |
| DOCX | **python-docx** | Standard library for Word documents. Lightweight and reliable. |
| TXT | Built-in `bytes.decode()` | No external dependency needed. |

**Alternatives**: `pdfplumber` (slower but better table extraction), `unstructured` (heavier, supports more formats), `Apache Tika` (Java-based, powerful but adds JVM dependency).

### Chunking

**Choice**: Custom recursive character splitter with sentence boundary detection.

**Why**:
- Simple, predictable, and fast.
- Sentence boundary awareness prevents mid-sentence splits that degrade retrieval quality.
- Configurable `chunk_size` (500) and `chunk_overlap` (50) via environment variables.

**Alternatives**: LangChain's `RecursiveCharacterTextSplitter` (heavier dependency for the same result), semantic chunking (splits by topic/meaning -- better quality but much slower and more complex), fixed-size token chunking (simpler but ignores text structure).

---

## 6. Authentication: API Key + bcrypt

**Choice**: Random hex API keys with bcrypt hashing and prefix-based lookup.

**Why**:
- Simple for B2B SaaS -- companies integrate with a single API key.
- bcrypt hashing means stolen database data doesn't expose keys.
- 8-character prefix enables fast DB lookup without trying every hash.
- No token expiry or refresh flow complexity.

**Alternatives considered**:

| Method | Why not (for now) |
|---|---|
| **JWT** | Adds token issuance, expiry, refresh complexity. Better for user-facing auth (login/signup) than machine-to-machine API access. |
| **OAuth 2.0** | Overkill for API key auth. Appropriate if we add third-party integrations or user-level auth later. |
| **API key without hashing** | Insecure. A database breach exposes all keys in plaintext. |

---

## 7. Multi-Tenancy: Separate Collections

**Choice**: One Qdrant collection per tenant (`tenant_<hex_uuid>`).

**Why**:
- **Hard isolation**: No query can accidentally access another tenant's data, even with bugs.
- **Simple deletion**: Dropping a tenant means deleting one collection.
- **Independent tuning**: Collections can have different indexing parameters if needed.

**Trade-offs**:
- More collections = more memory overhead in Qdrant (each collection maintains its own HNSW index).
- At 10,000+ tenants, this approach may need re-evaluation.

**Alternative**: Single shared collection with a `tenant_id` payload filter. Lower overhead but weaker isolation -- a missing filter clause leaks data across tenants. Suitable for trusted internal multi-tenancy, risky for B2B SaaS.

---

## 8. Rate Limiting: SlowAPI

**Choice**: SlowAPI (backed by `limits` library).

**Why**:
- Integrates directly with FastAPI as middleware.
- IP-based rate limiting out of the box.
- Minimal configuration.

**Alternatives**: Custom middleware with Redis (more scalable for distributed deployments), Cloudflare rate limiting (offloads to edge, no code changes), Kong/Traefik (API gateway-level limiting).

For production with multiple API server instances, move rate limiting to Redis or an API gateway so limits are shared across instances.

---

## 9. Async Architecture

**Choice**: Fully async I/O with thread pool offloading for sync libraries.

**Why**:
- FastAPI + uvicorn runs an async event loop. Blocking calls freeze all concurrent requests.
- Database (asyncpg) and vector DB (AsyncQdrantClient) are natively async.
- Google Gemini SDK is sync-only. We use `anyio.to_thread.run_sync` to run embedding and LLM calls in a thread pool without blocking the event loop.

**Alternative**: Sync FastAPI with multiple Gunicorn workers. Simpler code but worse resource utilization -- each worker handles one request at a time. Async handles thousands of concurrent I/O-bound requests per worker.

---

## 10. Migration Tool: Alembic

**Choice**: Alembic with async support.

**Why**:
- The standard migration tool for SQLAlchemy.
- Supports auto-generation of migrations from model changes.
- Async-compatible with `asyncpg`.

**Alternatives**: `yoyo-migrations` (lighter but less integrated), raw SQL files (no auto-generation, error-prone), Django migrations (tied to Django ORM).

---

## Summary Table

| Component | Choice | Key Reason |
|---|---|---|
| Framework | FastAPI | Async-native, auto-docs, Pydantic validation |
| Vector DB | Qdrant | Open-source, collection isolation, async client |
| Metadata DB | PostgreSQL | Industry standard, async driver, managed options |
| Embeddings | Gemini embedding-001 | Free tier, 3072-dim, same vendor as LLM |
| LLM | Gemini 2.0 Flash | Low cost, low latency, good RAG grounding |
| PDF parsing | PyMuPDF | Fastest Python PDF parser |
| Auth | API key + bcrypt | Simple B2B pattern, secure storage |
| Multi-tenancy | Separate collections | Hard data isolation |
| Rate limiting | SlowAPI | FastAPI-native, minimal config |
| Migrations | Alembic | SQLAlchemy standard, async support |
