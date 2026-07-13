"""Basecamp REST API v4 provider."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.briefs.exceptions import BriefValidationError
from app.briefs.protocol import RawBriefItem
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _extract_ids(project_url: str) -> tuple[str, str]:
    """Extract account ID and project ID from Basecamp URL.

    URL format: https://3.basecamp.com/{account_id}/buckets/{project_id}/...
    """
    match = re.search(r"basecamp\.com/(\d+)/buckets/(\d+)", project_url)
    if not match:
        msg = f"Cannot extract Basecamp IDs from URL: {project_url}"
        raise BriefValidationError(msg)
    return match.group(1), match.group(2)


class BasecampBriefProvider:
    """Basecamp REST API provider."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url_override = base_url

    def _resolve_base_url(self, account_id: str) -> str:
        """Return override URL or build the real Basecamp API URL."""
        if self._base_url_override:
            return self._base_url_override
        return f"https://3.basecampapi.com/{account_id}"

    def _resolve_auth_url(self) -> str:
        """Return override URL for auth check or the real 37signals URL."""
        if self._base_url_override:
            return f"{self._base_url_override}/authorization.json"
        return "https://launchpad.37signals.com/authorization.json"

    async def validate_credentials(self, credentials: dict[str, str], project_url: str) -> bool:  # noqa: ARG002
        settings = get_settings()
        async with httpx.AsyncClient(timeout=settings.briefs.sync_timeout) as client:
            resp = await client.get(
                self._resolve_auth_url(),
                headers={
                    "Authorization": f"Bearer {credentials['access_token']}",
                    "User-Agent": "EmailHub (support@merkle.com)",
                },
            )
            resp.raise_for_status()
        return True

    async def extract_project_id(self, project_url: str) -> str:
        account_id, project_id = _extract_ids(project_url)
        return f"{account_id}/{project_id}"

    async def list_items(self, credentials: dict[str, str], project_id: str) -> list[RawBriefItem]:
        settings = get_settings()
        parts = project_id.split("/")
        if len(parts) != 2:
            msg = "Basecamp project_id must be in 'account_id/project_id' format"
            raise BriefValidationError(msg)
        account_id, bucket_id = parts
        base_url = self._resolve_base_url(account_id)
        headers = {
            "Authorization": f"Bearer {credentials['access_token']}",
            "User-Agent": "EmailHub (support@merkle.com)",
        }

        async with httpx.AsyncClient(timeout=settings.briefs.sync_timeout) as client:
            # First get the todolists for the project
            resp = await client.get(
                f"{base_url}/buckets/{bucket_id}/todolists.json",
                headers=headers,
            )
            resp.raise_for_status()
            todolists = resp.json()

            # Fetch todos from each todolist
            items: list[RawBriefItem] = []
            for todolist in todolists:
                todos_url = todolist.get("todos_url", "")
                if not todos_url:
                    continue
                todo_resp = await client.get(todos_url, headers=headers)
                if todo_resp.status_code != 200:
                    continue
                todos = todo_resp.json()

                for todo in todos:
                    assignees: list[str] = []
                    raw_assignees: list[dict[str, Any]] = todo.get("assignees", []) or []
                    for person in raw_assignees:
                        name: str = person.get("name", "")
                        if name:
                            assignees.append(name)

                    completed = todo.get("completed", False)

                    items.append(
                        RawBriefItem(
                            external_id=str(todo["id"]),
                            title=todo.get("title", todo.get("content", "")),
                            description="",
                            status="done" if completed else "open",
                            priority=None,
                            assignees=assignees,
                            labels=[],
                        )
                    )

                    if len(items) >= settings.briefs.max_items_per_sync:
                        break
                if len(items) >= settings.briefs.max_items_per_sync:
                    break

        return items

    async def get_item(
        self,
        credentials: dict[str, str],
        project_id: str,
        item_id: str,
    ) -> RawBriefItem:
        settings = get_settings()
        parts = project_id.split("/")
        if len(parts) != 2:
            msg = "Basecamp project_id must be in 'account_id/project_id' format"
            raise BriefValidationError(msg)
        account_id, bucket_id = parts
        base_url = self._resolve_base_url(account_id)
        headers = {
            "Authorization": f"Bearer {credentials['access_token']}",
            "User-Agent": "EmailHub (support@merkle.com)",
        }

        async with httpx.AsyncClient(timeout=settings.briefs.sync_timeout) as client:
            resp = await client.get(
                f"{base_url}/buckets/{bucket_id}/todos/{item_id}.json",
                headers=headers,
            )
            resp.raise_for_status()
            todo = resp.json()

        assignees: list[str] = []
        raw_assignees: list[dict[str, Any]] = todo.get("assignees", []) or []
        for person in raw_assignees:
            name: str = person.get("name", "")
            if name:
                assignees.append(name)

        return RawBriefItem(
            external_id=str(todo["id"]),
            title=todo.get("title", todo.get("content", "")),
            description=todo.get("description", "") or "",
            status="done" if todo.get("completed") else "open",
            priority=None,
            assignees=assignees,
            labels=[],
        )
