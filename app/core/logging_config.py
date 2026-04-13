import logging
import json
import os
import sys
from datetime import datetime, timezone

from app.config import settings


_RESERVED_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "environment": settings.environment,
            "process": record.process,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_ATTRS and not key.startswith("_")
        }
        log_record.update(extras)

        return json.dumps(log_record, default=str)


def setup_logging():
    """Setup logging for the application based on the environment."""
    log_level = os.getenv("LOG_LEVEL", settings.log_level).upper()
    handler = logging.StreamHandler(sys.stdout)

    if settings.environment == "production":
        handler.setFormatter(JSONFormatter())
    else:
        # User-friendly simple formatter for development
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )
        handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.access", "gunicorn", "gunicorn.access"):
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.handlers.clear()
        third_party_logger.propagate = True
        third_party_logger.setLevel(log_level)
