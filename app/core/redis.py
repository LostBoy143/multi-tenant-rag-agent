import redis.asyncio as aioredis
from app.config import settings

redis_client: aioredis.Redis = aioredis.from_url(settings.redis_url)
