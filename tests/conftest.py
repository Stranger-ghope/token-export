import asyncio
import os
import pytest
from gateway.db.session import init_db

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
