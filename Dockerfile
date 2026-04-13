FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy only installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application
COPY . .

EXPOSE 8000

# Keep the HTTP worker alive for Azure diagnostics; enable migrations explicitly when desired.
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS_ON_STARTUP:-false}\" = \"true\" ]; then alembic upgrade head; else echo 'RUN_MIGRATIONS_ON_STARTUP=false; skipping alembic upgrade'; fi; exec gunicorn -c gunicorn_conf.py app.main:app"]
