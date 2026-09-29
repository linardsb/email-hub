"""Minimal async client for TypeSafe's System One endpoint (Jev).

Talks to the REST API with the existing ``httpx`` instead of ``typesafe-sdk``
(plan Q2): one endpoint, no retries (a failed shadow call is a logged miss),
and the API key only ever travels in the ``Authorization`` header.
"""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.core.exceptions import ServiceUnavailableError

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-1.13.0"
JEV_TIMEOUT_S = 10.0
_REQUEST_ID_HEADER = "x-typesafe-request-id"


class ChoiceAnswer(BaseModel):
    """Answer to a Choice question."""

    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float


class NoulAnswer(BaseModel):
    """Answer to a Noul (yes/no) question; ``noul`` is P(yes)."""

    type: Literal["noul"]
    noul: float


Answer = Annotated[ChoiceAnswer | NoulAnswer, Field(discriminator="type")]


class Usage(BaseModel):
    """Token usage for one request."""

    input_tokens: int = 0
    output_tokens: int = 0


class SystemOneResponse(BaseModel):
    """Response body of ``POST /v1/systemone``."""

    model: str
    answers: dict[str, Answer]
    usage: Usage = Field(default_factory=Usage)
    request_id: str | None = None  # from the response header, not the body


_RESPONSE_ADAPTER = TypeAdapter(SystemOneResponse)


class JevError(ServiceUnavailableError):
    """A Jev call failed: transport error, non-2xx status or malformed body."""

    def __init__(
        self, message: str, *, status: int | None = None, request_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.request_id = request_id


class JevClient:
    """Async System One client. Closes only an ``httpx.AsyncClient`` it created."""

    def __init__(self, api_key: str, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=JEV_TIMEOUT_S)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def system_one(
        self,
        state: dict[str, object],
        questions: dict[str, dict[str, object]],
    ) -> SystemOneResponse:
        """Send one fan-out request; raise :class:`JevError` on any failure."""
        body = {"state": state, "model": JEV_MODEL, "questions": questions}
        try:
            resp = await self._http.post(
                JEV_URL,
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=JEV_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            raise JevError(f"transport error: {type(exc).__name__}") from exc
        request_id = resp.headers.get(_REQUEST_ID_HEADER)
        if not resp.is_success:
            raise JevError(
                f"HTTP {resp.status_code}", status=resp.status_code, request_id=request_id
            )
        try:
            parsed = _RESPONSE_ADAPTER.validate_json(resp.content)
        except ValidationError as exc:
            raise JevError(
                "malformed response body", status=resp.status_code, request_id=request_id
            ) from exc
        return parsed.model_copy(update={"request_id": request_id})
