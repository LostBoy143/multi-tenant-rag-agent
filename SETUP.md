# Setup Guide

Complete walkthrough to get the RAG SaaS API running locally from scratch.

---

## 1. Prerequisites

| Tool           | Version | Check              |
| -------------- | ------- | ------------------ |
| Python         | 3.12+   | `python --version` |
| Docker Desktop | Latest  | `docker --version` |
| pip            | Latest  | `pip --version`    |

---

## 2. Environment Variables

Copy the example and fill in values:

```bash
cp .env.example .env
```

### Variable Reference

| Variable               | Required | Default                                                     | Description                                                                                                                     |
| ---------------------- | -------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`         | Yes      | `postgresql+asyncpg://postgres:dev@localhost:5432/rag_saas` | PostgreSQL connection string. Uses async driver `asyncpg`. Change the password if you used a custom one when starting Postgres. |
| `QDRANT_HOST`          | Yes      | `localhost`                                                 | Qdrant vector DB hostname. Use `localhost` for local Docker.                                                                    |
| `QDRANT_PORT`          | Yes      | `6333`                                                      | Qdrant REST API port. Default Qdrant port is `6333`.                                                                            |
| `GEMINI_API_KEY`       | **Yes**  | _(empty)_                                                   | Your Google Gemini API key. **This is the only value you must manually set.** See section below on how to get it.               |
| `EMBEDDING_MODEL`      | No       | `text-embedding-004`                                        | Gemini embedding model name. `text-embedding-004` produces 768-dim vectors and is the cheapest option.                          |
| `EMBEDDING_DIMENSIONS` | No       | `768`                                                       | Vector dimensions. Must match the embedding model output.                                                                       |
| `LLM_MODEL`            | No       | `gemini-2.0-flash`                                          | Gemini LLM model for generating RAG answers. Flash is the cheapest and fastest.                                                 |
| `CORS_ORIGINS`         | No       | `["*"]`                                                     | Allowed CORS origins as JSON array. Use `["*"]` for development, restrict in production.                                        |

---

## 3. How to Get a Gemini API Key

This is the only external credential you need. It is free to get started.

1. Go to **Google AI Studio**: [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with your Google account.
3. Click **"Create API key"**.
4. Select or create a Google Cloud project when prompted.
5. Copy the generated key (starts with `AIza...`).
6. Paste it into your `.env` file:
   ```
   GEMINI_API_KEY=AIzaSy...your-key-here
   ```

**Free tier limits** (as of March 2026):

- Gemini 2.0 Flash: 15 requests/minute, 1 million tokens/day
- text-embedding-004: 1,500 requests/minute

This is more than enough for development and light production use.

---

## 4. Start Infrastructure (Docker)

Open a terminal and run these commands to start PostgreSQL and Qdrant:

```bash
# Start PostgreSQL (metadata store)
docker run -d \
  --name rag-postgres \
  -p 5432:5432 \
  -e POSTGRES_DB=rag_saas \
  -e POSTGRES_PASSWORD=dev \
  postgres:16

# Start Qdrant (vector database)
docker run -d \
  --name rag-qdrant \
  -p 6333:6333 \
  qdrant/qdrant
```

**On Windows (PowerShell)**, use backtick `` ` `` instead of `\` for line continuation, or run each as a single line:

```powershell
docker run -d --name rag-postgres -p 5432:5432 -e POSTGRES_DB=rag_saas -e POSTGRES_PASSWORD=dev postgres:16

docker run -d --name rag-qdrant -p 6333:6333 qdrant/qdrant
```

Verify they are running:

```bash
docker ps
```

You should see both `rag-postgres` and `rag-qdrant` listed.

---

## 5. Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

## 6. Run Database Migrations

This creates the `tenants`, `api_keys`, and `documents` tables in PostgreSQL:

```bash
alembic upgrade head
```

If `alembic` is not on PATH, use:

```bash
python -m alembic upgrade head
```

---

## 7. Start the API Server

```bash
fastapi dev
```

Or if `fastapi` CLI is not on PATH:

```bash
python -m uvicorn app.main:app --reload
```

The server starts at **http://localhost:8000**.

- Swagger UI docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

## 8. Test the API (Quick Walkthrough)

### Register a tenant

```bash
curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "My Company"}'
```

Response includes a one-time `api_key`. Save it -- it cannot be retrieved again.

### Upload a document

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@path/to/document.pdf"
```

### Ask a question

```bash
curl -X POST http://localhost:8000/api/v1/chat/query \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main topic of the document?"}'
```

---

## 9. Test Frontend

Open `frontend/index.html` in your browser for a visual testing interface. No build step needed -- it is a standalone HTML file that talks directly to the API.

---

## Stopping / Restarting

```bash
# Stop containers
docker stop rag-postgres rag-qdrant

# Start them again (data persists)
docker start rag-postgres rag-qdrant

# Remove containers and data (destructive)
docker rm -f rag-postgres rag-qdrant
```

---

## Troubleshooting

| Problem                           | Fix                                                                                                       |
| --------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `Connection refused` on port 5432 | Ensure `rag-postgres` container is running: `docker ps`                                                   |
| `Connection refused` on port 6333 | Ensure `rag-qdrant` container is running: `docker ps`                                                     |
| `alembic: command not found`      | Use `python -m alembic upgrade head` instead                                                              |
| `GEMINI_API_KEY` errors           | Verify the key is set in `.env` and is valid at [aistudio.google.com](https://aistudio.google.com/apikey) |
| `Unsupported file type` on upload | Ensure the file is PDF, DOCX, or TXT. Some systems send wrong MIME types.                                 |
| Document stuck in `processing`    | Check the terminal running the API server for error logs. Likely a Gemini API key issue.                  |
