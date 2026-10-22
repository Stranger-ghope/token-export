from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from gateway.auth.middleware import get_current_api_key
from gateway.proxy.router import forward_request, resolve_provider
from gateway.config.logging import log
import uuid

router = APIRouter(prefix="/v1", tags=["proxy"])


@router.post("/chat/completions")
async def chat_completions(request: Request, api_key=Depends(get_current_api_key)):
    request.state.request_id = f"req_{uuid.uuid4().hex[:12]}"
    body = await request.json()
    model = body.get("model", "gpt-4o")
    provider = resolve_provider(model, body.get("provider"))
    stream = bool(body.get("stream", False))
    return await forward_request(request, provider, "chat/completions", body, stream=stream)


@router.post("/completions")
async def completions(request: Request, api_key=Depends(get_current_api_key)):
    request.state.request_id = f"req_{uuid.uuid4().hex[:12]}"
    body = await request.json()
    model = body.get("model", "gpt-4o")
    provider = resolve_provider(model, body.get("provider"))
    stream = bool(body.get("stream", False))
    return await forward_request(request, provider, "completions", body, stream=stream)


@router.post("/embeddings")
async def embeddings(request: Request, api_key=Depends(get_current_api_key)):
    request.state.request_id = f"req_{uuid.uuid4().hex[:12]}"
    body = await request.json()
    model = body.get("model", "text-embedding-3-small")
    provider = resolve_provider(model, body.get("provider"))
    return await forward_request(request, provider, "embeddings", body, stream=False)


@router.post("/messages")
async def messages(request: Request, api_key=Depends(get_current_api_key)):
    """Anthropic-style messages endpoint passthrough."""
    request.state.request_id = f"req_{uuid.uuid4().hex[:12]}"
    body = await request.json()
    model = body.get("model", "claude-3-5-sonnet-20241022")
    provider = "anthropic"
    stream = bool(body.get("stream", False))
    return await forward_request(request, provider, "messages", body, stream=stream)


@router.get("/models")
async def list_models(request: Request, api_key=Depends(get_current_api_key)):
    from gateway.proxy.router import MODEL_PROVIDER
    return {"data": [{"id": m, "object": "model", "owned_by": p} for m, p in MODEL_PROVIDER.items()]}
