import asyncio, os, pytest
os.environ["REDIS_FAKE"] = "1"
from httpx import AsyncClient, ASGITransport
from gateway.main import app
from gateway.db.session import init_db
from gateway.middleware.rate_limit import get_limiter

ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "dev-admin-key-change-me")




@pytest.mark.asyncio
async def test_rpm_limit_enforced():
    # reset limiter
    from gateway.middleware import rate_limit as rl
    rl._limiter = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "rl"}, headers={"X-Admin-Key": ADMIN_KEY})
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid}, headers={"X-Admin-Key": ADMIN_KEY})
        key = k.json()["key"]
        # set a tiny rpm limit by updating quota row directly
        from gateway.db.session import get_session_factory
        from gateway.db.models import Quota
        from sqlalchemy import update
        sf = get_session_factory()
        async with sf() as s:
            await s.execute(update(Quota).where(Quota.tenant_id == tid).values(rpm_limit=2, tpm_limit=100000))
            await s.commit()
        statuses = []
        for _ in range(4):
            r = await c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                             json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
            statuses.append(r.status_code)
        assert 429 in statuses, statuses


@pytest.mark.asyncio
async def test_redis_limits_shared_across_workers():
    """Two limiter instances on the same Redis share counters, so multiple
    workers/instances enforce ONE limit instead of one limit each."""
    import fakeredis
    import fakeredis.aioredis as aioredis
    from gateway.middleware.rate_limit import RedisRateLimiter

    server = fakeredis.FakeServer()
    worker_a = RedisRateLimiter(aioredis.FakeRedis(server=server))
    worker_b = RedisRateLimiter(aioredis.FakeRedis(server=server))

    assert await worker_a.check_rpm("tenant:shared", 2) is True
    assert await worker_b.check_rpm("tenant:shared", 2) is True
    # third request seen by a *different* worker must still be refused
    assert await worker_a.check_rpm("tenant:shared", 2) is False
    assert await worker_b.check_rpm("tenant:shared", 2) is False


@pytest.mark.asyncio
async def test_redis_unreachable_falls_back_to_inmemory(monkeypatch):
    monkeypatch.delenv("REDIS_FAKE", raising=False)
    from gateway.middleware import rate_limit as rl
    from gateway.config.settings import settings as app_settings
    monkeypatch.setattr(app_settings, "redis_fallback_inmemory", True)
    monkeypatch.setattr(app_settings, "redis_url", "redis://127.0.0.1:6398/0")
    monkeypatch.setattr(rl, "_limiter", None)

    limiter = await rl.get_limiter()
    assert isinstance(limiter, rl.InMemoryRateLimiter)
    # the fallback still enforces limits
    assert await limiter.check_rpm("tenant:fb", 1) is True
    assert await limiter.check_rpm("tenant:fb", 1) is False


@pytest.mark.asyncio
async def test_redis_required_fails_closed(monkeypatch):
    """With REDIS_FALLBACK_INMEMORY=false an unreachable Redis must refuse
    traffic (503) instead of silently allowing unlimited requests."""
    monkeypatch.delenv("REDIS_FAKE", raising=False)
    from gateway.middleware import rate_limit as rl
    from gateway.config.settings import settings as app_settings
    monkeypatch.setattr(app_settings, "redis_fallback_inmemory", False)
    monkeypatch.setattr(app_settings, "redis_url", "redis://127.0.0.1:6398/0")
    monkeypatch.setattr(rl, "_limiter", None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "failclosed"}, headers={"X-Admin-Key": ADMIN_KEY})
        k = await c.post("/admin/api-keys", json={"tenant_id": t.json()["id"]}, headers={"X-Admin-Key": ADMIN_KEY})
        r = await c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {k.json()['key']}"},
                         json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 503
        assert "Rate limiter" in r.json()["detail"]
