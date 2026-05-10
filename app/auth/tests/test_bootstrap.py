# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportUnusedFunction=false
# mypy: disable-error-code="method-assign,attr-defined"
"""F030 regression tests for /api/v1/auth/bootstrap third-factor hardening.

Truth table covered:
- dev + zero users + loopback (127.0.0.1, ::1)              -> 200
- dev + zero users + non-loopback + no secret               -> 403 ForbiddenError
- dev + zero users + non-loopback + valid secret            -> 200
- dev + zero users + non-loopback + invalid secret          -> 403 ForbiddenError
- production + loopback                                     -> 401 InvalidCredentialsError
- dev + users-already-exist                                 -> 401 InvalidCredentialsError
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest

from app.auth.exceptions import InvalidCredentialsError
from app.auth.models import User
from app.auth.service import AuthService
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop AUTH__/ENVIRONMENT env vars so each test sets its own state."""
    monkeypatch.delenv("AUTH__BOOTSTRAP_SECRET", raising=False)
    monkeypatch.delenv("AUTH__JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("AUTH__DEMO_USER_PASSWORD", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Ensure get_settings cache is empty before each test and after the suite."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def service() -> AuthService:
    svc = AuthService(AsyncMock())
    svc.repo = AsyncMock()
    svc.repo.count = AsyncMock(return_value=0)

    async def _create(user: User) -> User:
        user.id = 1
        return user

    svc.repo.create = AsyncMock(side_effect=_create)
    return svc


@pytest.mark.asyncio
async def test_loopback_ipv4_succeeds(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    response = await service.bootstrap_demo(client_host="127.0.0.1", provided_secret=None)

    assert response.email == "admin@email-hub.dev"
    assert response.role == "admin"
    assert response.access_token


@pytest.mark.asyncio
async def test_loopback_ipv6_succeeds(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    response = await service.bootstrap_demo(client_host="::1", provided_secret=None)

    assert response.role == "admin"


@pytest.mark.asyncio
async def test_non_loopback_no_secret_is_forbidden(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """F030 mandatory regression: non-loopback origins are 403'd in development."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    with pytest.raises(ForbiddenError):
        await service.bootstrap_demo(client_host="192.0.2.1", provided_secret=None)
    service.repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_loopback_with_valid_secret_succeeds(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTH__BOOTSTRAP_SECRET", "correct-horse-battery-staple")

    response = await service.bootstrap_demo(
        client_host="192.0.2.1", provided_secret="correct-horse-battery-staple"
    )

    assert response.role == "admin"


@pytest.mark.asyncio
async def test_non_loopback_with_invalid_secret_is_forbidden(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTH__BOOTSTRAP_SECRET", "correct-horse-battery-staple")

    with pytest.raises(ForbiddenError):
        await service.bootstrap_demo(client_host="192.0.2.1", provided_secret="wrong")


@pytest.mark.asyncio
async def test_empty_configured_secret_blocks_non_loopback(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """An empty AUTH__BOOTSTRAP_SECRET must never authorize via the secret path."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("AUTH__BOOTSTRAP_SECRET", "")

    with pytest.raises(ForbiddenError):
        await service.bootstrap_demo(client_host="192.0.2.1", provided_secret="")


@pytest.mark.asyncio
async def test_testclient_host_is_not_loopback(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """Starlette TestClient sets client.host='testclient' — must not bypass."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    with pytest.raises(ForbiddenError):
        await service.bootstrap_demo(client_host="testclient", provided_secret=None)


@pytest.mark.asyncio
async def test_production_blocks_even_from_loopback(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """Existing env-gate must take precedence over the third factor."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH__JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("AUTH__DEMO_USER_PASSWORD", "rotated-strong-password")

    with pytest.raises(InvalidCredentialsError):
        await service.bootstrap_demo(client_host="127.0.0.1", provided_secret=None)


@pytest.mark.asyncio
async def test_existing_users_block_even_from_loopback(
    monkeypatch: pytest.MonkeyPatch, service: AuthService
) -> None:
    """Existing zero-user gate must take precedence over the third factor."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")
    service.repo.count = AsyncMock(return_value=1)

    with pytest.raises(InvalidCredentialsError):
        await service.bootstrap_demo(client_host="127.0.0.1", provided_secret=None)
