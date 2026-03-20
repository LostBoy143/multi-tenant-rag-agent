# API Documentation

Base URL: `http://localhost:8000/api/v1`

All authenticated endpoints require the `X-API-Key` header containing the API key returned during tenant registration.

---

## Authentication

Every request (except tenant registration and health check) must include:

```
X-API-Key: <your-api-key>
```

The API key is a hex token generated during tenant registration. It is shown only once -- store it securely. The key is matched by its 8-character prefix and verified against a bcrypt hash.

If the key is missing, invalid, or inactive, all authenticated endpoints return:

```json
{ "detail": "Invalid API key." }
```

**Status**: `401 Unauthorized`

---

## Endpoints

### Health Check

Check that the API, database, and vector store are reachable.

```
GET /api/v1/health
```

**Auth**: None

**Response** `200 OK` (or `503` if degraded):

```json
{
  "status": "ok",
  "qdrant": "ok",
  "database": "ok"
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"degraded"` |
| `qdrant` | string | `"ok"` or `"unavailable"` |
| `database` | string | `"ok"` or `"unavailable"` |

---

### Register Tenant

Create a new tenant and receive an API key.

```
POST /api/v1/tenants
```

**Auth**: None

**Request Body** (JSON):

```json
{
  "name": "Acme Corp"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `name` | string | Yes | 1-255 characters |

**Response** `201 Created`:

```json
{
  "tenant": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Acme Corp",
    "created_at": "2026-03-20T10:30:00Z"
  },
  "api_key": "abcd1234.e5f6789012345678901234567890abcdef1234567890abcdef12"
}
```

| Field | Type | Description |
|---|---|---|
| `tenant.id` | UUID | Unique tenant identifier |
| `tenant.name` | string | Tenant display name |
| `tenant.created_at` | datetime | ISO 8601 creation timestamp |
| `api_key` | string | **Shown only once.** Use this in the `X-API-Key` header for all subsequent requests. |

**Side effects**: Creates a dedicated Qdrant vector collection for this tenant.

---

### Get Current Tenant

Retrieve info about the authenticated tenant.

```
GET /api/v1/tenants/me
```

**Auth**: Required (`X-API-Key`)

**Response** `200 OK`:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Acme Corp",
  "created_at": "2026-03-20T10:30:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Tenant identifier |
| `name` | string | Tenant name |
| `created_at` | datetime | Account creation timestamp |

---

### Upload Document

Upload a document for processing (parsing, chunking, embedding).

```
POST /api/v1/documents/upload
```

**Auth**: Required (`X-API-Key`)

**Request**: `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | Yes | The document file to upload |

**Supported file types**:

| MIME Type | Extension |
|---|---|
| `application/pdf` | `.pdf` |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `.docx` |
| `text/plain` | `.txt` |

**Max file size**: 20 MB (configurable via `MAX_UPLOAD_SIZE_MB`)

**Response** `202 Accepted`:

```json
{
  "document": {
    "id": "f1e2d3c4-b5a6-7890-1234-567890abcdef",
    "filename": "company-handbook.pdf",
    "file_type": "pdf",
    "status": "processing",
    "chunk_count": 0,
    "error_message": null,
    "created_at": "2026-03-20T10:35:00Z"
  },
  "message": "Document uploaded and processing started."
}
```

| Field | Type | Description |
|---|---|---|
| `document.id` | UUID | Unique document identifier |
| `document.filename` | string | Original filename |
| `document.file_type` | string | `"pdf"`, `"docx"`, or `"txt"` |
| `document.status` | string | `"processing"` initially, then `"ready"` or `"failed"` |
| `document.chunk_count` | integer | Number of text chunks (0 until processing completes) |
| `document.error_message` | string or null | Error details if processing failed |
| `document.created_at` | datetime | Upload timestamp |
| `message` | string | Confirmation message |

**Note**: Processing happens in the background. Poll the list endpoint to check when `status` changes to `"ready"`.

**Error responses**:

| Status | Condition |
|---|---|
| `400 Bad Request` | Unsupported file type |
| `413 Request Entity Too Large` | File exceeds size limit |
| `401 Unauthorized` | Missing or invalid API key |

---

### List Documents

Get all documents belonging to the authenticated tenant, sorted newest first.

```
GET /api/v1/documents
```

**Auth**: Required (`X-API-Key`)

**Response** `200 OK`:

```json
[
  {
    "id": "f1e2d3c4-b5a6-7890-1234-567890abcdef",
    "filename": "company-handbook.pdf",
    "file_type": "pdf",
    "status": "ready",
    "chunk_count": 47,
    "error_message": null,
    "created_at": "2026-03-20T10:35:00Z"
  }
]
```

Returns an empty array `[]` if no documents exist.

---

### Delete Document

Remove a document and all its vector embeddings.

```
DELETE /api/v1/documents/{document_id}
```

**Auth**: Required (`X-API-Key`)

**Path Parameters**:

| Parameter | Type | Description |
|---|---|---|
| `document_id` | UUID | ID of the document to delete |

**Response** `204 No Content`: Empty body on success.

**Error responses**:

| Status | Condition |
|---|---|
| `404 Not Found` | Document doesn't exist or belongs to another tenant |
| `401 Unauthorized` | Missing or invalid API key |

---

### Query (Chat)

Ask a question against the tenant's uploaded documents using RAG.

```
POST /api/v1/chat/query
```

**Auth**: Required (`X-API-Key`)

**Request Body** (JSON):

```json
{
  "question": "What is the company's remote work policy?",
  "top_k": 5
}
```

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `question` | string | Yes | -- | 1-2000 characters |
| `top_k` | integer | No | 5 | 1-20 |

`top_k` controls how many relevant document chunks are retrieved from the vector database to build the answer context.

**Response** `200 OK`:

```json
{
  "answer": "The company allows fully remote work for all employees. Teams coordinate their own schedules, and there's a monthly in-office day for collaboration.",
  "sources": [
    {
      "filename": "company-handbook.pdf",
      "chunk_index": 12,
      "text_snippet": "All employees are eligible for remote work. Teams may set their own...",
      "score": 0.8723
    },
    {
      "filename": "company-handbook.pdf",
      "chunk_index": 14,
      "text_snippet": "Monthly collaboration days are held at the office on the first...",
      "score": 0.8341
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `answer` | string | The LLM-generated response grounded in retrieved context |
| `sources` | array | The document chunks used to build the answer |
| `sources[].filename` | string | Source document filename |
| `sources[].chunk_index` | integer | Position of this chunk within the document |
| `sources[].text_snippet` | string | First 200 characters of the chunk text |
| `sources[].score` | float | Cosine similarity score (0-1, higher = more relevant) |

If no relevant documents are found, `sources` will be an empty array and the answer will be a generic fallback.

**Error responses**:

| Status | Condition |
|---|---|
| `401 Unauthorized` | Missing or invalid API key |
| `429 Too Many Requests` | Rate limit exceeded |

---

## Rate Limiting

The API enforces rate limits using the client's IP address. When exceeded:

```json
{ "detail": "Rate limit exceeded. Please slow down." }
```

**Status**: `429 Too Many Requests`

---

## Error Format

All error responses follow a consistent shape:

```json
{
  "detail": "Human-readable error description."
}
```

For validation errors (Pydantic), the response includes field-level details:

```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "String should have at least 1 character",
      "type": "string_too_short"
    }
  ]
}
```

---

## Interactive Docs

FastAPI auto-generates interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

Both are available in development and can be disabled in production by passing `docs_url=None, redoc_url=None` to the FastAPI constructor.
