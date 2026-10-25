from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def now_utc():
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    is_active = Column(Boolean, default=True)
    api_keys = relationship("ApiKey", back_populates="tenant", cascade="all, delete-orphan")
    quotas = relationship("Quota", back_populates="tenant", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False, index=True)
    key_hash = Column(String(128), nullable=False, unique=True, index=True)
    key_prefix = Column(String(16), nullable=False)
    name = Column(String(255), default="default")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    ip_whitelist = Column(JSON, default=list)
    tenant = relationship("Tenant", back_populates="api_keys")
    __table_args__ = (Index("ix_api_keys_tenant_active", "tenant_id", "is_active"),)


class Quota(Base):
    __tablename__ = "quotas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False, index=True)
    rpm_limit = Column(Integer, default=60)
    tpm_limit = Column(Integer, default=100000)
    daily_token_cap = Column(Integer, default=10_000_000)
    monthly_token_cap = Column(Integer, default=100_000_000)
    tenant = relationship("Tenant", back_populates="quotas")


class UsageRecord(Base):
    __tablename__ = "usage_records"
    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False, index=True)
    api_key_id = Column(String(64), ForeignKey("api_keys.id"), nullable=True, index=True)
    request_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    bpe_prompt_tokens = Column(Integer, default=0)
    bpe_completion_tokens = Column(Integer, default=0)
    compression_ratio = Column(Float, default=1.0)
    latency_ms = Column(Float, default=0.0)
    status_code = Column(Integer, default=200)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
    metadata_json = Column(JSON, default=dict)
    __table_args__ = (Index("ix_usage_tenant_created", "tenant_id", "created_at"),)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSON, default=dict)
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class QuotaAudit(Base):
    """Who changed which quota, with before/after values."""
    __tablename__ = "quota_audit"
    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), ForeignKey("tenants.id"), nullable=False, index=True)
    changes = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
