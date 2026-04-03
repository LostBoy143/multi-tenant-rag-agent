from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings

# Initialize Limiter with Redis storage if available
storage_uri = settings.redis_url if settings.redis_url.startswith("redis") else "memory://"
limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)
