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
