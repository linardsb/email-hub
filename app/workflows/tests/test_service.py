"""Unit tests for WorkflowService."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workflows.exceptions import InvalidFlowDefinitionError, WorkflowValidationError
from app.workflows.schemas import Flow
from app.workflows.service import WorkflowService


def _make_service(mock_client: AsyncMock | None = None) -> WorkflowService:
    with patch("app.workflows.service.KestraClient") as mock_cls:
        if mock_client:
            mock_cls.return_value = mock_client
        service = WorkflowService()
    return service


def _make_flow(flow_id: str = "test-flow", **kwargs: Any) -> Flow:
    return Flow(
        id=flow_id,
        namespace="email-hub",
        **kwargs,
    )


class TestListWorkflows:
    @pytest.mark.anyio
    async def test_merges_remote_and_templates(self) -> None:
        mock_client = AsyncMock()
        mock_client.list_flows.return_value = [
            _make_flow("remote-flow", description="Remote"),
        ]

        service = _make_service(mock_client)
        # Patch bundled templates to include one not in remote
        with patch.object(
            service,
            "_list_bundled_templates",
            return_value=[
                {
                    "id": "email-build-and-qa",
                    "namespace": "email-hub",
                    "description": "Bundled",
                },
                {"id": "remote-flow", "namespace": "email-hub", "description": "Duplicate"},
            ],
        ):
            result = await service.list_workflows()

        # Remote + 1 unique bundled template (remote-flow deduplicated)
        assert len(result.flows) == 2
        ids = {f.id for f in result.flows}
        assert "remote-flow" in ids
        assert "email-build-and-qa" in ids

        # Bundled template flagged correctly
        bundled = next(f for f in result.flows if f.id == "email-build-and-qa")
        assert bundled.is_template is True


class TestCreateCustomFlow:
    @pytest.mark.anyio
    async def test_rejects_disallowed_task_type(self) -> None:
        service = _make_service()
        user = MagicMock()
        user.id = 1

        from app.workflows.schemas import FlowCreateRequest

        data = FlowCreateRequest(
            flow_id="evil-flow",
            yaml_definition='tasks:\n  - id: pwn\n    type: "os.system"\n',
        )

        with pytest.raises(InvalidFlowDefinitionError, match=r"Disallowed task type.*os\.system"):
            await service.create_custom_flow(data, user)


class TestValidateTaskTypes:
    def test_accepts_hub_tasks(self) -> None:
        service = _make_service()
        tasks = [
            {"id": "build", "type": "hub.blueprint_run"},
            {"id": "qa", "type": "hub.qa_check"},
        ]
        # Should not raise
        service._validate_task_types(tasks)

    def test_accepts_kestra_builtins(self) -> None:
        service = _make_service()
        tasks = [
            {
                "id": "parallel",
                "type": "io.kestra.core.tasks.flows.Parallel",
                "tasks": [
                    {"id": "qa", "type": "hub.qa_check"},
                ],
            },
        ]
        service._validate_task_types(tasks)

    def test_rejects_arbitrary_types(self) -> None:
        service = _make_service()
        tasks = [
            {"id": "shell", "type": "io.kestra.plugin.scripts.shell.Commands"},
        ]
        with pytest.raises(InvalidFlowDefinitionError, match="Disallowed task type"):
            service._validate_task_types(tasks)

    def test_recurses_into_nested_tasks(self) -> None:
        service = _make_service()
        tasks = [
            {
                "id": "parallel",
                "type": "io.kestra.core.tasks.flows.Parallel",
                "tasks": [
                    {"id": "evil", "type": "os.system"},
                ],
            },
        ]
        with pytest.raises(InvalidFlowDefinitionError, match=r"os\.system"):
            service._validate_task_types(tasks)


class TestParseAndValidateYaml:
    def test_invalid_yaml_raises(self) -> None:
        service = _make_service()
        with pytest.raises(WorkflowValidationError, match="Invalid YAML"):
            service._parse_and_validate_yaml("{{invalid")

    def test_non_dict_raises(self) -> None:
        service = _make_service()
        with pytest.raises(WorkflowValidationError, match="YAML must be a mapping"):
            service._parse_and_validate_yaml("- item1\n- item2")


class TestSyncFlowTemplates:
    @pytest.mark.anyio
    async def test_syncs_bundled_templates(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_flow.return_value = _make_flow("email-build-and-qa")

        service = _make_service(mock_client)

        with patch.object(
            service,
            "_list_bundled_templates",
            return_value=[
                {"id": "email-build-and-qa", "namespace": "email-hub"},
                {"id": "weekly-newsletter", "namespace": "email-hub"},
            ],
        ):
            count = await service.sync_flow_templates()

        assert count == 2
        assert mock_client.create_flow.call_count == 2
