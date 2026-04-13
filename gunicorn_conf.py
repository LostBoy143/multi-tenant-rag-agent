import multiprocessing
import os

# Gunicorn configuration file for FastAPI/Uvicorn
# Usage: gunicorn -c gunicorn_conf.py app.main:app

def _container_port() -> str:
    # Azure App Service for Containers forwards traffic to WEBSITES_PORT.
    return os.getenv("WEBSITES_PORT") or os.getenv("PORT") or "8000"


# Bind to 0.0.0.0 to be accessible outside the container/host.
bind = os.getenv("BIND", f"0.0.0.0:{_container_port()}")

# Worker configuration
# RAG workers can be memory-heavy because embedding/model code is loaded in-process.
# Default to one worker on PaaS; scale out via instances or set WEB_CONCURRENCY.
workers_per_core_str = os.getenv("WORKERS_PER_CORE", "0")
max_workers_str = os.getenv("MAX_WORKERS", None)
use_importlib = True

cores = multiprocessing.cpu_count()
workers_per_core = float(workers_per_core_str)
default_web_concurrency = max(int(workers_per_core * cores), 1)
if max_workers_str:
    use_concurrency = min(int(max_workers_str), int(default_web_concurrency))
else:
    use_concurrency = int(default_web_concurrency)

workers = max(int(os.getenv("WEB_CONCURRENCY", str(use_concurrency))), 1)

# Uvicorn worker class
worker_class = "uvicorn.workers.UvicornWorker"

# Logging
accesslog = os.getenv("ACCESS_LOG", "-")
errorlog = os.getenv("ERROR_LOG", "-")
loglevel = os.getenv("LOG_LEVEL", "info")
capture_output = True
enable_stdio_inheritance = True
access_log_format = (
    '%(h)s %(l)s %(u)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" request_time_us=%(D)s'
)

# Timeout
# RAG queries (embeddings/LLM) can take time, so we set a generous timeout
timeout = int(os.getenv("TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("KEEP_ALIVE", "5"))
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")

# Process management
preload_app = False
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None


def on_starting(server):
    server.log.info(
        "Starting gunicorn: bind=%s workers=%s timeout=%s loglevel=%s",
        bind,
        workers,
        timeout,
        loglevel,
    )


def when_ready(server):
    server.log.info("Gunicorn master is ready and listening on %s", bind)


def worker_abort(worker):
    worker.log.error("Gunicorn worker aborted: pid=%s", worker.pid)
