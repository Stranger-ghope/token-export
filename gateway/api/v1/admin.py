from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from gateway.auth.middleware import get_current_api_key
from gateway.db.session import get_session
from gateway.auth.keys import create_tenant, issue_api_key, get_quota
from gateway.db.models import Tenant, ApiKey, Quota, UsageRecord, BillingEvent
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateTenantReq(BaseModel):
    name: str
    tenant_id: Optional[str] = None


class IssueKeyReq(BaseModel):
    tenant_id: str
    name: str = "default"
    ip_whitelist: List[str] = []


@router.post("/tenants")
async def create_tenant_endpoint(req: CreateTenantReq, session: AsyncSession = Depends(get_session)):
    t = await create_tenant(session, req.name, req.tenant_id)
    return {"id": t.id, "name": t.name}


@router.post("/api-keys")
async def issue_key_endpoint(req: IssueKeyReq, session: AsyncSession = Depends(get_session)):
    ak, raw = await issue_api_key(session, req.tenant_id, req.name, req.ip_whitelist)
    return {"id": ak.id, "tenant_id": ak.tenant_id, "key": raw, "prefix": ak.key_prefix}


@router.get("/usage")
async def usage_summary(tenant_id: Optional[str] = None, session: AsyncSession = Depends(get_session)):
    q = select(
        UsageRecord.tenant_id,
        func.count(UsageRecord.id).label("requests"),
        func.coalesce(func.sum(UsageRecord.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(UsageRecord.completion_tokens), 0).label("completion_tokens"),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
    ).group_by(UsageRecord.tenant_id)
    if tenant_id:
        q = q.where(UsageRecord.tenant_id == tenant_id)
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


@router.get("/quota/{tenant_id}")
async def get_quota_endpoint(tenant_id: str, session: AsyncSession = Depends(get_session)):
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
