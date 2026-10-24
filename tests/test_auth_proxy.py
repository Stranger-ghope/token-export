import asyncio, os, pytest
from httpx import AsyncClient, ASGITransport, Response
from gateway.main import app
from gateway.db.session import init_db
from gateway.config import settings

ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "dev-admin-key-change-me")

@pytest.fixture(scope="session", autouse=True)
def _db():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

@pytest.mark.asyncio
async def test_missing_key_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/chat/completions", json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 401

@pytest.mark.asyncio
async def test_invalid_key_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/chat/completions", headers={"Authorization": "Bearer tg_bogus"}, json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 401

@pytest.mark.asyncio
async def test_admin_requires_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/admin/tenants", json={"name": "x"})
        assert r.status_code in (401, 403, 422, 503)
        r2 = await c.post("/admin/tenants", json={"name": "x"}, headers={"X-Admin-Key": "wrong"})
        assert r2.status_code == 401

@pytest.mark.asyncio
async def test_tools_requires_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/tools/tokens/count", json={"text": "hi"})
        assert r.status_code == 401

@pytest.mark.asyncio
async def test_proxy_nonstream_mocked(monkeypatch):
    # patch httpx.AsyncClient.post to return a canned response
    import gateway.proxy.router as pr
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            return Response(200, json={"choices": [{"message": {"content": "hello"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}})
    monkeypatch.setattr(pr.httpx, "AsyncClient", FakeClient)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "px"}, headers={"X-Admin-Key": ADMIN_KEY})
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid}, headers={"X-Admin-Key": ADMIN_KEY})
        key = k.json()["key"]
        r = await c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                         json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 200
        assert r.json()["choices"][0]["message"]["content"] == "hello"

@pytest.mark.asyncio
async def test_proxy_stream_mocked(monkeypatch):
    import gateway.proxy.router as pr
    class FakeStreamResp:
        status_code = 200
        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"hi"}}]}'
            yield 'data: [DONE]'
        async def aread(self):
            return b""
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def stream(self, method, url, json=None, headers=None):
            class CM:
                async def __aenter__(self_inner): return FakeStreamResp()
                async def __aexit__(self_inner, *a): return False
            return CM()
    monkeypatch.setattr(pr.httpx, "AsyncClient", FakeClient)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "sx"}, headers={"X-Admin-Key": ADMIN_KEY})
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid}, headers={"X-Admin-Key": ADMIN_KEY})
        key = k.json()["key"]
        r = await c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                         json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True})
        assert r.status_code == 200
        assert "data:" in r.text
