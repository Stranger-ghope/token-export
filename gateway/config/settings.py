from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8",
                             case_sensitive=False, extra="ignore")

    app_name: str = "token-gateway"
    app_env: str = "dev"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///./data/gateway.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_fallback_inmemory: bool = True

    # Admin API key (required in prod; dev default in .env.example). When unset,
    # admin endpoints fail closed (503).
    admin_api_key: Optional[str] = None

    # CORS
    cors_origins: str = "*"  # comma-separated list, or "*"

    # Trusted proxies (comma-separated IPs) whose X-Forwarded-For is honored
    trusted_proxies: str = ""

    # Max request body size in bytes (0 = unlimited)
    max_request_body_bytes: int = 1_048_576  # 1 MiB

    jwt_secret: str = Field(default="change-me-in-prod-please-32bytes-min", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    api_key_prefix: str = "tg_"

    upstream_deepseek: str = "https://api.deepseek.com"
    upstream_qwen: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    upstream_openai: str = "https://api.openai.com/v1"
    upstream_anthropic: str = "https://api.anthropic.com/v1"
    upstream_baichuan: str = "https://api.baichuan-ai.com/v1"

    # Server-side provider credentials. When set, the gateway injects them on
    # the outbound request so tenant keys never leave the gateway. When unset,
    # the proxy fails closed with an actionable 503 instead of forwarding the
    # tenant key upstream.
    upstream_api_key_deepseek: Optional[str] = None
    upstream_api_key_qwen: Optional[str] = None
    upstream_api_key_openai: Optional[str] = None
    upstream_api_key_anthropic: Optional[str] = None
    upstream_api_key_baichuan: Optional[str] = None

    pii_masking_enabled: bool = True
    pii_mask_char: str = "*"

    billing_webhook_url: Optional[str] = None
    usage_flush_interval_sec: int = 10

    default_rpm: int = 60
    default_tpm: int = 100000

    # Quota enforcement
    quota_enforcement_enabled: bool = True

    # Cap alert: fire a `cap_alert` billing event (DB + BILLING_WEBHOOK_URL)
    # once per tenant per day when today's tokens reach this share of the
    # daily cap. 0 disables the alert.
    cap_alert_threshold: float = 0.8

settings = Settings()
