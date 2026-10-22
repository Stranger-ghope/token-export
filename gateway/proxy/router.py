import time
import uuid
import json
from typing import AsyncIterator, Optional
import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from gateway.config.settings import settings
from gateway.config.logging import log
from gateway.billing.token_calc import count_tokens, count_messages_tokens, bpe_compress_estimate
from gateway.security.pii import mask_pii_obj

PROVIDER_BASE = {
    "deepseek": settings.upstream_deepseek,
    "qwen": settings.upstream_qwen,
    "openai": settings.upstream_openai,
    "anthropic": settings.upstream_anthropic,
    "baichuan": settings.upstream_baichuan,
}

# Model -> provider routing
MODEL_PROVIDER = {
    "deepseek-chat": "deepseek",
    "deepseek-reasoner": "deepseek",
    "qwen-max": "qwen",
    "qwen-plus": "qwen",
    "qwen-turbo": "qwen",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4.1": "openai",
    "claude-3-5-sonnet-20241022": "anthropic",
    "claude-3-opus-20240229": "anthropic",
    "Baichuan4": "baichuan",
    "Baichuan3-Turbo": "baichuan",
}


def resolve_provider(model: str, explicit: Optional[str] = None) -> str:
    if explicit and explicit in PROVIDER_BASE:
        return explicit
    return MODEL_PROVIDER.get(model, "openai")


def build_upstream_url(provider: str, path: str) -> str:
    base = PROVIDER_BASE[provider].rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}"


async def forward_request(
    request: Request,
    provider: str,
    path: str,
    body: dict,
    stream: bool = False,
) -> Response:
    request_id = getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:12]}"
    request.state.request_id = request_id
    start = time.time()

    # PII masking on outbound payload
    if settings.pii_masking_enabled:
        body = mask_pii_obj(body)

    # Token estimation for billing / rate limiting
    messages = body.get("messages", [])
    model = body.get("model", "gpt-4o")
    prompt_tokens = count_messages_tokens(messages, model) if messages else count_tokens(
        body.get("prompt", "") or body.get("input", "") or "", model
    )
    bpe_info = bpe_compress_estimate(
        " ".join(m.get("content", "") if isinstance(m.get("content"), str) else "" for m in messages),
        model,
    )

    # rate limit estimated tokens
    from gateway.middleware.rate_limit import rate_limit_check, get_limiter
    await rate_limit_check(request, estimated_tokens=prompt_tokens)

    url = build_upstream_url(provider, path)
    headers = {}
    # Forward auth: prefer provider key from env? For demo, pass through client Authorization
    # and add provider-specific headers.
    for h in ("authorization", "content-type", "accept", "x-api-key", "anthropic-version", "anthropic-beta"):
        v = request.headers.get(h)
        if v:
            headers[h] = v

    # If no authorization provided, inject a placeholder note (demo mode)
    if "authorization" not in {k.lower() for k in headers} and "x-api-key" not in {k.lower() for k in headers}:
        log.warning("no_upstream_creds", provider=provider)

    timeout = httpx.Timeout(120.0, connect=10.0, read=120.0, write=30.0)

    if stream:
        return await _stream_response(request, url, headers, body, provider, model, prompt_tokens, bpe_info, request_id, start)

    # Non-streaming
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException:
            log.error("upstream_timeout", provider=provider, url=url)
            return JSONResponse(status_code=504, content={"error": "upstream timeout"})
        except httpx.ConnectError as e:
            log.error("upstream_connect_error", provider=provider, error=str(e))
            return JSONResponse(status_code=502, content={"error": "upstream unreachable"})

    latency_ms = (time.time() - start) * 1000
    # Parse usage from response
    completion_text = ""
    usage = {}
    try:
        data = resp.json()
        usage = data.get("usage", {}) or {}
        choices = data.get("choices", [])
        if choices:
            completion_text = choices[0].get("message", {}).get("content", "") or ""
    except Exception:
        data = {"raw": resp.text}

    pt = usage.get("prompt_tokens", prompt_tokens)
    ct = usage.get("completion_tokens", 0)
    if ct == 0 and completion_text:
        ct = count_tokens(completion_text, model)

    # record usage
    try:
        from gateway.db.session import get_session_factory
        from gateway.billing.tracker import record_usage, emit_billing_event
        sf = get_session_factory()
        async with sf() as session:
            ak = getattr(request.state, "api_key", None)
            await record_usage(
                session=session,
                tenant_id=ak.tenant_id if ak else "unknown",
                api_key_id=ak.id if ak else None,
                request_id=request_id,
                provider=provider,
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                bpe_prompt=bpe_info["bpe_tokens"],
                bpe_completion=count_tokens(completion_text, model) if completion_text else 0,
                compression_ratio=bpe_info["ratio"],
                latency_ms=latency_ms,
                status_code=resp.status_code,
            )
            await emit_billing_event(session, ak.tenant_id if ak else "unknown", "usage", {
                "request_id": request_id, "provider": provider, "model": model,
                "prompt_tokens": pt, "completion_tokens": ct,
            })
    except Exception as e:
        log.warning("usage_record_failed", error=str(e))

    # PII mask response
    if settings.pii_masking_enabled:
        if isinstance(data, dict):
            data = mask_pii_obj(data)

    return Response(
        content=json.dumps(data).encode(),
        status_code=resp.status_code,
        media_type="application/json",
        headers={"x-request-id": request_id, "x-latency-ms": f"{latency_ms:.1f}"},
    )


async def _stream_response(
    request: Request,
    url: str,
    headers: dict,
    body: dict,
    provider: str,
    model: str,
    prompt_tokens: int,
    bpe_info: dict,
    request_id: str,
    start: float,
) -> StreamingResponse:
    async def event_generator() -> AsyncIterator[bytes]:
        completion_chunks = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            try:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code >= 400:
                        err = await resp.aread()
                        yield f"data: {err.decode(errors='replace')}\n\n".encode()
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        # SSE passthrough
                        if settings.pii_masking_enabled and line.startswith("data:"):
                            # mask inside data payload best-effort
                            payload = line[5:].strip()
                            if payload and payload != "[DONE]":
                                try:
                                    obj = json.loads(payload)
                                    # mask content deltas
                                    choices = obj.get("choices", [])
                                    for c in choices:
                                        delta = c.get("delta", {})
                                        if "content" in delta and isinstance(delta["content"], str):
                                            delta["content"] = mask_pii_obj(delta["content"], settings.pii_mask_char)
                                    line = "data: " + json.dumps(obj)
                                except Exception:
                                    line = "data: " + mask_pii_obj(payload, settings.pii_mask_char)
                        yield (line + "\n").encode()
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            if payload and payload != "[DONE]":
                                try:
                                    obj = json.loads(payload)
                                    ch = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if ch:
                                        completion_chunks.append(ch)
                                except Exception:
                                    pass
                        yield b"\n"
            except httpx.TimeoutException:
                yield b"data: {\"error\":\"upstream timeout\"}\n\n"
            except httpx.ConnectError as e:
                yield f"data: {{\"error\":\"upstream unreachable: {e}\"}}\n\n".encode()
        # After stream ends, record usage
        completion_text = "".join(completion_chunks)
        ct = count_tokens(completion_text, model) if completion_text else 0
        latency_ms = (time.time() - start) * 1000
        try:
            from gateway.db.session import get_session_factory
            from gateway.billing.tracker import record_usage, emit_billing_event
            sf = get_session_factory()
            async with sf() as session:
                ak = getattr(request.state, "api_key", None)
                await record_usage(
                    session=session,
                    tenant_id=ak.tenant_id if ak else "unknown",
                    api_key_id=ak.id if ak else None,
                    request_id=request_id,
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=ct,
                    bpe_prompt=bpe_info["bpe_tokens"],
                    bpe_completion=count_tokens(completion_text, model) if completion_text else 0,
                    compression_ratio=bpe_info["ratio"],
                    latency_ms=latency_ms,
                    status_code=200,
                )
        except Exception as e:
            log.warning("stream_usage_record_failed", error=str(e))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "x-request-id": request_id,
        },
    )
