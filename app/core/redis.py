import os
import json
import redis
from redis.exceptions import RedisError

REDIS_URL = os.getenv("REDIS_URL")

redis_client = None

if REDIS_URL:
    try:
        redis_client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2
        )
        redis_client.ping()
        print("✅ Redis connected")
    except RedisError as e:
        print("⚠️ Redis not available, continuing without cache:", e)
        redis_client = None


def get_cache(key: str):
    if not redis_client:
        return None
    try:
        data = redis_client.get(key)
        return json.loads(data) if data else None
    except RedisError:
        return None


def set_cache(key: str, value, ttl: int = 60):
    if not redis_client:
        return
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except RedisError:
        pass


def delete_cache(key: str):
    if not redis_client:
        return
    try:
        redis_client.delete(key)
    except RedisError:
        pass
