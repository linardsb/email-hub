"""Per-service tests for BrazeConnectorService.

Coverage: 200 happy path, 429 → ExportFailedError, malformed JSON →
ExportFailedError + lease.report_failure(0), KeyError on response →
ExportFailedError + lease NOT blamed (F023), NoHealthyCredentialsError
propagates so the orchestrator can wrap it.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.connectors.braze.service import BrazeConnectorService
from app.connectors.exceptions import ExportFailedError
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


class TestBrazeService:
    @pytest.mark.asyncio()
    async def test_happy_path_returns_external_id(self) -> None:
        lease = _lease()
        service = BrazeConnectorService(pool=_pool(lease))
        with patch(
            "app.connectors._base.api_key.resilient_request",
            new_callable=AsyncMock,
            return_value=_resp(200, {"content_block_id": "cb_1"}),
        ):
            result = await service.export("<h1>x</h1>", "Welcome")
        assert result == "cb_1"
        lease.report_success.assert_awaited_once()
        lease.report_failure.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_429_raises_export_failed_and_blames_lease(self) -> None:
        lease = _lease()
        service = BrazeConnectorService(pool=_pool(lease))
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=_resp(429, {"error": "rate"}),
            ),
            pytest.raises(ExportFailedError, match="Braze API returned 429"),
        ):
            await service.export("<h1>x</h1>", "Welcome")
        lease.report_failure.assert_awaited_once_with(429)
        lease.report_success.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_401_blames_lease_and_does_not_retry(self) -> None:
        # ApiKey services have no token-refresh path — 401 is terminal,
        # unlike OAuth services where a 401 evicts the cached token and retries.
        lease = _lease()
        service = BrazeConnectorService(pool=_pool(lease))
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=_resp(401, {"error": "unauthorized"}),
            ) as mock_req,
            pytest.raises(ExportFailedError, match="Braze API returned 401"),
        ):
            await service.export("<h1>x</h1>", "Welcome")
        assert mock_req.await_count == 1
        lease.report_failure.assert_awaited_once_with(401)
        lease.report_success.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_malformed_json_blames_lease_with_zero(self) -> None:
        lease = _lease()
        service = BrazeConnectorService(pool=_pool(lease))
        bad = httpx.Response(
            status_code=200,
            content=b"not-json",
            request=httpx.Request("POST", "http://test"),
        )
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=bad,
            ),
            pytest.raises(ExportFailedError, match="Braze export failed"),
        ):
            await service.export("<h1>x</h1>", "Welcome")
        lease.report_failure.assert_awaited_once_with(0)

    @pytest.mark.asyncio()
    async def test_key_error_on_response_does_not_blame_lease(self) -> None:
        """F023: KeyError parsing response must not count as transport failure."""
        lease = _lease()
        service = BrazeConnectorService(pool=_pool(lease))
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                return_value=_resp(200, {"unexpected_field": "x"}),
            ),
            pytest.raises(KeyError),
        ):
            await service.export("<h1>x</h1>", "Welcome")
        lease.report_failure.assert_not_awaited()
        lease.report_success.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_no_healthy_credentials_propagates(self) -> None:
        pool = AsyncMock(spec=CredentialPool)
        pool.get_key = AsyncMock(side_effect=NoHealthyCredentialsError("braze"))
        service = BrazeConnectorService(pool=pool)
        with pytest.raises(NoHealthyCredentialsError):
            await service.export("<h1>x</h1>", "Welcome")

    @pytest.mark.asyncio()
    async def test_transport_error_blames_lease(self) -> None:
        lease = _lease()
        service = BrazeConnectorService(pool=_pool(lease))
        with (
            patch(
                "app.connectors._base.api_key.resilient_request",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("refused"),
            ),
            pytest.raises(ExportFailedError, match="Braze export failed"),
        ):
            await service.export("<h1>x</h1>", "Welcome")
        lease.report_failure.assert_awaited_once_with(0)

    @pytest.mark.asyncio()
    async def test_explicit_credentials_skip_pool(self) -> None:
        pool = _pool(_lease())
        service = BrazeConnectorService(pool=pool)
        with patch(
            "app.connectors._base.api_key.resilient_request",
            new_callable=AsyncMock,
            return_value=_resp(200, {"content_block_id": "cb_explicit"}),
        ) as mock_req:
            result = await service.export(
                "<h1>x</h1>",
                "Welcome",
                credentials={"api_key": "explicit"},  # pragma: allowlist secret
            )
        assert result == "cb_explicit"
        pool.get_key.assert_not_awaited()
        assert mock_req.call_args.kwargs["headers"]["Authorization"] == "Bearer explicit"

    @pytest.mark.asyncio()
    async def test_payload_shape_matches_braze_api(self) -> None:
        service = BrazeConnectorService(pool=_pool(_lease()))
        with patch(
            "app.connectors._base.api_key.resilient_request",
            new_callable=AsyncMock,
            return_value=_resp(200, {"content_block_id": "cb_1"}),
        ) as mock_req:
            await service.export("<h1>x</h1>", "Welcome")
        body = json.dumps(mock_req.call_args.kwargs["json"])
        assert "Welcome" in body
        assert "<h1>x</h1>" in body
        assert "email-hub" in body
