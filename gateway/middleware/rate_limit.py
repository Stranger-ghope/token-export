import time
import uuid
from collections import defaultdict, deque
from typing import Optional
from fastapi import Request, HTTPException, status
from gateway.config.settings import settings
from gateway.config.logging import log

# In-memory fallback rate limiter (per process). Production should use Redis.
class InMemoryRateLimiter:
    def __init__(self):
        self._rpm: dict[str, deque] = defaultdict(deque)
        self._tpm: dict[str, list] = defaultdict(lambda: [0, time.time()])

    def check_rpm(self, key: str, limit: int) -> bool:
        now = time.time()
        q = self._rpm[key]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def check_tpm(self, key: str, tokens: int, limit: int) -> bool:
        now = time.time()
        bucket = self._tpm[key]
        if now - bucket[1] > 60:
            bucket[0] = 0
            bucket[1] = now
        if bucket[0] + tokens > limit:
            return False
        bucket[0] += tokens
        return True

    def record_tokens(self, key: str, tokens: int) -> None:
        now = time.time()
        bucket = self._tpm[key]
        if now - bucket[1] > 60:
            bucket[0] = 0
            bucket[1] = now
        bucket[0] += tokens


_limiter = InMemoryRateLimiter()


async def rate_limit_check(request: Request, estimated_tokens: int = 0) -> None:
    ak = getattr(request.state, "api_key", None)
    if ak is None:
        return
    quota = getattr(request.state, "quota", None)
    rpm_limit = quota.rpm_limit if quota else settings.default_rpm
    tpm_limit = quota.tpm_limit if quota else settings.default_tpm

    tenant_key = f"tenant:{ak.tenant_id}"
    if not _limiter.check_rpm(tenant_key, rpm_limit):
        log.warning("rate_limit_rpm_exceeded", tenant=ak.tenant_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Rate limit (RPM) exceeded")
    if estimated_tokens > 0 and not _limiter.check_tpm(tenant_key, estimated_tokens, tpm_limit):
        log.warning("rate_limit_tpm_exceeded", tenant=ak.tenant_id)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Rate limit (TPM) exceeded")
    request.state.rate_limit_key = tenant_key


def get_limiter() -> InMemoryRateLimiter:
    return _limiter
