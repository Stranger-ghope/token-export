import os
import time
from collections import defaultdict, deque
from typing import Optional
from fastapi import Request, HTTPException, status
from gateway.config.settings import settings
from gateway.config.logging import log

# ---------------------------------------------------------------------------
# Limiter implementations
# ---------------------------------------------------------------------------

class InMemoryRateLimiter:
    """Per-process fallback. Used when REDIS_FALLBACK_INMEMORY=true or Redis
    is unreachable. Not shared across workers/instances."""

    def __init__(self):
        self._rpm: dict[str, deque] = defaultdict(deque)
        self._tpm: dict[str, list] = defaultdict(lambda: [0, time.time()])

    async def check_rpm(self, key: str, limit: int) -> bool:
        now = time.time()
        q = self._rpm[key]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    async def check_tpm(self, key: str, tokens: int, limit: int) -> bool:
        now = time.time()
        bucket = self._tpm[key]
        if now - bucket[1] > 60:
            bucket[0] = 0
            bucket[1] = now
        if bucket[0] + tokens > limit:
            return False
        bucket[0] += tokens
        return True

    async def record_tokens(self, key: str, tokens: int) -> None:
        now = time.time()
        bucket = self._tpm[key]
        if now - bucket[1] > 60:
            bucket[0] = 0
            bucket[1] = now
        bucket[0] += tokens


class RedisRateLimiter:
    """Fixed-window limiter backed by Redis (async client)."""

    def __init__(self, redis_client):
        self.r = redis_client

    def _rpm_key(self, key: str) -> str:
        return f"rl:rpm:{key}:{int(time.time() // 60)}"

    def _tpm_key(self, key: str) -> str:
        return f"rl:tpm:{key}:{int(time.time() // 60)}"

    async def check_rpm(self, key: str, limit: int) -> bool:
        rk = self._rpm_key(key)
        try:
            n = await self.r.incr(rk)
            if n == 1:
                await self.r.expire(rk, 60)
            return n <= limit
        except Exception as e:
            log.warning("redis_rpm_error", error=str(e))
            return True  # fail open

    async def check_tpm(self, key: str, tokens: int, limit: int) -> bool:
        tk = self._tpm_key(key)
        try:
            cur = await self.r.get(tk)
            cur = int(cur) if cur else 0
            if cur + tokens > limit:
                return False
            await self.r.incrby(tk, tokens)
            await self.r.expire(tk, 60)
            return True
        except Exception as e:
            log.warning("redis_tpm_error", error=str(e))
            return True  # fail open

    async def record_tokens(self, key: str, tokens: int) -> None:
        tk = self._tpm_key(key)
        try:
            await self.r.incrby(tk, tokens)
            await self.r.expire(tk, 60)
        except Exception as e:
            log.warning("redis_record_error", error=str(e))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_limiter = None


async def _build_limiter():
    global _limiter
    # Test override: use fakeredis when REDIS_FAKE=1
    if os.environ.get("REDIS_FAKE") == "1":
        import fakeredis.aioredis as aioredis
        log.info("rate_limiter", backend="fakeredis")
        _limiter = RedisRateLimiter(aioredis.FakeRedis())
        return _limiter

    # Redis is the primary backend so limits are shared across workers and
    # instances. REDIS_FALLBACK_INMEMORY only decides what happens when Redis
    # is unreachable: fall back to the per-process limiter (dev), or fail
    # closed instead of silently allowing unlimited traffic (prod).
    try:
        import redis.asyncio as redis_async
        client = redis_async.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        await client.ping()
        log.info("rate_limiter", backend="redis", url=settings.redis_url)
        _limiter = RedisRateLimiter(client)
        return _limiter
    except Exception as e:
        if settings.redis_fallback_inmemory:
            log.warning("redis_unavailable_fallback_inmemory", error=str(e))
            _limiter = InMemoryRateLimiter()
            return _limiter
        # No fallback allowed: leave _limiter unset so the next request retries
        # (Redis may just be starting), and let the caller fail closed.
        log.error("redis_unavailable_no_fallback", error=str(e))
        _limiter = None
        raise RuntimeError(f"Redis unavailable ({e}) and REDIS_FALLBACK_INMEMORY=false") from e


async def get_limiter():
    global _limiter
    if _limiter is None:
        await _build_limiter()
    return _limiter


async def rate_limit_check(request: Request, estimated_tokens: int = 0) -> None:
    ak = getattr(request.state, "api_key", None)
    if ak is None:
        return
    quota = getattr(request.state, "quota", None)
    rpm_limit = quota.rpm_limit if quota else settings.default_rpm
    tpm_limit = quota.tpm_limit if quota else settings.default_tpm

    tenant_key = f"tenant:{ak.tenant_id}"
    try:
        limiter = await get_limiter()
    except Exception as e:
        log.error("rate_limiter_unavailable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter backend unavailable (Redis unreachable and REDIS_FALLBACK_INMEMORY=false)",
        )
    if not await limiter.check_rpm(tenant_key, rpm_limit):
        log.warning("rate_limit_rpm_exceeded", tenant=ak.tenant_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Rate limit (RPM) exceeded")
    if estimated_tokens > 0 and not await limiter.check_tpm(tenant_key, estimated_tokens, tpm_limit):
        log.warning("rate_limit_tpm_exceeded", tenant=ak.tenant_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Rate limit (TPM) exceeded")
    request.state.rate_limit_key = tenant_key
