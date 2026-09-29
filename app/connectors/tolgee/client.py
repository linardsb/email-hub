"""Async HTTP client for Tolgee Translation Management API v2."""

from __future__ import annotations

import re

import httpx

from app.connectors.http_resilience import resilient_request
from app.connectors.tolgee.schemas import (
    BCP47_PATTERN,
    PushResult,
    TolgeeLanguage,
    TolgeeProject,
    TranslationKey,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Gmail clipping threshold in bytes
GMAIL_CLIPPING_THRESHOLD = 102 * 1024  # 102KB


class TolgeeClient:
    """Async HTTP client for Tolgee Translation Management API v2."""

    def __init__(self, base_url: str, pat: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "X-API-Key": pat,
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    async def list_projects(self) -> list[TolgeeProject]:
        """List all Tolgee projects accessible with the PAT."""
        url = f"{self._base_url}/v2/projects"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await resilient_request(client, "GET", url, headers=self._headers)
        data = response.json()
        projects_data = data.get("_embedded", {}).get("projects", [])
        return [
            TolgeeProject(id=p["id"], name=p["name"], description=p.get("description", ""))
            for p in projects_data
        ]

    async def get_languages(self, project_id: int) -> list[TolgeeLanguage]:
        """List languages configured for a Tolgee project."""
        url = f"{self._base_url}/v2/projects/{project_id}/languages"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await resilient_request(client, "GET", url, headers=self._headers)
        data = response.json()
        languages_data = data.get("_embedded", {}).get("languages", [])
        return [
            TolgeeLanguage(
                id=lang["id"],
                tag=lang["tag"],
                name=lang["name"],
                original_name=lang.get("originalName", ""),
                flag_emoji=lang.get("flagEmoji", ""),
                base=lang.get("base", False),
            )
            for lang in languages_data
        ]

    async def get_translations(
        self, project_id: int, language: str, namespace: str | None = None
    ) -> dict[str, str]:
        """Fetch all translations for a language. Returns {key: translated_text}."""
        # Both are URL path segments; re-check here so every caller is covered.
        if not re.fullmatch(BCP47_PATTERN, language):
            msg = f"Invalid BCP-47 locale: {language!r}"
            raise ValueError(msg)
        if not str(project_id).isdigit():
            msg = f"Invalid Tolgee project id: {project_id!r}"
            raise ValueError(msg)
        url = f"{self._base_url}/v2/projects/{project_id}/translations/{language}"
        params: dict[str, str] = {}
        if namespace:
            params["ns"] = namespace
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await resilient_request(
                client, "GET", url, headers=self._headers, params=params
            )
        data = response.json()
        result: dict[str, str] = {}
        for key_name, value in data.items():
            if isinstance(value, str):
                result[key_name] = value
            elif isinstance(value, dict) and "text" in value:
                result[key_name] = value["text"]
        return result

    async def push_keys(self, project_id: int, keys: list[TranslationKey]) -> PushResult:
        """Create or update translation keys with source text in Tolgee."""
        url = f"{self._base_url}/v2/projects/{project_id}/keys/import"
        payload = {
            "keys": [
                {
                    "name": k.key,
                    "namespace": k.namespace,
                    "description": k.context or "",
                    "translations": {"en": k.source_text},
                }
                for k in keys
            ]
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await resilient_request(
                client, "POST", url, headers=self._headers, json=payload
            )
        data = response.json()
        return PushResult(
            created=data.get("created", 0),
            updated=data.get("updated", 0),
            skipped=data.get("skipped", 0),
        )

    async def export_translations(
        self, project_id: int, format: str, languages: list[str]
    ) -> bytes:
        """Bulk export translations in specified format."""
        url = f"{self._base_url}/v2/projects/{project_id}/export"
        params = {"format": format, "languages": ",".join(languages)}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await resilient_request(
                client, "GET", url, headers=self._headers, params=params
            )
        return response.content

    async def validate_connection(self) -> bool:
        """Validate PAT by listing projects. Returns True if authenticated."""
        try:
            await self.list_projects()
            return True
        except Exception:
            logger.warning("tolgee.connection_validation_failed", exc_info=True)
            return False
