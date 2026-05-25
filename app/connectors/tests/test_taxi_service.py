"""Per-service tests for TaxiConnectorService.

Coverage: 200 happy path, 429 → ExportFailedError, malformed JSON →
ExportFailedError + lease.report_failure(0), KeyError on response →
ExportFailedError + lease NOT blamed (F023), NoHealthyCredentialsError
propagates so the orchestrator can wrap it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.connectors.exceptions import ExportFailedError
from app.connectors.taxi.service import TaxiConnectorService
from app.core.credentials import CredentialLease, CredentialPool
from app.core.exceptions import NoHealthyCredentialsError


def _resp(status: int = 200, body: dict[str, object] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=body or {},
        request=httpx.Request("POST", "http://test"),
    )


def _lease(key: str = "k1") -> AsyncMock:
    lease = AsyncMock(spec=CredentialLease)
    lease.key = key
    lease.report_success = AsyncMock()
    lease.report_failure = AsyncMock()
    return lease


def _pool(lease: AsyncMock) -> AsyncMock:
    pool = AsyncMock(spec=CredentialPool)
    pool.get_key = AsyncMock(return_value=lease)
    return pool


class TestTaxiService:
    @pytest.mark.asyncio()
    async def test_happy_path_returns_external_id(self) -> None:
        lease = _lease()
        service = TaxiConnectorService(pool=_pool(lease))
        with patch(
            "app.connectors._base.api_key.resilient_request",
            new_callable=AsyncMock,
            return_value=_resp(200, {"id": "tpl_1"}),
        ) as mock_req:
            result = await service.export("<p>x</p>", "Newsletter")
        assert result == "tpl_1"
        lease.report_success.assert_awaited_once()
        # Taxi uses X-API-Key, not Authorization
        assert mock_req.call_args.kwargs["headers"]["X-API-Key"] == "k1"

    @pytest.mark.asyncio()
    async def test_429_raises_export_failed_and_blames_lease(self) -> None:
        lease = _lease()
        service = TaxiConnectorService(pool=_pool(lease))
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=_resp(429),
            ),
            pytest.raises(ExportFailedError, match="Taxi API returned 429"),
        ):
            await service.export("<p>x</p>", "Newsletter")
        lease.report_failure.assert_awaited_once_with(429)

    @pytest.mark.asyncio()
    async def test_401_blames_lease_and_does_not_retry(self) -> None:
        # ApiKey services have no token-refresh path — 401 is terminal,
        # unlike OAuth services where a 401 evicts the cached token and retries.
        lease = _lease()
        service = TaxiConnectorService(pool=_pool(lease))
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=_resp(401),
            ) as mock_req,
            pytest.raises(ExportFailedError, match="Taxi API returned 401"),
        ):
            await service.export("<p>x</p>", "Newsletter")
        assert mock_req.await_count == 1
        lease.report_failure.assert_awaited_once_with(401)
        lease.report_success.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_malformed_json_blames_lease_with_zero(self) -> None:
        lease = _lease()
        service = TaxiConnectorService(pool=_pool(lease))
        bad = httpx.Response(
            status_code=200,
            content=b"<<not json>>",
            request=httpx.Request("POST", "http://test"),
        )
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=bad,
            ),
            pytest.raises(ExportFailedError, match="Taxi export failed"),
        ):
            await service.export("<p>x</p>", "Newsletter")
        lease.report_failure.assert_awaited_once_with(0)

    @pytest.mark.asyncio()
    async def test_key_error_on_response_does_not_blame_lease(self) -> None:
        lease = _lease()
        service = TaxiConnectorService(pool=_pool(lease))
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=_resp(200, {"wrong_field": "x"}),
            ),
            pytest.raises(KeyError),
        ):
            await service.export("<p>x</p>", "Newsletter")
        lease.report_failure.assert_not_awaited()
        lease.report_success.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_no_healthy_credentials_propagates(self) -> None:
        pool = AsyncMock(spec=CredentialPool)
        pool.get_key = AsyncMock(side_effect=NoHealthyCredentialsError("taxi"))
        service = TaxiConnectorService(pool=pool)
        with pytest.raises(NoHealthyCredentialsError):
            await service.export("<p>x</p>", "Newsletter")
