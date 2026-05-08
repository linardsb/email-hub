"""Tests for Plan 02 Part C — JWT decode strictness, refresh TTL config-flow, revocation fail-open log."""

import datetime
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest

from app.auth.token import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_token_revoked,
)

_SECRET = "test-secret"


@pytest.fixture
def mock_token_settings() -> Iterator[MagicMock]:
    """Patch app.auth.token.get_settings with deterministic auth config."""
    with patch("app.auth.token.get_settings") as mock:
        mock.return_value.auth.jwt_secret_key = _SECRET
        mock.return_value.auth.access_token_expire_minutes = 30
        mock.return_value.auth.refresh_token_expire_days = 7
        yield mock


def _encode(payload: dict[str, Any]) -> str:
    # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret,python.jwt.security.audit.jwt-exposed-data.jwt-python-exposed-data
    # _SECRET is a test-only constant patched into get_settings via mock_token_settings;
    # never reaches a real auth path. Payload is also test-synthesized.
    # Alerts #156 + #157 dismissed as false positive (test code).
    return pyjwt.encode(payload, _SECRET, algorithm="HS256")


# ── C1d: decode_token rejects tokens missing required claims ──


@pytest.mark.usefixtures("mock_token_settings")
def test_decode_rejects_token_without_jti() -> None:
    token = _encode({"sub": "1", "role": "admin", "iat": 1, "exp": 9999999999, "type": "access"})
    assert decode_token(token) is None


@pytest.mark.usefixtures("mock_token_settings")
def test_decode_rejects_token_without_exp() -> None:
    token = _encode({"sub": "1", "role": "admin", "iat": 1, "type": "access", "jti": "abc"})
    assert decode_token(token) is None


@pytest.mark.usefixtures("mock_token_settings")
def test_decode_rejects_token_without_iat() -> None:
    token = _encode(
        {"sub": "1", "role": "admin", "exp": 9999999999, "type": "access", "jti": "abc"}
    )
    assert decode_token(token) is None


# ── C1d: token creators emit iat ──


@pytest.mark.usefixtures("mock_token_settings")
def test_create_access_token_emits_iat() -> None:
    before = datetime.datetime.now(datetime.UTC)
    token = create_access_token(user_id=1, role="admin")
    after = datetime.datetime.now(datetime.UTC)

    payload = pyjwt.decode(token, _SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert "iat" in payload
    iat = datetime.datetime.fromtimestamp(payload["iat"], tz=datetime.UTC)
    assert before - datetime.timedelta(seconds=2) <= iat <= after + datetime.timedelta(seconds=2)


@pytest.mark.usefixtures("mock_token_settings")
def test_create_refresh_token_emits_iat() -> None:
    before = datetime.datetime.now(datetime.UTC)
    token = create_refresh_token(user_id=1)
    after = datetime.datetime.now(datetime.UTC)

    payload = pyjwt.decode(token, _SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert "iat" in payload
    iat = datetime.datetime.fromtimestamp(payload["iat"], tz=datetime.UTC)
    assert before - datetime.timedelta(seconds=2) <= iat <= after + datetime.timedelta(seconds=2)


# ── C4: refresh TTL flows from config ──


@pytest.mark.parametrize("days", [1, 7, 30])
def test_refresh_ttl_follows_config(days: int) -> None:
    from app.auth.routes import _refresh_ttl_seconds

    with patch("app.auth.routes.get_settings") as mock:
        mock.return_value.auth.refresh_token_expire_days = days
        assert _refresh_ttl_seconds() == days * 86400


# ── C4: Redis fail-open logs enriched warning ──


async def test_revocation_check_fails_open_emits_warning() -> None:
    """When Redis raises, is_token_revoked returns False and logs error / error_type."""

    class _Boom(Exception):
        pass

    async def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise _Boom("connection refused")

    redis_mock = AsyncMock()
    redis_mock.get = _raise

    with (
        patch("app.core.redis.get_redis", AsyncMock(return_value=redis_mock)),
        patch("app.auth.token.logger") as mock_logger,
    ):
        result = await is_token_revoked("some-jti")

    assert result is False
    mock_logger.warning.assert_called_once()
    call = mock_logger.warning.call_args
    assert call.args[0] == "auth.token.revocation_check_degraded"
    assert call.kwargs["error_type"] == "_Boom"
    assert "connection refused" in call.kwargs["error"]
