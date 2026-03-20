# Architecture

This document explains how the RAG SaaS API works end-to-end.

---

## High-Level Overview

```
                        ┌──────────────┐
                        │   Client     │
                        │ (Frontend /  │
                        │  SDK / cURL) │
                        └──────┬───────┘
                               │ HTTPS + X-API-Key
                               ▼
                     ┌─────────────────────┐
                     │     FastAPI App      │
                     │  ┌───────────────┐   │
                     │  │  Rate Limiter │   │
                     │  │  (SlowAPI)    │   │
                     │  └───────────────┘   │
                     │  ┌───────────────┐   │
                     │  │    CORS       │   │
                     │  │  Middleware   │   │
                     │  └───────────────┘   │
                     │  ┌───────────────┐   │
                     │  │  API Key Auth │   │
                     │  │  (bcrypt)     │   │
                     │  └───────────────┘   │
                     └──────┬──────┬────────┘
                            │      │
               ┌────────────┘      └────────────┐
               ▼                                 ▼
    ┌─────────────────────┐          ┌──────────────────────┐
    │   PostgreSQL        │          │      Qdrant          │
    │   (Metadata DB)     │          │  (Vector Database)   │
    │                     │          │                      │
    │  - tenants          │          │  One collection per  │
    │  - api_keys         │          │  tenant (isolated)   │
    │  - documents        │          │                      │
    └─────────────────────┘          └──────────────────────┘
                                              ▲
                                              │ Embeddings
                                     ┌────────┴────────┐
                                     │  Google Gemini   │
                                     │  Embedding API   │
                                     │  + LLM API       │
                                     └─────────────────┘
```

---

## Core Flows

### 1. Tenant Registration

```
Client                     FastAPI                PostgreSQL              Qdrant
  │                           │                       │                      │
  │  POST /tenants            │                       │                      │
  │  { "name": "Acme" }      │                       │                      │
  │ ─────────────────────────>│                       │                      │
  │                           │  INSERT tenant        │                      │
  │                           │ ─────────────────────>│                      │
  │                           │                       │                      │
  │                           │  INSERT api_key       │                      │
  │                           │  (bcrypt hashed)      │                      │
  │                           │ ─────────────────────>│                      │
  │                           │                       │                      │
  │                           │  Create collection    │                      │
  │                           │  "tenant_<hex_id>"    │                      │
  │                           │ ─────────────────────────────────────────────>│
  │                           │                       │                      │
  │  201: { tenant, api_key } │                       │                      │
  │ <─────────────────────────│                       │                      │
```

1. A new `Tenant` row is created in PostgreSQL.
2. A random API key is generated (`8-char-prefix.48-char-secret`).
3. The key is bcrypt-hashed and stored; the raw key is returned once.
4. A dedicated Qdrant collection is created for the tenant with cosine distance and 3072-dimensional vectors.

### 2. Document Upload & Processing

```
Client                FastAPI              Background Task         Gemini          Qdrant
  │                      │                       │                   │               │
  │  POST /upload        │                       │                   │               │
  │  (multipart file)    │                       │                   │               │
  │ ────────────────────>│                       │                   │               │
  │                      │  Validate file type   │                   │               │
  │                      │  Validate file size   │                   │               │
  │                      │  INSERT document      │                   │               │
  │                      │  (status=processing)  │                   │               │
  │  202: Accepted       │                       │                   │               │
  │ <────────────────────│                       │                   │               │
  │                      │  Spawn background     │                   │               │
  │                      │ ─────────────────────>│                   │               │
  │                      │                       │                   │               │
  │                      │                       │ 1. Parse document  │               │
  │                      │                       │    (PDF/DOCX/TXT)  │               │
  │                      │                       │                   │               │
  │                      │                       │ 2. Chunk text      │               │
  │                      │                       │    (500 chars,     │               │
  │                      │                       │     50 overlap)    │               │
  │                      │                       │                   │               │
  │                      │                       │ 3. Embed chunks    │               │
  │                      │                       │ ──────────────────>│               │
  │                      │                       │  (batch of 100)    │               │
  │                      │                       │ <──────────────────│               │
  │                      │                       │  3072-dim vectors  │               │
  │                      │                       │                   │               │
  │                      │                       │ 4. Upsert to Qdrant               │
  │                      │                       │ ─────────────────────────────────>│
  │                      │                       │                   │               │
  │                      │                       │ 5. UPDATE document │               │
  │                      │                       │    status = ready  │               │
  │                      │                       │    chunk_count = N │               │
```

The upload returns immediately with `202 Accepted`. The heavy work (parsing, chunking, embedding, vector storage) happens in a FastAPI background task so the client doesn't wait.

**Document parsing pipeline**:
- **PDF**: PyMuPDF extracts text page by page.
- **DOCX**: `python-docx` extracts paragraph text.
- **TXT**: UTF-8 decode.

**Chunking strategy**: Recursive character splitter that prioritizes sentence boundaries (`.`, `!`, `?`, `\n`). Default chunk size is 500 characters with 50-character overlap to preserve context across chunk boundaries.

**Embedding**: Chunks are sent to Google Gemini's `gemini-embedding-001` model in batches of 100. Each chunk becomes a 3072-dimensional vector.

**Storage**: Vectors are upserted into the tenant's Qdrant collection with metadata (document ID, chunk index, text, filename).

### 3. RAG Query

```
Client              FastAPI            Gemini Embed       Qdrant           Gemini LLM
  │                    │                    │                │                 │
  │  POST /chat/query  │                    │                │                 │
  │  { question }      │                    │                │                 │
  │ ──────────────────>│                    │                │                 │
  │                    │                    │                │                 │
  │                    │  Embed question    │                │                 │
  │                    │ ──────────────────>│                │                 │
  │                    │  query vector      │                │                 │
  │                    │ <─────────────────│                │                 │
  │                    │                    │                │                 │
  │                    │  Vector search (top_k, threshold)   │                 │
  │                    │ ───────────────────────────────────>│                 │
  │                    │  scored chunks                      │                 │
  │                    │ <──────────────────────────────────│                 │
  │                    │                    │                │                 │
  │                    │  Build prompt:     │                │                 │
  │                    │  system_instruction + context + question              │
  │                    │ ────────────────────────────────────────────────────>│
  │                    │  LLM response                                        │
  │                    │ <───────────────────────────────────────────────────│
  │                    │                    │                │                 │
  │  200: { answer,    │                    │                │                 │
  │         sources }  │                    │                │                 │
  │ <─────────────────│                    │                │                 │
```

1. The user's question is embedded into a 3072-dim vector using the same Gemini embedding model.
2. Qdrant performs cosine similarity search against the tenant's collection, returning the top-k most relevant chunks above a score threshold (default 0.3).
3. Retrieved chunks are formatted into a numbered context block.
4. The context + question are sent to `gemini-2.0-flash` with a system instruction that enforces conversational tone, brevity, and natural responses without revealing the underlying knowledge base.
5. The response is returned alongside source metadata for optional frontend display.

---

## Multi-Tenancy Model

Each tenant gets a **physically separate Qdrant collection** named `tenant_<hex_uuid>`. This provides:

- **Data isolation**: Tenant A's queries never touch Tenant B's vectors.
- **Independent scaling**: Collections can be sized/indexed independently.
- **Clean deletion**: Removing a tenant means dropping one collection.

The metadata database (PostgreSQL) stores tenant accounts, API key hashes, and document records. Foreign keys with `ON DELETE CASCADE` ensure cleanup when a tenant is removed.

---

## Request Authentication Flow

```
Incoming Request
       │
       ▼
  Has X-API-Key header?
       │
  No ──┤──> 401 Unauthorized
       │
  Yes  ▼
  Extract 8-char prefix
       │
       ▼
  Find APIKey row by prefix (WHERE is_active = true)
       │
  Not found ──> 401 Unauthorized
       │
  Found  ▼
  bcrypt.checkpw(raw_key, stored_hash)
       │
  Mismatch ──> 401 Unauthorized
       │
  Match  ▼
  Load Tenant by tenant_id
       │
       ▼
  Inject Tenant into route handler
```

The prefix-based lookup avoids full-table bcrypt comparisons. Only the matching prefix's hash is verified.

---

## Project Structure

```
rag/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, middleware, routers
│   ├── config.py            # Pydantic Settings (env-based config)
│   ├── database.py          # Async SQLAlchemy engine & session
│   ├── dependencies.py      # DI: DB session, Qdrant client, auth
│   ├── models/
│   │   ├── tenant.py        # Tenant + APIKey ORM models
│   │   └── document.py      # Document ORM model + status enum
│   ├── schemas/
│   │   ├── tenant.py        # Pydantic request/response models
│   │   ├── document.py
│   │   └── chat.py
│   ├── routers/
│   │   ├── tenants.py       # Tenant registration & info
│   │   ├── documents.py     # Upload, list, delete + background processing
│   │   └── chat.py          # RAG query endpoint
│   └── services/
│       ├── document_processor.py  # PDF/DOCX/TXT text extraction
│       ├── chunker.py             # Recursive text splitter
│       ├── embedding.py           # Gemini embedding API wrapper
│       ├── vector_store.py        # Qdrant CRUD operations
│       └── rag.py                 # RAG orchestrator (embed -> search -> LLM)
├── alembic/                  # Database migration scripts
├── frontend/                 # Test UI (vanilla HTML/CSS/JS)
├── docs/                     # Documentation
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## Concurrency Model

FastAPI runs on an async event loop (uvicorn). Most operations are natively async:

- **Database**: Async SQLAlchemy with `asyncpg` driver.
- **Qdrant**: `AsyncQdrantClient` for all vector operations.

The Google Gemini SDK is synchronous. To avoid blocking the event loop, all Gemini calls (embedding and LLM generation) are offloaded to a thread pool using `anyio.to_thread.run_sync`.

Document processing runs as a FastAPI `BackgroundTask`, which executes after the HTTP response is sent. This keeps upload latency low regardless of document size.
