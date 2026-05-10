"""SFMC sync provider — bidirectional template sync via Content Builder Asset API."""

# TODO(tech-debt): the OAuth cache plumbing here mirrors `OAuthConnectorService`
# (app/connectors/_base/oauth.py) — only the bidirectional CRUD surface keeps
# this class separate. Future option-(a) unification would migrate onto an
# `OAuthSyncProviderBase` ABC. See closed deferred-items entry
# `tech-debt-04-sync-provider-duplication`.

from __future__ import annotations

from collections.abc import Mapping, Sequence

import httpx

from app.connectors.http_resilience import resilient_request
from app.connectors.sync_schemas import ESPTemplate
from app.core.cache import LruWithTtl
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_CACHE_MAXSIZE = 64
_TOKEN_REFRESH_GRACE = 60.0
_DEFAULT_TOKEN_TTL = 3600.0


class SFMCSyncProvider:
    """Implements ESPSyncProvider for Salesforce Marketing Cloud.

    Credentials: ``{"client_id": "...", "client_secret": "...", "subdomain": "..."}``

    Auth flow: OAuth2 client_credentials → POST /v2/token → Bearer on Asset API.
    """

    _base_url: str

    def __init__(self, settings: Settings | None = None) -> None:
        _settings = settings or get_settings()
        self._base_url = _settings.esp_sync.sfmc_base_url
        self._token_cache: LruWithTtl[str, str] = LruWithTtl(
            maxsize=_TOKEN_CACHE_MAXSIZE,
            default_ttl=_DEFAULT_TOKEN_TTL,
        )

    @staticmethod
    def _cache_key(credentials: dict[str, str]) -> str:
        return f"sfmc:{credentials['client_id']}"

    async def _get_access_token(self, credentials: dict[str, str]) -> str:
        """Exchange client credentials for an access token, with caching."""
        key = self._cache_key(credentials)
        cached = self._token_cache.get(key)
        if cached is not None:
            return cached

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._base_url}/v2/token",
                json={
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            token = str(data["access_token"])
            expires_in = float(data.get("expires_in", _DEFAULT_TOKEN_TTL))
            ttl = max(expires_in - _TOKEN_REFRESH_GRACE, 1.0)
            self._token_cache.put(key, token, ttl=ttl)
            return token

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def _call_with_auth(
        self,
        credentials: dict[str, str],
        method: str,
        url: str,
        params: Mapping[
            str, str | int | float | bool | None | Sequence[str | int | float | bool | None]
        ]
        | None = None,
        json: object | None = None,
    ) -> httpx.Response:
        """Make an API call; on 401 evict cache, re-auth, retry once."""
        token = await self._get_access_token(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await resilient_request(
                client, method, url, headers=self._headers(token), params=params, json=json
            )
            if resp.status_code == 401:
                self._token_cache.pop(self._cache_key(credentials))
                token = await self._get_access_token(credentials)
                resp = await resilient_request(
                    client, method, url, headers=self._headers(token), params=params, json=json
                )
            return resp

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    async def validate_credentials(self, credentials: dict[str, str]) -> bool:
        """Validate by performing token exchange."""
        try:
            await self._get_access_token(credentials)
            return True
        except httpx.HTTPError:
            logger.warning("sfmc.sync.validate_failed", exc_info=True)
            return False

    async def list_templates(self, credentials: dict[str, str]) -> list[ESPTemplate]:
        """List all SFMC content assets."""
        resp = await self._call_with_auth(
            credentials,
            "GET",
            f"{self._base_url}/asset/v1/content/assets",
            params={"$page": 1, "$pageSize": 1000},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            ESPTemplate(
                id=str(asset["id"]),
                name=asset["name"],
                html=asset.get("content", ""),
                esp_type="sfmc",
                created_at=asset.get("created_at", ""),
                updated_at=asset.get("updated_at", ""),
            )
            for asset in data.get("items", [])
        ]

    async def get_template(self, template_id: str, credentials: dict[str, str]) -> ESPTemplate:
        """Get a single SFMC asset."""
        resp = await self._call_with_auth(
            credentials,
            "GET",
            f"{self._base_url}/asset/v1/content/assets/{template_id}",
        )
        resp.raise_for_status()
        asset = resp.json()
        return ESPTemplate(
            id=str(asset["id"]),
            name=asset["name"],
            html=asset.get("content", ""),
            esp_type="sfmc",
            created_at=asset.get("created_at", ""),
            updated_at=asset.get("updated_at", ""),
        )

    async def create_template(
        self, name: str, html: str, credentials: dict[str, str]
    ) -> ESPTemplate:
        """Create a new content asset in SFMC."""
        resp = await self._call_with_auth(
            credentials,
            "POST",
            f"{self._base_url}/asset/v1/content/assets",
            json={"name": name, "content": html},
        )
        resp.raise_for_status()
        asset = resp.json()
        return ESPTemplate(
            id=str(asset["id"]),
            name=asset.get("name", name),
            html=asset.get("content", html),
            esp_type="sfmc",
            created_at=asset.get("created_at", ""),
            updated_at=asset.get("updated_at", ""),
        )

    async def update_template(
        self, template_id: str, html: str, credentials: dict[str, str]
    ) -> ESPTemplate:
        """Update an SFMC asset's HTML."""
        resp = await self._call_with_auth(
            credentials,
            "PATCH",
            f"{self._base_url}/asset/v1/content/assets/{template_id}",
            json={"content": html},
        )
        resp.raise_for_status()
        asset = resp.json()
        return ESPTemplate(
            id=str(asset["id"]),
            name=asset.get("name", ""),
            html=asset.get("content", html),
            esp_type="sfmc",
            created_at=asset.get("created_at", ""),
            updated_at=asset.get("updated_at", ""),
        )

    async def delete_template(self, template_id: str, credentials: dict[str, str]) -> bool:
        """Delete an SFMC asset."""
        resp = await self._call_with_auth(
            credentials,
            "DELETE",
            f"{self._base_url}/asset/v1/content/assets/{template_id}",
        )
        return resp.status_code == 200
