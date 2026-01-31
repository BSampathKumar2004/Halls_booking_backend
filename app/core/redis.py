import os
import json
import redis
from redis.exceptions import RedisError
from dotenv import load_dotenv

load_dotenv()

_redis_client = None


def get_redis_client():
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    redis_url = os.getenv("REDIS_URL")
    print("DEBUG REDIS_URL =", redis_url)

    if not redis_url:
        return None

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        print("✅ Redis connected")
        _redis_client = client
        return _redis_client
    except RedisError as e:
        print("⚠️ Redis unavailable:", e)
        return None


def get_cache(key: str):
    client = get_redis_client()
    if not client:
        return None
    try:
        data = client.get(key)
        return json.loads(data) if data else None
    except RedisError:
        return None


def set_cache(key: str, value, ttl: int = 60):
    client = get_redis_client()
    if not client:
        return
    try:
        client.setex(key, ttl, json.dumps(value))
    except RedisError:
        pass


def delete_cache(key: str):
    client = get_redis_client()
    if not client:
        return
    try:
        client.delete(key)
    except RedisError:
        pass
