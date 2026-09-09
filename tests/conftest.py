import pytest
from app.core.database import engine

@pytest.fixture(autouse=True)
async def cleanup_engine():
    yield
    await engine.dispose()
