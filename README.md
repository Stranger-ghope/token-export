# AI Token Export / Routing Gateway

High-performance, low-latency, cross-border proxy gateway for AI model token requests
(DeepSeek, Qwen, Baichuan, OpenAI, Anthropic). Multi-tenant API keys, rate limiting,
usage-based billing, BPE token optimization, PII anonymization, SSE streaming.

## Stack
- Python 3.12, FastAPI, Uvicorn (async)
- SQLAlchemy 2 (async) + SQLite (dev) / Postgres (prod)
- Redis (optional; in-memory fallback for dev)
- tiktoken for BPE token estimation
- Prometheus metrics, structlog JSON logging

## Quick start
```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn gateway.main:app --host 0.0.0.0 --port 8080
```

## Endpoints
- `POST /v1/chat/completions` (OpenAI-compatible, supports stream=true)
- `POST /v1/completions`, `/v1/embeddings`, `/v1/messages` (Anthropic-style)
- `GET  /v1/models`
- `POST /admin/tenants`, `POST /admin/api-keys`
- `GET  /admin/usage`, `GET /admin/quota/{tenant_id}`
- `POST /tools/pii/mask`, `/tools/tokens/count`, `/tools/tokens/compress`
- `GET  /health`, `/metrics`

## Auth
Pass API key via `Authorization: Bearer <key>` or `X-API-Key` header.

## Features
- Dynamic provider routing by model name + optional `provider` override
- Failover-ready upstream client with timeout handling (CN provider timeouts, drops)
- SSE streaming passthrough (no buffering) with `X-Accel-Buffering: no`
- Per-tenant RPM/TPM rate limiting + IP whitelisting
- Real-time token usage tracking (prompt + completion) + BPE compression logs
- Usage-based billing events + optional webhook
- PII masking/anonymization pipeline on outbound + inbound payloads
- Prometheus metrics & structured JSON logs
