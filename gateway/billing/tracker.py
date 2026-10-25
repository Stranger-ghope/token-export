import uuid
import time
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from gateway.db.models import UsageRecord, BillingEvent, Quota
from gateway.config.settings import settings
from gateway.config.logging import log


async def record_usage(
    session: AsyncSession,
    tenant_id: str,
    api_key_id: Optional[str],
    request_id: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    bpe_prompt: int = 0,
    bpe_completion: int = 0,
    compression_ratio: float = 1.0,
    latency_ms: float = 0.0,
    status_code: int = 200,
    metadata: Optional[dict] = None,
) -> UsageRecord:
    rec = UsageRecord(
        id=f"u_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        request_id=request_id,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        bpe_prompt_tokens=bpe_prompt,
        bpe_completion_tokens=bpe_completion,
        compression_ratio=compression_ratio,
        latency_ms=latency_ms,
        status_code=status_code,
        metadata_json=metadata or {},
    )
    session.add(rec)
    await session.commit()
    return rec


async def emit_billing_event(session: AsyncSession, tenant_id: str, event_type: str, payload: dict) -> BillingEvent:
    ev = BillingEvent(
        id=f"be_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
    )
    session.add(ev)
    await session.commit()
    # Fire webhook if configured (best-effort, non-blocking, fire-and-forget)
    if settings.billing_webhook_url:
        import asyncio
        ev_id = ev.id
        async def _fire():
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(settings.billing_webhook_url, json={
                        "tenant_id": tenant_id,
                        "event_type": event_type,
                        "payload": payload,
                    })
                try:
                    from gateway.db.session import get_session_factory
                    sf = get_session_factory()
                    if sf is not None:
                        async with sf() as s2:
                            from gateway.db.models import BillingEvent
                            from sqlalchemy import update
                            await s2.execute(update(BillingEvent).where(BillingEvent.id == ev_id).values(delivered=True))
                            await s2.commit()
                except Exception:
                    pass
            except Exception as e:
                log.warning("billing_webhook_failed", error=str(e))
        asyncio.create_task(_fire())
    return ev


async def maybe_emit_cap_alert(session: AsyncSession, tenant_id: str) -> Optional[BillingEvent]:
    """Fire a `cap_alert` event when the tenant's usage today crosses
    CAP_ALERT_THRESHOLD of its daily cap. Emitted at most once per tenant per
    UTC day (tracked in billing_events, so it stays once across workers).
    Returns None when no alert is due."""
    threshold = settings.cap_alert_threshold
    if not threshold or threshold <= 0:
        return None

    quota = (
        await session.execute(select(Quota).where(Quota.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if quota is None or not quota.daily_token_cap:
        return None

    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    used = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(UsageRecord.total_tokens), 0)).where(
                    UsageRecord.tenant_id == tenant_id,
                    UsageRecord.created_at >= day_start,
                )
            )
        ).scalar()
        or 0
    )
    cap = int(quota.daily_token_cap)
    if used < cap * threshold:
        return None

    already = (
        await session.execute(
            select(BillingEvent.id)
            .where(
                BillingEvent.tenant_id == tenant_id,
                BillingEvent.event_type == "cap_alert",
                BillingEvent.created_at >= day_start,
            )
            .limit(1)
        )
    ).first()
    if already:
        return None

    percent = round(used / cap * 100, 1)
    log.warning(
        "daily_cap_alert",
        tenant=tenant_id,
        tokens_used=used,
        daily_token_cap=cap,
        percent=percent,
    )
    return await emit_billing_event(
        session,
        tenant_id,
        "cap_alert",
        {
            "period": "daily",
            "tokens_used": used,
            "token_cap": cap,
            "percent": percent,
            "threshold_percent": round(threshold * 100, 1),
        },
    )
