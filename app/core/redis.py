import os
import json
import redis

REDIS_URL = os.getenv("REDIS_URL")

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True
) if REDIS_URL else None


def get_cache(key: str):
    if not redis_client:
        return None
    data = redis_client.get(key)
    return json.loads(data) if data else None


def set_cache(key: str, value, ttl: int = 60):
    """
    value MUST be JSON serializable (dict / list)
    """
    if not redis_client:
        return
    redis_client.setex(
        key,
        ttl,
        json.dumps(value)
    )


def delete_cache(key: str):
    if not redis_client:
        return
    redis_client.delete(key)
