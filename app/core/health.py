# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false
"""Health check endpoints for monitoring application and database status."""

import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.redis import get_redis

logger = get_logger(__name__)

# Cached health results to prevent connection pool exhaustion
_db_health_cache: dict[str, str] | None = None
_db_health_cache_time: float = 0.0
_DB_HEALTH_CACHE_TTL: float = 10.0

_redis_health_cache: dict[str, str] | None = None
_redis_health_cache_time: float = 0.0
_REDIS_HEALTH_CACHE_TTL: float = 10.0

router = APIRouter(tags=["health"])


@router.get("/health")
@limiter.limit("60/minute")
async def health_check(request: Request) -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "api"}


@router.get("/health/db")
@limiter.limit("60/minute")
async def database_health_check(
    request: Request,
    db: AsyncSession = Depends(get_db),  # tenant-exempt: /health has no caller identity
) -> dict[str, str]:
    """Database connectivity health check with 10s result caching."""
    global _db_health_cache, _db_health_cache_time
    now = time.monotonic()
    if _db_health_cache is not None and (now - _db_health_cache_time) < _DB_HEALTH_CACHE_TTL:
        return _db_health_cache

    try:
        await db.execute(text("SELECT 1"))
        result = {"status": "healthy", "service": "database"}
        _db_health_cache = result
        _db_health_cache_time = now
        return result
    except Exception as exc:
        _db_health_cache = None
        logger.error("database.health_check_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not accessible",
        ) from exc


@router.get("/health/redis")
@limiter.limit("60/minute")
async def health_redis(request: Request) -> dict[str, str]:
    """Redis health check with 10s result caching."""
    global _redis_health_cache, _redis_health_cache_time
    now = time.monotonic()
    if (
        _redis_health_cache is not None
        and (now - _redis_health_cache_time) < _REDIS_HEALTH_CACHE_TTL
    ):
        return _redis_health_cache
    try:
        redis_client = await get_redis()
        result = await redis_client.ping()
        if not result:
            raise HTTPException(status_code=503, detail="Redis ping failed")
        _redis_health_cache = {"status": "healthy", "service": "redis"}
        _redis_health_cache_time = now
        return _redis_health_cache
    except HTTPException:
        raise
    except Exception as e:
        logger.error("redis.health_check_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=503, detail="Service dependency unavailable") from e


@router.get("/health/ready")
@limiter.limit("60/minute")
async def readiness_check(
    request: Request,
    db: AsyncSession = Depends(get_db),  # tenant-exempt: /health/ready has no caller identity
) -> dict[str, str]:
    """Readiness check for all application dependencies."""
    settings = get_settings()

    try:
        await db.execute(text("SELECT 1"))

        redis_status = "connected"
        try:
            redis_client = await get_redis()
            if not await redis_client.ping():
                redis_status = "unhealthy"
        except Exception:
            redis_status = "unavailable"

        _ = settings
        return {
            "status": "ready",
            "database": "connected",
            "redis": redis_status,
        }
    except Exception as exc:
        logger.error("health.readiness_check_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application is not ready",
        ) from exc
