import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import func, select

from gateway.main import app
from gateway.config.settings import settings as app_settings
from gateway.billing.tracker import maybe_emit_cap_alert, record_usage
from gateway.db.session import get_session_factory
from gateway.db.models import BillingEvent

ADMIN_KEY = "dev-admin-key-change-me"
HEADERS = {"X-Admin-Key": ADMIN_KEY}


async def _make_tenant(name: str) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        t = await c.post("/admin/tenants", json={"name": name}, headers=HEADERS)
        assert t.status_code == 200
        tid = t.json()["id"]
        r = await c.put(f"/admin/quotas/{tid}", json={"daily_token_cap": 1000}, headers=HEADERS)
        assert r.status_code == 200
        return tid


async def _count_alerts(tenant_id: str) -> int:
    sf = get_session_factory()
    async with sf() as s:
        return int(
            (
                await s.execute(
                    select(func.count(BillingEvent.id)).where(
                        BillingEvent.tenant_id == tenant_id,
                        BillingEvent.event_type == "cap_alert",
                    )
                )
            ).scalar()
            or 0
        )


@pytest.mark.asyncio
async def test_cap_alert_fires_once_per_day(monkeypatch):
    monkeypatch.setattr(app_settings, "cap_alert_threshold", 0.8)
    tid = await _make_tenant("cap-alert-once")

    sf = get_session_factory()
    async with sf() as s:
        # 850 / 1000 = 85% of the daily cap -> above the 80% threshold
        await record_usage(
            session=s, tenant_id=tid, api_key_id=None, request_id="req_alert_1",
            provider="openai", model="gpt-4o", prompt_tokens=400, completion_tokens=450,
        )
        first = await maybe_emit_cap_alert(s, tid)
        assert first is not None
        assert first.event_type == "cap_alert"
        assert first.payload["period"] == "daily"
        assert first.payload["tokens_used"] == 850
        assert first.payload["token_cap"] == 1000
        assert first.payload["percent"] == 85.0

        # second call the same day must stay silent
        second = await maybe_emit_cap_alert(s, tid)
        assert second is None

    assert await _count_alerts(tid) == 1


@pytest.mark.asyncio
async def test_cap_alert_silent_below_threshold(monkeypatch):
    monkeypatch.setattr(app_settings, "cap_alert_threshold", 0.8)
    tid = await _make_tenant("cap-alert-below")

    sf = get_session_factory()
    async with sf() as s:
        # 100 / 1000 = 10% -> well below 80%
        await record_usage(
            session=s, tenant_id=tid, api_key_id=None, request_id="req_alert_2",
            provider="openai", model="gpt-4o", prompt_tokens=50, completion_tokens=50,
        )
        assert await maybe_emit_cap_alert(s, tid) is None

    assert await _count_alerts(tid) == 0


@pytest.mark.asyncio
async def test_cap_alert_disabled_when_threshold_zero(monkeypatch):
    monkeypatch.setattr(app_settings, "cap_alert_threshold", 0)
    tid = await _make_tenant("cap-alert-off")

    sf = get_session_factory()
    async with sf() as s:
        await record_usage(
            session=s, tenant_id=tid, api_key_id=None, request_id="req_alert_3",
            provider="openai", model="gpt-4o", prompt_tokens=1000, completion_tokens=1000,
        )
        assert await maybe_emit_cap_alert(s, tid) is None

    assert await _count_alerts(tid) == 0
