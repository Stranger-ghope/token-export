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

## Admin console (UI)
A React + Vite console with light/dark theme lives in `frontend/` — overview,
tenants & API keys, usage, and a streaming playground. FastAPI serves the built
app on the same origin as the API.

```bash
cd frontend && npm install && npm run build   # build once
uvicorn gateway.main:app --host 0.0.0.0 --port 8080
# open http://localhost:8080
```

First run: click **Set admin key** (top bar) and enter `ADMIN_API_KEY` from `.env`.

Hot-reload development (Vite proxies `/v1`, `/admin`, `/health` to `:8080`):

```bash
cd frontend && npm run dev    # http://localhost:5173
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

Provider credentials live **server-side**: set `UPSTREAM_API_KEY_DEEPSEEK`,
`UPSTREAM_API_KEY_QWEN`, `UPSTREAM_API_KEY_OPENAI`, `UPSTREAM_API_KEY_ANTHROPIC`,
`UPSTREAM_API_KEY_BAICHUAN` in `.env`. The gateway injects them on the outbound
request (Bearer for OpenAI-compatible providers, `x-api-key` for Anthropic), so
tenant keys never leave the gateway. Without a key the proxy answers `503` with
the exact env var to set.

## Features
- Dynamic provider routing by model name + optional `provider` override
- Failover-ready upstream client with timeout handling (CN provider timeouts, drops)
- SSE streaming passthrough (no buffering) with `X-Accel-Buffering: no`
- Per-tenant RPM/TPM rate limiting + IP whitelisting
- Real-time token usage tracking (prompt + completion) + BPE compression logs
- Usage-based billing events + optional webhook
- PII masking/anonymization pipeline on outbound + inbound payloads
- Prometheus metrics & structured JSON logs
