from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from gateway.db.session import get_session
from gateway.auth.keys import resolve_api_key, get_quota
from gateway.db.models import ApiKey, Quota
from gateway.config.logging import log

bearer = HTTPBearer(auto_error=False)


async def get_current_api_key(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    raw = None
    if creds and creds.credentials:
        raw = creds.credentials
    if not raw:
        raw = request.headers.get("x-api-key")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    ak = await resolve_api_key(session, raw)
    if not ak:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API key")
    # IP whitelist check
    client_ip = request.client.host if request.client else None
    if ak.ip_whitelist and client_ip and client_ip not in ak.ip_whitelist:
        log.warning("ip_not_whitelisted", ip=client_ip, key=ak.key_prefix)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not whitelisted")
    request.state.api_key = ak
    request.state.quota = await get_quota(session, ak.tenant_id)
    return ak


async def get_quota_dep(request: Request) -> Quota:
    q = getattr(request.state, "quota", None)
    if q is None:
        raise HTTPException(status_code=500, detail="Quota not loaded")
    return q
