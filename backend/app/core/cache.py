import redis.asyncio as aioredis
from typing import Optional

from .config import settings

redis_pool: Optional[aioredis.Redis] = None

async def get_redis_connection() -> Optional[aioredis.Redis]:
    """
    Returns the active Redis connection pool.
    Ensure startup_redis_pool() has been called.
    """
    return redis_pool

async def startup_redis_pool():
    """
    Initializes the Redis connection pool.
    Call this function during application startup.
    """
    global redis_pool
    if settings.REDIS_URL:
        try:
            print(f"Connecting to Redis at {settings.REDIS_URL}")
            redis_pool = await aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            # Test connection
            await redis_pool.ping()
            print("Successfully connected to Redis and pinged.")
        except Exception as e:
            print(f"Failed to connect to Redis: {e}")
            redis_pool = None # Ensure pool is None if connection fails
    else:
        print("REDIS_URL not configured. Redis cache will not be available.")
        redis_pool = None

async def shutdown_redis_pool():
    """
    Closes the Redis connection pool.
    Call this function during application shutdown.
    """
    global redis_pool
    if redis_pool:
        print("Closing Redis connection pool...")
        await redis_pool.close()
        print("Redis connection pool closed.")
        redis_pool = None

# Utility functions for caching (examples)
async def set_cache(key: str, value: str, expire: Optional[int] = None):
    """
    Sets a value in the Redis cache.
    :param key: The cache key.
    :param value: The value to store (will be stored as a string).
    :param expire: Expiration time in seconds. If None, no expiration.
    """
    if redis_pool:
        try:
            await redis_pool.set(key, value, ex=expire)
        except Exception as e:
            print(f"Error setting cache for key '{key}': {e}")

async def get_cache(key: str) -> Optional[str]:
    """
    Gets a value from the Redis cache.
    :param key: The cache key.
    :return: The cached value as a string, or None if not found or error.
    """
    if redis_pool:
        try:
            return await redis_pool.get(key)
        except Exception as e:
            print(f"Error getting cache for key '{key}': {e}")
            return None
    return None

async def delete_cache(key: str):
    """
    Deletes a key from the Redis cache.
    :param key: The cache key to delete.
    """
    if redis_pool:
        try:
            await redis_pool.delete(key)
        except Exception as e:
            print(f"Error deleting cache for key '{key}': {e}")
