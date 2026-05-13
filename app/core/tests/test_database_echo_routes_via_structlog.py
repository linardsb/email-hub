"""F059 — assert SQLAlchemy echo logs go through structlog (and therefore redaction)."""

import logging
from unittest.mock import patch

from app.core.database import (
    _route_sqlalchemy_to_structlog,
    _StructlogBridgeHandler,
)


def test_route_sqlalchemy_to_structlog_attaches_bridge_handler() -> None:
    sa_logger = logging.getLogger("sqlalchemy.engine")
    original_handlers = sa_logger.handlers[:]
    original_propagate = sa_logger.propagate
    try:
        sa_logger.handlers.clear()
        sa_logger.propagate = True

        _route_sqlalchemy_to_structlog()

        assert any(isinstance(h, _StructlogBridgeHandler) for h in sa_logger.handlers)
        assert sa_logger.propagate is False
    finally:
        sa_logger.handlers[:] = original_handlers
        sa_logger.propagate = original_propagate


def test_route_sqlalchemy_to_structlog_is_idempotent() -> None:
    sa_logger = logging.getLogger("sqlalchemy.engine")
    original_handlers = sa_logger.handlers[:]
    original_propagate = sa_logger.propagate
    try:
        sa_logger.handlers.clear()

        _route_sqlalchemy_to_structlog()
        _route_sqlalchemy_to_structlog()

        bridge_count = sum(1 for h in sa_logger.handlers if isinstance(h, _StructlogBridgeHandler))
        assert bridge_count == 1
    finally:
        sa_logger.handlers[:] = original_handlers
        sa_logger.propagate = original_propagate


def test_bridge_handler_emits_via_structlog() -> None:
    handler = _StructlogBridgeHandler()
    record = logging.LogRecord(
        name="sqlalchemy.engine",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="SELECT user_email FROM users WHERE id = ?",
        args=(),
        exc_info=None,
    )

    with patch("app.core.database.get_logger") as mock_get_logger:
        mock_logger = mock_get_logger.return_value
        handler.emit(record)

    mock_get_logger.assert_called_once_with("sqlalchemy.engine")
    mock_logger.info.assert_called_once_with(
        "sqlalchemy.engine.echo",
        message="SELECT user_email FROM users WHERE id = ?",
        level="INFO",
    )
