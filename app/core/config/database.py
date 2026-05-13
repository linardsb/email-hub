"""Database connection settings."""

from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """Database connection settings."""

    url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/email_hub"
    pool_size: int = Field(default=20, ge=1)
    pool_max_overflow: int = Field(default=20, ge=0)
    pool_recycle: int = 1800
    # When True, SQLAlchemy SQL logs are routed through structlog so
    # `redact_event_dict` still applies (see `_route_sqlalchemy_to_structlog`
    # in `app/core/database.py`). Default off to minimise log volume.
    echo: bool = False


class RedisConfig(BaseModel):
    """Redis connection settings."""

    url: str = "redis://localhost:6379/0"
