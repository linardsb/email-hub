"""Schema validation tests for workflow orchestration."""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from app.workflows.schemas import (
    Execution,
    FlowCreateRequest,
    TaskRun,
    WorkflowTriggerRequest,
)


class TestWorkflowTriggerRequest:
    def test_valid_request(self) -> None:
        req = WorkflowTriggerRequest(flow_id="email-build-and-qa", inputs={"brief": "test"})
        assert req.flow_id == "email-build-and-qa"
        assert req.inputs == {"brief": "test"}

    def test_flow_id_max_length(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 200 characters"):
            WorkflowTriggerRequest(flow_id="x" * 201)

    def test_default_empty_inputs(self) -> None:
        req = WorkflowTriggerRequest(flow_id="test")
        assert req.inputs == {}
        assert req.project_id is None


class TestFlowCreateRequest:
    def test_valid_flow_id_pattern(self) -> None:
        req = FlowCreateRequest(flow_id="my-flow_123", yaml_definition="id: test")
        assert req.flow_id == "my-flow_123"

    def test_invalid_flow_id_pattern(self) -> None:
        with pytest.raises(ValidationError, match="String should match pattern"):
            FlowCreateRequest(flow_id="My Flow!", yaml_definition="id: test")

    def test_flow_id_max_length(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 200 characters"):
            FlowCreateRequest(flow_id="x" * 201, yaml_definition="id: test")

    def test_yaml_definition_max_length(self) -> None:
        with pytest.raises(ValidationError, match="String should have at most 50000 characters"):
            FlowCreateRequest(flow_id="test", yaml_definition="x" * 50_001)


class TestExecution:
    def test_parse_task_runs(self) -> None:
        now = datetime.datetime.now(tz=datetime.UTC)
        execution = Execution(
            id="exec-1",
            namespace="email-hub",
            flow_id="test-flow",
            status="RUNNING",
            started=now,
            task_runs=[
                TaskRun(task_id="build", status="SUCCESS", started=now),
                TaskRun(task_id="qa", status="RUNNING"),
            ],
        )
        assert len(execution.task_runs) == 2
        assert execution.task_runs[0].status == "SUCCESS"
        assert execution.task_runs[1].started is None
