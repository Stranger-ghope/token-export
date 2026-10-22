# AI Token Export / Routing Gateway — Architecture

## Overview
Cross-border proxy bridge routing AI token requests between providers (DeepSeek, Qwen,
Baichuan, OpenAI, Anthropic) and enterprise clients, with multi-tenant auth, rate limiting,
usage billing, BPE token optimization, PII anonymization, and SSE streaming.

## Directory structure
```
token-gateway/
├── gateway/
│   ├── main.py                 # FastAPI app, middleware, routes
│   ├── config/
│   │   ├── settings.py         # pydantic-settings env config
│   │   └── logging.py          # structlog setup
│   ├── db/
│   │   ├── models.py           # SQLAlchemy ORM (tenants, api_keys, quotas, usage, billing)
│   │   └── session.py          # async engine + session factory
│   ├── auth/
│   │   ├── keys.py             # API key issuance / hashing / resolution
│   │   └── middleware.py       # FastAPI dependency: bearer/x-api-key, IP whitelist
│   ├── middleware/
│   │   └── rate_limit.py       # RPM/TPM limiter (in-memory; Redis-ready)
│   ├── proxy/
│   │   └── router.py           # upstream forwarding, SSE streaming, failover
│   ├── billing/
│   │   ├── token_calc.py       # tiktoken BPE counting, compression, allocation
│   │   └── tracker.py          # usage record + billing events + webhook
│   ├── security/
│   │   └── pii.py              # regex PII masking (email/phone/id/CC/IP)
│   └── api/v1/
│       ├── proxy.py            # /v1/* OpenAI-compatible endpoints
│       ├── admin.py            # tenant/key/usage/quota management
│       └── tools.py            # PII + token utilities
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

## Data flow
1. Client -> `/v1/chat/completions` with Bearer API key
2. Auth middleware resolves tenant + quota + IP whitelist
3. Rate limiter checks RPM/TPM (in-memory or Redis)
4. PII masking applied to outbound payload
5. BPE token count estimated for billing + dynamic allocation
6. Upstream forwarded (stream or non-stream) with timeout handling
7. Usage recorded (prompt + completion + BPE + compression ratio)
8. Billing event emitted (+ optional webhook)
9. PII masking applied to response
10. Prometheus metrics + structured logs

## Production hardening (next steps)
- Swap in-memory rate limiter for Redis (sliding window)
- Add upstream failover across multiple nodes per provider
- Replace regex PII with NER model pipeline
- Add circuit breaker + retry with exponential backoff
- Postgres + connection pooling
- JWT admin auth (currently open admin endpoints — gate behind auth in prod)
EOF
echo done