import hashlib
import secrets
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from gateway.db.models import Tenant, ApiKey, Quota
from gateway.config.settings import settings


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> str:
    return settings.api_key_prefix + secrets.token_urlsafe(32)


async def create_tenant(session: AsyncSession, name: str, tenant_id: Optional[str] = None) -> Tenant:
    import uuid
    tid = tenant_id or f"t_{uuid.uuid4().hex[:12]}"
    tenant = Tenant(id=tid, name=name)
    session.add(tenant)
    quota = Quota(tenant_id=tid, rpm_limit=settings.default_rpm, tpm_limit=settings.default_tpm)
    session.add(quota)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def issue_api_key(session: AsyncSession, tenant_id: str, name: str = "default",
                      ip_whitelist: Optional[list] = None) -> tuple[ApiKey, str]:
    raw = generate_api_key()
    ak = ApiKey(
        id=f"k_{secrets.token_hex(8)}",
        tenant_id=tenant_id,
        key_hash=hash_api_key(raw),
        key_prefix=raw[:8],
        name=name,
        ip_whitelist=ip_whitelist or [],
    )
    session.add(ak)
    await session.commit()
    await session.refresh(ak)
    return ak, raw


async def resolve_api_key(session: AsyncSession, raw_key: str) -> Optional[ApiKey]:
    h = hash_api_key(raw_key)
    res = await session.execute(select(ApiKey).where(ApiKey.key_hash == h, ApiKey.is_active == True))
    ak = res.scalar_one_or_none()
    if ak:
        ak.last_used_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await session.commit()
    return ak


async def get_quota(session: AsyncSession, tenant_id: str) -> Optional[Quota]:
    res = await session.execute(select(Quota).where(Quota.tenant_id == tenant_id))
    return res.scalar_one_or_none()
