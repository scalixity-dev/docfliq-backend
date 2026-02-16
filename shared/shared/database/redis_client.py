from typing import Any

import redis.asyncio as redis

RedisClient = redis.Redis


def get_redis_client(redis_url: str, **kwargs: Any) -> redis.Redis:
    return redis.from_url(redis_url, decode_responses=True, **kwargs)
