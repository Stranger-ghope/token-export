# MVP Status & Known Limitations

Last updated: 2026-10-22 · branch `master` · commit `35a7e28` + security hardening

## What this MVP delivers (demo-ready)

- OpenAI-compatible proxy: `POST /v1/chat/completions` (stream + non-stream), `/v1/completions`,
  `/v1/embeddings`, `/v1/messages` (Anthropic-style), `GET /v1/models`
- SSE streaming passthrough with `X-Accel-Buffering: no` and upstream timeout handling
- Multi-tenant auth: tenant + API key issuance, SHA-256 hashed keys, IP whitelist
- Per-tenant RPM/TPM rate limiting, usage recording, billing events (+ optional webhook)
- PII masking on outbound + inbound payloads and SSE deltas (regex-based)
- BPE token counting (tiktoken) + `/tools/*` utilities
- Prometheus `/metrics`, structlog JSON logs, `/health`

## Security (hardened in this pass)

- `/admin/*` now requires an admin key (`ADMIN_API_KEY`, sent via `Authorization: Bearer`
  or `X-Admin-Key`). Fails closed (503) if unset.
- `/tools/*` now requires a valid tenant API key.
- CORS no longer combines `allow_origins=["*"]` with `allow_credentials=True`.

## Known limitations (NOT production-ready)

1. Rate limiter is **in-memory per process**. Redis is configured but not wired; do not run
   multiple workers/instances expecting shared limits. Either wire Redis or run a single worker.
2. No retry / backoff / circuit breaker on upstream calls (single attempt, then 504/502).
3. No pricing model — `BillingEvent` records usage only; no per-token cost or invoices.
4. "BPE compression ratio" is a heuristic (bpe_tokens vs chars/4), not actual payload compression.
5. PII masking is regex-based (email/phone/id/CC/IP). No NER; expect false positives/negatives.
6. Quota columns (`daily_token_cap`, `monthly_token_cap`) exist but are not enforced yet.
7. SQLite default; Postgres supported via `DATABASE_URL` but no migrations (schema = `create_all`).
   Use a single DB volume and back it up.
8. No request body size limits / input validation beyond FastAPI defaults.
9. Admin auth is a single shared key, not per-user JWT. Rotate via env; not for multi-admin use.
10. Tests: 4 smoke tests only. No proxy-path, streaming, or auth tests.

## Deployment

- `Dockerfile` + `docker-compose.yml` (app + postgres + redis) provided.
- Copy `.env.example` → `.env`, set `ADMIN_API_KEY`, `JWT_SECRET`, provider URLs, and
  `CORS_ORIGINS` (comma-separated, or `*` for dev).

## Recommended next steps before client delivery

1. Wire Redis sliding-window rate limiter (or remove the Redis claim from README).
2. Add quota enforcement + Alembic migrations + backup story.
3. Add proxy/streaming/auth tests and a CI pipeline.
4. Decide product scope with client: gateway is one component; the compute revenue-share /
   vertical SaaS business logic described in the research docs is not implemented here.
