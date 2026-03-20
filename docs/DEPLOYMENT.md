# Deployment Guide

This guide walks through deploying the RAG SaaS API to a production environment.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.12+ |
| Docker & Docker Compose | Latest |
| PostgreSQL | 15+ (managed or self-hosted) |
| Qdrant | 1.8+ (managed or self-hosted) |
| A Google Cloud account | Gemini API key enabled |

---

## 1. Containerize the Application

### Dockerfile

Create a `Dockerfile` in the project root:

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Docker Compose (Full Stack)

Create a `docker-compose.yml` for the entire stack:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: rag_saas
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_storage:/qdrant/storage
    ports:
      - "6333:6333"
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}

  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"

volumes:
  pgdata:
  qdrant_storage:
```

Build and run:

```bash
docker compose up --build -d
```

---

## 2. Environment Variables for Production

Create a `.env` file (never commit this):

```env
DATABASE_URL=postgresql+asyncpg://postgres:<password>@postgres:5432/rag_saas
QDRANT_HOST=qdrant
QDRANT_PORT=6333
GEMINI_API_KEY=<your-gemini-api-key>
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=3072
LLM_MODEL=gemini-2.0-flash
CORS_ORIGINS=["https://yourdomain.com"]
```

In managed cloud environments, inject these via secrets management (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault) rather than `.env` files.

---

## 3. Database Migrations

Always run Alembic migrations before starting the API:

```bash
alembic upgrade head
```

In Docker, this is handled by the `command` in `docker-compose.yml`. In Kubernetes or other environments, run migrations as an init container or a pre-deploy job.

---

## 4. Cloud Deployment Options

### Option A: Railway / Render / Fly.io (Simplest)

These PaaS platforms support Docker images directly.

1. Push your repo to GitHub.
2. Connect the repo to the platform.
3. Set environment variables in the platform dashboard.
4. The platform auto-builds from `Dockerfile` and deploys.
5. Use their managed PostgreSQL add-on. For Qdrant, use [Qdrant Cloud](https://cloud.qdrant.io) (free tier available).

### Option B: AWS (ECS + Fargate)

1. Push your Docker image to ECR:
   ```bash
   aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker build -t rag-saas-api .
   docker tag rag-saas-api:latest <account>.dkr.ecr.<region>.amazonaws.com/rag-saas-api:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/rag-saas-api:latest
   ```
2. Create an ECS cluster with Fargate.
3. Define a task definition referencing the ECR image.
4. Use RDS PostgreSQL for the database.
5. Run Qdrant on an EC2 instance or use Qdrant Cloud.
6. Use an Application Load Balancer (ALB) in front of ECS.
7. Store secrets in AWS Secrets Manager and reference them in the task definition.

### Option C: GCP (Cloud Run)

1. Build and push to Google Artifact Registry:
   ```bash
   gcloud builds submit --tag gcr.io/<project>/rag-saas-api
   ```
2. Deploy to Cloud Run:
   ```bash
   gcloud run deploy rag-saas-api \
     --image gcr.io/<project>/rag-saas-api \
     --platform managed \
     --set-env-vars "DATABASE_URL=...,GEMINI_API_KEY=..." \
     --allow-unauthenticated
   ```
3. Use Cloud SQL for PostgreSQL.
4. Use Qdrant Cloud or a GCE instance for Qdrant.

### Option D: Kubernetes

1. Create Deployment and Service manifests for the API.
2. Deploy PostgreSQL via Helm chart (`bitnami/postgresql`) or use a managed database.
3. Deploy Qdrant via its official Helm chart (`qdrant/qdrant`).
4. Use ConfigMaps for non-secret config and Secrets for credentials.
5. Set up an Ingress controller (nginx-ingress or Traefik) with TLS.

---

## 5. Reverse Proxy & TLS

For any self-hosted deployment, place NGINX or Caddy in front of the API:

```nginx
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Use Let's Encrypt / Certbot for free TLS certificates. Caddy handles this automatically.

---

## 6. Health Checks & Monitoring

The API exposes a health endpoint:

```
GET /api/v1/health
```

Response:
```json
{"status": "ok", "qdrant": "ok", "database": "ok"}
```

Configure your load balancer or orchestrator to poll this endpoint. A `503` response means a dependency is down.

For monitoring, add:
- **Prometheus + Grafana**: Expose `/metrics` via `prometheus-fastapi-instrumentator`.
- **Structured logging**: The app already uses Python `logging`. Forward logs to CloudWatch, Stackdriver, or an ELK stack.
- **Alerting**: Set up alerts on error rates, latency P95, and health check failures.

---

## 7. CI/CD Pipeline

Example GitHub Actions workflow (`.github/workflows/deploy.yml`):

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build & push Docker image
        run: |
          docker build -t rag-saas-api .
          # Push to your registry of choice
      - name: Deploy
        run: |
          # Trigger deployment (ECS update, Cloud Run deploy, kubectl apply, etc.)
```

---

## 8. Production Checklist

- [ ] Environment variables set via secrets manager (not `.env` files)
- [ ] `CORS_ORIGINS` restricted to your actual frontend domain(s)
- [ ] TLS/HTTPS enabled on all public endpoints
- [ ] Database connection pooling configured (SQLAlchemy pool defaults are usually fine; tune `pool_size` and `max_overflow` for load)
- [ ] Qdrant API key set if using Qdrant Cloud
- [ ] File upload size limit configured (`max_upload_size_mb`)
- [ ] Rate limiting tuned for expected traffic
- [ ] Health check endpoint monitored by load balancer
- [ ] Logs forwarded to a centralized system
- [ ] Alembic migrations run as part of deploy pipeline
- [ ] Backups configured for PostgreSQL and Qdrant storage
