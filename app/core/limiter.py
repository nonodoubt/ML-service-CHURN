"""Rate-limit и concurrent-limit на Redis.

Используется во всём пайплайне проверок:
  Кредиты -> Concurrent -> Rate limit -> Резерв -> Celery
"""

import time
import redis.asyncio as aioredis
from app.core.config import get_settings

settings = get_settings()

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url, decode_responses=True, max_connections=50
        )
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# Sliding-window лимитер на ZSET. Атомарность гарантируется eval'ом lua.
RATE_LIMIT_LUA = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000)
local count = redis.call('ZCARD', key)
if count >= limit then
  return 0
end
redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
redis.call('PEXPIRE', key, window * 1000)
return 1
"""


async def check_rate_limit(user_id: str, limit: int, window_sec: int) -> bool:
    r = await get_redis()
    now_ms = int(time.time() * 1000)
    res = await r.eval(RATE_LIMIT_LUA, 1, f"rl:{user_id}", window_sec, limit, now_ms)
    return bool(res)


async def acquire_concurrent_slot(user_id: str, max_concurrent: int, ttl: int = 300) -> bool:
    """Атомарно занимаем слот. Если перебор — откатываем INCR."""
    r = await get_redis()
    key = f"conc:{user_id}"
    current = await r.incr(key)
    await r.expire(key, ttl)
    if current > max_concurrent:
        await r.decr(key)
        return False
    return True


async def release_concurrent_slot(user_id: str):
    r = await get_redis()
    key = f"conc:{user_id}"
    val = await r.decr(key)
    if val <= 0:
        await r.delete(key)
