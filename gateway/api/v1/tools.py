from fastapi import APIRouter, Request, Depends
from gateway.auth.middleware import get_current_api_key
from gateway.security.pii import mask_pii_text, pii_stats
from gateway.billing.token_calc import bpe_compress_estimate, count_tokens

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(get_current_api_key)])


@router.post("/pii/mask")
async def pii_mask(request: Request, api_key=Depends(get_current_api_key)):
    body = await request.json()
    text = body.get("text", "")
    return {"masked": mask_pii_text(text), "stats": pii_stats(text)}


@router.post("/tokens/count")
async def tokens_count(request: Request, api_key=Depends(get_current_api_key)):
    body = await request.json()
    text = body.get("text", "")
    model = body.get("model", "gpt-4o")
    return {"tokens": count_tokens(text, model), "bpe": bpe_compress_estimate(text, model)}


@router.post("/tokens/compress")
async def tokens_compress(request: Request, api_key=Depends(get_current_api_key)):
    body = await request.json()
    text = body.get("text", "")
    model = body.get("model", "gpt-4o")
    return bpe_compress_estimate(text, model)
