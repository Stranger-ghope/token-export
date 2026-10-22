import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from gateway.db.models import Base
from gateway.config.settings import settings

_engine = None
_session_factory = None


async def init_db() -> None:
    global _engine, _session_factory
    os.makedirs("./data", exist_ok=True)
    _engine = create_async_engine(settings.database_url, echo=settings.debug, future=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_engine():
    return _engine


def get_session_factory():
    return _session_factory


async def get_session() -> AsyncSession:
    if _session_factory is None:
        await init_db()
    async with _session_factory() as session:
        yield session
