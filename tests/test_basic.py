import asyncio, json, pytest
from httpx import AsyncClient, ASGITransport
from gateway.main import app
from gateway.db.session import init_db


@pytest.fixture(scope="session", autouse=True)
def _db():
    asyncio.get_event_loop().run_until_complete(init_db())


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_pii_mask():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # create tenant + key
        t = await c.post("/admin/tenants", json={"name": "t"})
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid})
        key = k.json()["key"]
        r = await c.post("/tools/pii/mask", headers={"Authorization": f"Bearer {key}"},
                         json={"text": "email a@b.com phone 13800000000"})
        assert r.status_code == 200
        assert r.json()["stats"]["email"] == 1
        assert "*" in r.json()["masked"]


@pytest.mark.asyncio
async def test_token_count():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "t2"})
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid})
        key = k.json()["key"]
        r = await c.post("/tools/tokens/count", headers={"Authorization": f"Bearer {key}"},
                         json={"text": "hello world", "model": "gpt-4o"})
        assert r.status_code == 200
        assert r.json()["tokens"] > 0
        assert "bpe" in r.json()


@pytest.mark.asyncio
async def test_models_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "t3"})
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid})
        key = k.json()["key"]
        r = await c.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
        assert r.status_code == 200
        assert len(r.json()["data"]) > 0
