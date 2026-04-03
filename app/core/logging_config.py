import logging
import sys
import json
from datetime import datetime
from app.config import settings

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "environment": settings.environment,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if available (e.g. org_id, etc)
        if hasattr(record, "extra"):
            log_record.update(record.extra)
            
        return json.dumps(log_record)

def setup_logging():
    """Setup logging for the application based on the environment."""
    handler = logging.StreamHandler(sys.stdout)
    
    if settings.environment == "production":
        handler.setFormatter(JSONFormatter())
    else:
        # User-friendly simple formatter for development
        formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
        handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    
    # Silence third-party loggers if needed
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("gunicorn.access").handlers = [handler]
