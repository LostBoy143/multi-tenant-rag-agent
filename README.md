# RAG SaaS API

Multi-tenant RAG (Retrieval-Augmented Generation) SaaS API built with FastAPI, Qdrant, and Google Gemini.

## Quick Start

### Prerequisites

- Python 3.12+
- Docker (for Qdrant and PostgreSQL)
- Google Gemini API key

### Infrastructure

```bash
docker run -d -p 6333:6333 --name qdrant qdrant/qdrant
docker run -d -p 5432:5432 -e POSTGRES_DB=rag_saas -e POSTGRES_PASSWORD=dev --name postgres postgres:16
```

### Installation

```bash
pip install -r requirements.txt
cp .env.example .env   # edit with your values
alembic upgrade head
fastapi dev
```

API docs available at `http://localhost:8000/docs`

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/tenants` | None | Register a new company |
| GET | `/api/v1/tenants/me` | API Key | Get tenant info |
| POST | `/api/v1/documents/upload` | API Key | Upload a document |
| GET | `/api/v1/documents` | API Key | List tenant documents |
| DELETE | `/api/v1/documents/{id}` | API Key | Delete a document |
| POST | `/api/v1/chat/query` | API Key | Ask a question (RAG) |
| GET | `/api/v1/health` | None | Health check |

## Architecture

- **FastAPI** async Python API
- **Qdrant** vector database (1 collection per tenant for isolation)
- **PostgreSQL** metadata store (tenants, API keys, documents)
- **Google Gemini** embeddings + LLM
