"""Alembic environment configuration for async migrations."""

import asyncio
from logging.config import fileConfig
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import every model module so its tables register with Base.metadata before
# `alembic check` compares schema → models. In normal app runtime these modules
# load transitively via app.main → routes → services → repositories, but
# alembic loads only env.py, so without these imports `alembic check` would
# report 9+ "removed table" findings for any model not used elsewhere here.
import app.ai.blueprints.checkpoint_models  # noqa: F401
import app.ai.prompt_store  # noqa: F401  -- defines prompt_templates table
import app.ai.recovery_outcomes  # noqa: F401
import app.ai.routing_history  # noqa: F401
import app.ai.skills.repository  # noqa: F401  -- defines skill_amendments table
import app.ai.templates.models  # noqa: F401
import app.approval.models  # noqa: F401
import app.auth.models  # noqa: F401
import app.briefs.models  # noqa: F401
import app.components.models  # noqa: F401
import app.connectors.models  # noqa: F401
import app.connectors.sync_models  # noqa: F401
import app.design_sync.diagnose.models  # noqa: F401
import app.design_sync.models  # noqa: F401
import app.email_engine.models  # noqa: F401
import app.knowledge.models  # noqa: F401
import app.memory.models  # noqa: F401
import app.personas.models  # noqa: F401
import app.projects.models  # noqa: F401
import app.qa_engine.models  # noqa: F401
import app.rendering.calibration.models  # noqa: F401
import app.rendering.models  # noqa: F401
import app.shared.models  # noqa: F401
import app.streaming.crdt.models  # noqa: F401
import app.templates.models  # noqa: F401
import app.templates.upload.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.core.database import Base

config = context.config

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database.url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _include_object(
    object_: Any,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: ARG001  (alembic API contract)
    compare_to: Any,  # noqa: ARG001
) -> bool:
    """Suppress noisy ``ix_<table>_id`` PK-index findings.

    Postgres auto-creates a btree index on the primary key column; the
    explicit ``ix_<table>_id`` declaration that ``index=True`` produces on
    `Mapped[int] = mapped_column(primary_key=True, index=True)` shows up in
    ``alembic check`` as drift on every table because the auto-PK btree has
    a different name (``<table>_pkey``). Filter it out at compare time.
    """
    if type_ != "index" or name is None:
        return True
    if not (name.startswith("ix_") and name.endswith("_id")):
        return True
    cols = [c.name for c in getattr(object_, "columns", [])]
    if cols == ["id"] and getattr(object_, "unique", False) is False:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
