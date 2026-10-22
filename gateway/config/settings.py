from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "token-gateway"
    app_env: str = "dev"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///./data/gateway.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_fallback_inmemory: bool = True

    jwt_secret: str = Field(default="change-me-in-prod-please-32bytes-min", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    api_key_prefix: str = "tg_"

    upstream_deepseek: str = "https://api.deepseek.com"
    upstream_qwen: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    upstream_openai: str = "https://api.openai.com/v1"
    upstream_anthropic: str = "https://api.anthropic.com/v1"
    upstream_baichuan: str = "https://api.baichuan-ai.com/v1"

    pii_masking_enabled: bool = True
    pii_mask_char: str = "*"

    billing_webhook_url: Optional[str] = None
    usage_flush_interval_sec: int = 10

    default_rpm: int = 60
    default_tpm: int = 100000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
