import asyncio
import os
import pytest
from gateway.db.session import init_db

@pytest.fixture(autouse=True)
def _reset_admin_attempts():
    """The admin API keeps a per-IP brute-force budget (20 calls/min). Clear it
    between tests so the suite never trips its own limiter."""
    from gateway.api.v1.admin import _admin_attempts
    _admin_attempts.clear()
    yield
    _admin_attempts.clear()

@pytest.fixture(scope="session", autouse=True)
def _db():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(init_db())
    finally:
        pass
    yield
    loop.close()
