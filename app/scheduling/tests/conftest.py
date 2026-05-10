"""Fixtures for scheduling engine tests."""

from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest

from app.core.config import SchedulingConfig
from app.scheduling.registry import clear_registry


@pytest.fixture(autouse=True)
def _clear_job_registry() -> Generator[None]:
    """Clear the job registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


@pytest.fixture()
def mock_redis() -> AsyncMock:
    """Create a mock Redis client with common scheduling methods."""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.exists = AsyncMock(return_value=0)
    redis.hset = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hincrby = AsyncMock()
    redis.lpush = AsyncMock()
    redis.ltrim = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    redis.expire = AsyncMock()
    redis.delete = AsyncMock()
    # Lua CAS release returns 1 (we owned the lock and released it).
    redis.eval = AsyncMock(return_value=1)

    # scan_iter as an async generator
    async def _empty_scan_iter(match: str = "*") -> AsyncGenerator[bytes]:
        return
        yield  # pragma: no cover

    redis.scan_iter = _empty_scan_iter
    return redis


@pytest.fixture()
def scheduling_config() -> SchedulingConfig:
    """Create a test scheduling config with short intervals."""
    return SchedulingConfig(
        enabled=True,
        check_interval_seconds=1,
        job_timeout_seconds=5,
        max_run_history=10,
        run_history_ttl_seconds=60,
    )
