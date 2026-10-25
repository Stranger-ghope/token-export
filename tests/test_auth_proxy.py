import asyncio, os, pytest
from httpx import AsyncClient, ASGITransport, Response
from gateway.main import app
from gateway.db.session import init_db
from gateway.config import settings

from gateway.config.settings import settings as app_settings

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
async def test_admin_list_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # unauthenticated -> 401
        assert (await c.get("/admin/tenants")).status_code == 401
        assert (await c.get("/admin/api-keys")).status_code == 401
        h = {"X-Admin-Key": ADMIN_KEY}
        t = await c.post("/admin/tenants", json={"name": "list-me"}, headers=h)
        assert t.status_code == 200
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid}, headers=h)
        assert k.status_code == 200

        tenants = await c.get("/admin/tenants", headers=h)
        assert tenants.status_code == 200
        assert any(x["id"] == tid for x in tenants.json())
        row = next(x for x in tenants.json() if x["id"] == tid)
        assert row["active_keys"] >= 1

        keys = await c.get("/admin/api-keys", params={"tenant_id": tid}, headers=h)
        assert keys.status_code == 200
        listed = keys.json()
        assert len(listed) >= 1
        # never expose the raw/hash material in listings
        assert all("key_hash" not in x and "key" not in x for x in listed)
        assert all(x["tenant_id"] == tid for x in listed)


@pytest.mark.asyncio
async def test_upstream_creds_missing_fails_closed(monkeypatch):
    """No provider credential configured -> actionable 503, no upstream call."""
    import gateway.proxy.router as pr

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("httpx must not be touched without credentials")

    monkeypatch.setattr(pr.httpx, "AsyncClient", Boom)
    monkeypatch.setattr(app_settings, "upstream_api_key_openai", None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "nocreds"}, headers={"X-Admin-Key": ADMIN_KEY})
        k = await c.post("/admin/api-keys", json={"tenant_id": t.json()["id"]}, headers={"X-Admin-Key": ADMIN_KEY})
        key = k.json()["key"]
        r = await c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                         json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 503
        assert "UPSTREAM_API_KEY_OPENAI" in r.json()["error"]


@pytest.mark.asyncio
async def test_upstream_key_injected_tenant_key_withheld(monkeypatch):
    """Provider credential is injected; the tenant key never reaches upstream."""
    import gateway.proxy.router as pr

    captured: dict = {}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["headers"] = dict(headers or {})
            return Response(200, json={"choices": [{"message": {"content": "hello"}}],
                                       "usage": {"prompt_tokens": 5, "completion_tokens": 1}})

    monkeypatch.setattr(pr.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(app_settings, "upstream_api_key_openai", "sk-provider-xyz")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "inj"}, headers={"X-Admin-Key": ADMIN_KEY})
        k = await c.post("/admin/api-keys", json={"tenant_id": t.json()["id"]}, headers={"X-Admin-Key": ADMIN_KEY})
        key = k.json()["key"]
        r = await c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                         json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 200

    assert captured["headers"].get("authorization") == "Bearer sk-provider-xyz"
    sent = " ".join(str(v) for v in captured["headers"].values())
    assert key not in sent, "tenant key must not be forwarded upstream"


@pytest.mark.asyncio
async def test_admin_quotas_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/admin/quotas")).status_code == 401
        h = {"X-Admin-Key": ADMIN_KEY}
        t = await c.post("/admin/tenants", json={"name": "quota-list"}, headers=h)
        tid = t.json()["id"]

        r = await c.get("/admin/quotas", headers=h)
        assert r.status_code == 200
        row = next(x for x in r.json() if x["tenant_id"] == tid)
        assert row["tenant_name"] == "quota-list"
        assert row["rpm_limit"] > 0 and row["tpm_limit"] > 0
        assert row["daily_token_cap"] > 0 and row["monthly_token_cap"] > 0

        # per-tenant endpoint still works alongside the list
        single = await c.get(f"/admin/quota/{tid}", headers=h)
        assert single.status_code == 200
        assert single.json()["rpm_limit"] == row["rpm_limit"]


@pytest.mark.asyncio
async def test_admin_quota_update_and_usage_vs_cap():
    import uuid
    from datetime import datetime, timezone
    from gateway.db.session import get_session_factory
    from gateway.db.models import UsageRecord

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        h = {"X-Admin-Key": ADMIN_KEY}
        assert (await c.put("/admin/quotas/t_any", json={"rpm_limit": 5})).status_code == 401

        t = await c.post("/admin/tenants", json={"name": "quota-edit"}, headers=h)
        tid = t.json()["id"]

        # validation: non-positive limits are rejected
        bad = await c.put(f"/admin/quotas/{tid}", json={"rpm_limit": 0}, headers=h)
        assert bad.status_code == 422
        # unknown tenant
        missing = await c.put("/admin/quotas/t_missing", json={"rpm_limit": 5}, headers=h)
        assert missing.status_code == 404
        # nothing to update
        assert (await c.put(f"/admin/quotas/{tid}", json={}, headers=h)).status_code == 400

        # valid update
        r = await c.put(
            f"/admin/quotas/{tid}",
            json={"rpm_limit": 7, "tpm_limit": 999, "daily_token_cap": 1234},
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["rpm_limit"] == 7
        assert r.json()["daily_token_cap"] == 1234
        assert r.json()["monthly_token_cap"] > 0  # untouched field preserved

        # usage recorded today must show up against the caps
        sf = get_session_factory()
        async with sf() as s:
            s.add(UsageRecord(
                id=f"u_{uuid.uuid4().hex[:12]}", tenant_id=tid, request_id="req_test",
                provider="openai", model="gpt-4o",
                prompt_tokens=100, completion_tokens=50, total_tokens=150,
                created_at=datetime.now(timezone.utc),
            ))
            await s.commit()

        rows = (await c.get("/admin/quotas", headers=h)).json()
        row = next(x for x in rows if x["tenant_id"] == tid)
        assert row["rpm_limit"] == 7
        assert row["daily_tokens_used"] == 150
        assert row["monthly_tokens_used"] == 150


@pytest.mark.asyncio
async def test_admin_quota_audit_log():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        h = {"X-Admin-Key": ADMIN_KEY}
        assert (await c.get("/admin/audit")).status_code == 401

        t = await c.post("/admin/tenants", json={"name": "audit-tenant"}, headers=h)
        tid = t.json()["id"]
        before = len((await c.get("/admin/audit", headers=h)).json())
        quotas = (await c.get("/admin/quotas", headers=h)).json()
        original_rpm = next(q for q in quotas if q["tenant_id"] == tid)["rpm_limit"]

        # a real change is recorded with before/after values
        r = await c.put(f"/admin/quotas/{tid}", json={"rpm_limit": 33}, headers=h)
        assert r.status_code == 200
        entries = (await c.get("/admin/audit", headers=h)).json()
        assert len(entries) == before + 1
        entry = entries[0]
        assert entry["tenant_id"] == tid
        assert entry["tenant_name"] == "audit-tenant"
        assert entry["changes"]["rpm_limit"]["to"] == 33
        assert entry["changes"]["rpm_limit"]["from"] == original_rpm
        assert entry["created_at"]

        # writing the same value again is a no-op: nothing new to audit
        await c.put(f"/admin/quotas/{tid}", json={"rpm_limit": 33}, headers=h)
        entries2 = (await c.get("/admin/audit", headers=h)).json()
        assert len(entries2) == len(entries)

        # filterable by tenant
        only = (await c.get("/admin/audit", params={"tenant_id": tid}, headers=h)).json()
        assert all(e["tenant_id"] == tid for e in only)
        assert len(only) >= 1


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
    monkeypatch.setattr(app_settings, "upstream_api_key_openai", "sk-test-upstream")
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
    monkeypatch.setattr(app_settings, "upstream_api_key_openai", "sk-test-upstream")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": "sx"}, headers={"X-Admin-Key": ADMIN_KEY})
        tid = t.json()["id"]
        k = await c.post("/admin/api-keys", json={"tenant_id": tid}, headers={"X-Admin-Key": ADMIN_KEY})
        key = k.json()["key"]
        r = await c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                         json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True})
        assert r.status_code == 200
        assert "data:" in r.text
