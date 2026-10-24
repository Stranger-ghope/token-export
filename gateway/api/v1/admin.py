from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from gateway.config.settings import settings
from gateway.db.session import get_session
from gateway.auth.keys import create_tenant, issue_api_key, get_quota
from gateway.db.models import Tenant, ApiKey, Quota, UsageRecord, BillingEvent
from sqlalchemy import select, func
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
