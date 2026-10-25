# MVP Status & Known Limitations

Last updated: 2026-10-25 · branch `master` · console + upstream credentials + Redis rate limiting

## What this MVP delivers (demo-ready)

- OpenAI-compatible proxy: `POST /v1/chat/completions` (stream + non-stream), `/v1/completions`,
  `/v1/embeddings`, `/v1/messages` (Anthropic-style), `GET /v1/models`
- SSE streaming passthrough with `X-Accel-Buffering: no` and upstream timeout handling
- Multi-tenant auth: tenant + API key issuance, SHA-256 hashed keys, IP whitelist
- Per-tenant RPM/TPM rate limiting, usage recording, billing events (+ optional webhook)
- PII masking on outbound + inbound payloads and SSE deltas (regex-based)
- BPE token counting (tiktoken) + `/tools/*` utilities
- Prometheus `/metrics`, structlog JSON logs, `/health`
- Admin console (React + Vite, light/dark) served by FastAPI at `/`: overview,
  tenants & API keys, quota limits, usage, streaming playground
- Server-side upstream credentials (`UPSTREAM_API_KEY_*`) — tenant keys are never
  forwarded to providers; unconfigured providers fail closed with an actionable 503
- Quota management: list caps + usage-vs-cap, `PUT /admin/quotas/{tenant_id}` to edit,
  and a `quota_audit` table (before/after) surfaced in the console
- Daily-cap alert: `cap_alert` billing event (+ `BILLING_WEBHOOK_URL` webhook) fired once
  per tenant per day at `CAP_ALERT_THRESHOLD` of the daily cap
- CI: pytest + console build + Docker image build on every push; image pushed to
  `ghcr.io/<owner>/<repo>/gateway` on `v*` tags

## Security (hardened in this pass)

- `/admin/*` now requires an admin key (`ADMIN_API_KEY`, sent via `Authorization: Bearer`
  or `X-Admin-Key`). Fails closed (503) if unset.
- `/tools/*` now requires a valid tenant API key.
- CORS no longer combines `allow_origins=["*"]` with `allow_credentials=True`.

## Known limitations (NOT production-ready)

1. ~~Rate limiter is in-memory per process.~~ **RESOLVED:** Redis is the primary backend
   (counters shared across workers/instances). `REDIS_FALLBACK_INMEMORY=true` falls back to the
   per-process limiter only when Redis is unreachable; `false` fails closed with a 503 instead of
   silently allowing unlimited traffic. Live Redis is not exercised in the test suite (the shared
   logic is covered with fakeredis).
2. No retry / backoff / circuit breaker on upstream calls (single attempt, then 504/502).
3. No pricing model — `BillingEvent` records usage only; no per-token cost or invoices.
4. "BPE compression ratio" is a heuristic (bpe_tokens vs chars/4), not actual payload compression.
5. PII masking is regex-based (email/phone/id/CC/IP). No NER; expect false positives/negatives.
6. Quota columns (`daily_token_cap`, `monthly_token_cap`) exist but are not enforced yet.
7. SQLite default; Postgres supported via `DATABASE_URL` but no migrations (schema = `create_all`).
   Use a single DB volume and back it up.
8. No request body size limits / input validation beyond FastAPI defaults.
9. Admin auth is a single shared key, not per-user JWT. Rotate via env; not for multi-admin use.
10. Tests: 23 (proxy path, streaming, auth, admin/quota/audit endpoints, cap alerts,
    upstream credential injection, rate-limit backends). The Docker image builds in CI but
    no test calls a real upstream provider, and webhook delivery is only exercised when
    `BILLING_WEBHOOK_URL` points at a live receiver.

## Deployment

- `Dockerfile` + `docker-compose.yml` (app + postgres + redis) provided.
- Copy `.env.example` → `.env`, set `ADMIN_API_KEY`, `JWT_SECRET`, provider URLs, and
  `CORS_ORIGINS` (comma-separated, or `*` for dev).

## Recommended next steps before client delivery

1. ~~Wire Redis sliding-window rate limiter~~ — done (see limitation 1).
2. Add quota enforcement + Alembic migrations + backup story.
3. ~~Add proxy/streaming/auth tests and a CI pipeline~~ — done (18 tests, GitHub Actions).
4. Decide product scope with client: gateway is one component; the compute revenue-share /
   vertical SaaS business logic described in the research docs is not implemented here.
5. Build the Docker image in CI, and exercise one real upstream provider call in a staging run.
