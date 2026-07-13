"""Route integration tests for workflow orchestration."""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler  # pyright: ignore[reportMissingTypeStubs]
from slowapi.errors import RateLimitExceeded  # pyright: ignore[reportMissingTypeStubs]

from app.auth.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.workflows.routes import get_service, router
from app.workflows.schemas import (
    FlowSummary,
    WorkflowListResponse,
    WorkflowStatusResponse,
)


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the workflows router mounted."""
    test_app = FastAPI()
    test_app.state.limiter = limiter
    test_app.add_exception_handler(RateLimitExceeded, cast(Any, _rate_limit_exceeded_handler))
    test_app.include_router(router)
    return test_app


@pytest.fixture
def _mock_service() -> AsyncMock:
    service = AsyncMock()
    service.list_workflows.return_value = WorkflowListResponse(
        flows=[
            FlowSummary(
                id="email-build-and-qa",
                namespace="email-hub",
                description="Test",
            )
        ]
    )
    service.trigger.return_value = WorkflowStatusResponse(
        execution_id="exec-1",
        flow_id="email-build-and-qa",
        status="CREATED",
        started=datetime.datetime.now(tz=datetime.UTC),
    )
    service.get_status.return_value = WorkflowStatusResponse(
        execution_id="exec-1",
        flow_id="email-build-and-qa",
        status="RUNNING",
        started=datetime.datetime.now(tz=datetime.UTC),
    )
    return service


@pytest.fixture
def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "test@test.com"
    user.role = "admin"
    return user


@pytest.fixture
def client(_mock_service: AsyncMock, _mock_user: MagicMock) -> Iterator[TestClient]:
    """Test client with mocked auth and service."""
    app = _make_app()
    limiter.enabled = False

    app.dependency_overrides[get_service] = lambda: _mock_service
    app.dependency_overrides[get_current_user] = lambda: _mock_user

    yield TestClient(app)

    app.dependency_overrides.clear()
    limiter.enabled = True


class TestListWorkflows:
    def test_list_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/v1/workflows/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["flows"]) == 1
        assert data["flows"][0]["id"] == "email-build-and-qa"


class TestTriggerWorkflow:
    def test_trigger_returns_201(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/workflows/trigger",
            json={"flow_id": "email-build-and-qa", "inputs": {"brief": "test"}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["execution_id"] == "exec-1"
        assert data["status"] == "CREATED"


class TestGetExecutionStatus:
    def test_get_status_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/v1/workflows/exec-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution_id"] == "exec-1"
        assert data["status"] == "RUNNING"


class TestAuthRequired:
    def test_list_requires_auth(self) -> None:
        """Without auth override, routes should require authentication."""
        app = _make_app()
        limiter.enabled = False
        test_client = TestClient(app)
        resp = test_client.get("/api/v1/workflows/")
        # Should be 401 or 403 without valid auth
        assert resp.status_code in (401, 403)
        limiter.enabled = True
