import os

try:
    import redis.asyncio as redis
except ModuleNotFoundError:  # pragma: no cover - exercised via import fallback
    redis = None

try:
    from kombu.utils.url import safequote
except ModuleNotFoundError:  # pragma: no cover - exercised via import fallback
    def safequote(value):
        return value


_in_memory_store = {}


if redis is not None:
    redis_host = safequote(os.environ.get('REDIS_HOST', 'localhost'))
    redis_client = redis.Redis(host=redis_host, port=6379, db=0)
else:
    redis_client = None


async def add_key_value_redis(key, value, expire=None):
    if redis_client is None:
        _in_memory_store[key] = value
        return

    await redis_client.set(key, value)
    if expire:
        await redis_client.expire(key, expire)


async def get_value_redis(key):
    if redis_client is None:
        return _in_memory_store.get(key)

    return await redis_client.get(key)


async def delete_key_redis(key):
    if redis_client is None:
        _in_memory_store.pop(key, None)
        return

    await redis_client.delete(key)
