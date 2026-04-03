import multiprocessing
import os

# Gunicorn configuration file for FastAPI/Uvicorn
# Usage: gunicorn -c gunicorn_conf.py app.main:app

# Bind to 0.0.0.0 to be accessible outside the container/host
bind = os.getenv("BIND", "0.0.0.0:8000")

# Worker configuration
# For a RAG application, we want enough workers to handle concurrency 
# but not so many that we exhaust RAM (PDF parsing/LLM calls).
# Formula: (2 x $num_cores) + 1
workers_per_core_str = os.getenv("WORKERS_PER_CORE", "1")
max_workers_str = os.getenv("MAX_WORKERS", None)
use_importlib = True

cores = multiprocessing.cpu_count()
workers_per_core = float(workers_per_core_str)
default_web_concurrency = workers_per_core * cores + 1
if max_workers_str:
    use_concurrency = min(int(max_workers_str), int(default_web_concurrency))
else:
    use_concurrency = int(default_web_concurrency)

workers = max(int(os.getenv("WEB_CONCURRENCY", use_concurrency)), 2)

# Uvicorn worker class
worker_class = "uvicorn.workers.UvicornWorker"

# Logging
accesslog = os.getenv("ACCESS_LOG", "-")
errorlog = os.getenv("ERROR_LOG", "-")
loglevel = os.getenv("LOG_LEVEL", "info")

# Timeout
# RAG queries (embeddings/LLM) can take time, so we set a generous timeout
timeout = int(os.getenv("TIMEOUT", "120"))
keepalive = int(os.getenv("KEEP_ALIVE", "5"))

# Process management
preload_app = True
worker_tmp_dir = "/dev/shm"  # Recommended for Docker to prevent blocking
