import uuid
import time
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from gateway.db.models import UsageRecord, BillingEvent
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
    # Fire webhook if configured (best-effort, non-blocking)
    if settings.billing_webhook_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(settings.billing_webhook_url, json={
                    "tenant_id": tenant_id,
                    "event_type": event_type,
                    "payload": payload,
                })
            ev.delivered = True
            await session.commit()
        except Exception as e:
            log.warning("billing_webhook_failed", error=str(e))
    return ev
