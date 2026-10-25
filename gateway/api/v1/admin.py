from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid
from gateway.config.settings import settings
from gateway.db.session import get_session
from gateway.auth.keys import create_tenant, issue_api_key, get_quota
from gateway.db.models import Tenant, ApiKey, Quota, UsageRecord, BillingEvent, QuotaAudit
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_attempts: dict = {}
def _admin_rate_limit_ok(ip: str) -> bool:
    import time
    now = time.time()
    bucket = _admin_attempts.setdefault(ip, [])
    # keep last 60s
    bucket[:] = [t for t in bucket if now - t < 60]
    if len(bucket) >= 20:
        return False
    bucket.append(now)
    return True


_admin_bearer = HTTPBearer(auto_error=False)

async def require_admin(
    creds: HTTPAuthorizationCredentials = Depends(_admin_bearer),
    request: Request = None,
):
    if not settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Admin API not configured")
    # simple per-IP brute-force protection
    client_ip = request.client.host if request else "unknown"
    if not _admin_rate_limit_ok(client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
    raw = None
    if creds and creds.credentials:
        raw = creds.credentials
    if not raw:
        raw = request.headers.get("x-admin-key") if request else None
    if raw != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")
    return True


class CreateTenantReq(BaseModel):
    name: str
    tenant_id: Optional[str] = None


class IssueKeyReq(BaseModel):
    tenant_id: str
    name: str = "default"
    ip_whitelist: List[str] = []


class UpdateQuotaReq(BaseModel):
    rpm_limit: Optional[int] = Field(None, ge=1)
    tpm_limit: Optional[int] = Field(None, ge=1)
    daily_token_cap: Optional[int] = Field(None, ge=1)
    monthly_token_cap: Optional[int] = Field(None, ge=1)


@router.post("/tenants")
async def create_tenant_endpoint(req: CreateTenantReq, session: AsyncSession = Depends(get_session),
                                _=Depends(require_admin)):
    t = await create_tenant(session, req.name, req.tenant_id)
    return {"id": t.id, "name": t.name}


@router.post("/api-keys")
async def issue_key_endpoint(req: IssueKeyReq, session: AsyncSession = Depends(get_session),
                            _=Depends(require_admin)):
    ak, raw = await issue_api_key(session, req.tenant_id, req.name, req.ip_whitelist)
    return {"id": ak.id, "tenant_id": ak.tenant_id, "key": raw, "prefix": ak.key_prefix}


@router.get("/tenants")
async def list_tenants_endpoint(session: AsyncSession = Depends(get_session),
                                _=Depends(require_admin)):
    res = await session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = res.scalars().all()
    if not tenants:
        return []
    ids = [t.id for t in tenants]
    key_rows = await session.execute(
        select(ApiKey.tenant_id, func.count(ApiKey.id))
        .where(ApiKey.tenant_id.in_(ids), ApiKey.is_active.is_(True))
        .group_by(ApiKey.tenant_id)
    )
    keys_by_tenant = {r[0]: r[1] for r in key_rows.all()}
    return [
        {
            "id": t.id,
            "name": t.name,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "active_keys": keys_by_tenant.get(t.id, 0),
        }
        for t in tenants
    ]


@router.get("/api-keys")
async def list_keys_endpoint(tenant_id: Optional[str] = None, session: AsyncSession = Depends(get_session),
                             _=Depends(require_admin)):
    q = select(ApiKey).order_by(ApiKey.created_at.desc())
    if tenant_id:
        q = q.where(ApiKey.tenant_id == tenant_id)
    res = await session.execute(q)
    keys = res.scalars().all()
    return [
        {
            "id": k.id,
            "tenant_id": k.tenant_id,
            "name": k.name,
            "prefix": k.key_prefix,
            "is_active": k.is_active,
            "ip_whitelist": k.ip_whitelist or [],
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        }
        for k in keys
    ]


@router.get("/usage")
async def usage_summary(tenant_id: Optional[str] = None, limit: int = 100, offset: int = 0, session: AsyncSession = Depends(get_session),
                       _=Depends(require_admin)):
    q = select(
        UsageRecord.tenant_id,
        func.count(UsageRecord.id).label("requests"),
        func.coalesce(func.sum(UsageRecord.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(UsageRecord.completion_tokens), 0).label("completion_tokens"),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
    ).group_by(UsageRecord.tenant_id)
    if tenant_id:
        q = q.where(UsageRecord.tenant_id == tenant_id)
    q = q.limit(limit).offset(offset)
    res = await session.execute(q)
    rows = res.all()
    return [
        {
            "tenant_id": r.tenant_id,
            "requests": r.requests,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
        }
        for r in rows
    ]


@router.delete("/api-keys/{key_id}")
async def revoke_key_endpoint(key_id: str, session: AsyncSession = Depends(get_session),
                             _=Depends(require_admin)):
    from gateway.db.models import ApiKey
    from sqlalchemy import update
    res = await session.execute(update(ApiKey).where(ApiKey.id == key_id).values(is_active=False))
    await session.commit()
    if res.rowcount == 0:
        raise HTTPException(404, "key not found")
    return {"id": key_id, "revoked": True}


@router.get("/quotas")
async def list_quotas_endpoint(session: AsyncSession = Depends(get_session),
                               _=Depends(require_admin)):
    res = await session.execute(select(Quota))
    quotas = res.scalars().all()
    if not quotas:
        return []
    tids = [q.tenant_id for q in quotas]
    names = {
        t.id: t.name
        for t in (await session.execute(select(Tenant).where(Tenant.id.in_(tids)))).scalars()
    }

    # Tokens consumed so far today / this month, for the cap progress bars.
    # Same window boundaries as the enforcement check in the proxy.
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    usage_rows = await session.execute(
        select(
            UsageRecord.tenant_id,
            func.coalesce(
                func.sum(case((UsageRecord.created_at >= day_start, UsageRecord.total_tokens), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((UsageRecord.created_at >= month_start, UsageRecord.total_tokens), else_=0)), 0
            ),
        )
        .where(UsageRecord.tenant_id.in_(tids))
        .group_by(UsageRecord.tenant_id)
    )
    usage_by_tenant = {r[0]: (int(r[1]), int(r[2])) for r in usage_rows.all()}

    return [
        {
            "tenant_id": q.tenant_id,
            "tenant_name": names.get(q.tenant_id, q.tenant_id),
            "rpm_limit": q.rpm_limit,
            "tpm_limit": q.tpm_limit,
            "daily_token_cap": q.daily_token_cap,
            "monthly_token_cap": q.monthly_token_cap,
            "daily_tokens_used": usage_by_tenant.get(q.tenant_id, (0, 0))[0],
            "monthly_tokens_used": usage_by_tenant.get(q.tenant_id, (0, 0))[1],
        }
        for q in quotas
    ]


@router.put("/quotas/{tenant_id}")
async def update_quota_endpoint(tenant_id: str, req: UpdateQuotaReq,
                                session: AsyncSession = Depends(get_session),
                                _=Depends(require_admin)):
    q = await get_quota(session, tenant_id)
    if not q:
        raise HTTPException(404, "quota not found")
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "no quota fields supplied")
    # audit only fields that actually change
    changes = {
        f: {"from": getattr(q, f), "to": v}
        for f, v in updates.items()
        if getattr(q, f) != v
    }
    for field, value in updates.items():
        setattr(q, field, value)
    if changes:
        session.add(QuotaAudit(
            id=f"qa_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            changes=changes,
        ))
    await session.commit()
    return {
        "tenant_id": q.tenant_id,
        "rpm_limit": q.rpm_limit,
        "tpm_limit": q.tpm_limit,
        "daily_token_cap": q.daily_token_cap,
        "monthly_token_cap": q.monthly_token_cap,
    }


@router.get("/quota/{tenant_id}")
async def get_quota_endpoint(tenant_id: str, session: AsyncSession = Depends(get_session),
                             _=Depends(require_admin)):
    q = await get_quota(session, tenant_id)
    if not q:
        raise HTTPException(404, "quota not found")
    return {
        "tenant_id": q.tenant_id,
        "rpm_limit": q.rpm_limit,
        "tpm_limit": q.tpm_limit,
        "daily_token_cap": q.daily_token_cap,
        "monthly_token_cap": q.monthly_token_cap,
    }


@router.get("/audit")
async def list_audit_endpoint(limit: int = 50, tenant_id: Optional[str] = None,
                              session: AsyncSession = Depends(get_session),
                              _=Depends(require_admin)):
    """Recent quota changes, newest first."""
    q = select(QuotaAudit)
    if tenant_id:
        q = q.where(QuotaAudit.tenant_id == tenant_id)
    q = q.order_by(QuotaAudit.created_at.desc(), QuotaAudit.id.desc()).limit(
        max(1, min(limit, 200))
    )
    rows = (await session.execute(q)).scalars().all()
    if not rows:
        return []
    tids = list({r.tenant_id for r in rows})
    names = {
        t.id: t.name
        for t in (await session.execute(select(Tenant).where(Tenant.id.in_(tids)))).scalars()
    }
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "tenant_name": names.get(r.tenant_id, r.tenant_id),
            "changes": r.changes or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
