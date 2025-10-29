import redis.asyncio as aioredis
from app.config import settings

redis_async = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
