"""
Redis Cache Module

Provides async Redis connection for caching GeoJSON responses.
"""
import os
import json
import logging
from typing import Optional, Any
import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

# TTL en segundos (1 hora para datos geográficos que cambian poco)
DEFAULT_TTL = 3600

redis_client: Optional[redis.Redis] = None


async def connect_to_redis():
    """Inicializa la conexión a Redis."""
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            await redis_client.ping()
            logger.info(f"Redis connection initialized: {REDIS_URL}")
        except Exception as e:
            logger.warning(f"Redis not available, caching disabled: {e}")
            redis_client = None


async def disconnect_from_redis():
    """Cierra la conexión a Redis."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None
        logger.info("Redis connection closed")


async def get_redis() -> Optional[redis.Redis]:
    """
    Dependency para obtener el cliente Redis.
    Retorna None si Redis no está disponible (graceful degradation).
    """
    global redis_client
    if redis_client is None:
        await connect_to_redis()
    return redis_client


async def cache_get(key: str) -> Optional[Any]:
    """
    Obtiene un valor del cache.
    Retorna None si no existe o Redis no está disponible.
    """
    client = await get_redis()
    if client is None:
        return None

    try:
        data = await client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.warning(f"Redis GET error for {key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Guarda un valor en el cache.
    Retorna False si Redis no está disponible.
    """
    client = await get_redis()
    if client is None:
        return False

    try:
        await client.setex(key, ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.warning(f"Redis SET error for {key}: {e}")
        return False


async def cache_delete(pattern: str) -> int:
    """
    Elimina claves que coinciden con un patrón.
    Útil para invalidar cache cuando cambian los datos.
    """
    client = await get_redis()
    if client is None:
        return 0

    try:
        keys = await client.keys(pattern)
        if keys:
            return await client.delete(*keys)
        return 0
    except Exception as e:
        logger.warning(f"Redis DELETE error for pattern {pattern}: {e}")
        return 0
